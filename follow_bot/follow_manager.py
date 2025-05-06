import asyncio
import logging
import random
import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from database.models import DatabaseManager, BotAccount, FollowActivity, TrendingPost
from utils.browser import BrowserManager, create_browser_instance
from config.settings import THREADS_URLS, MAX_FOLLOWS_PER_DAY


logger = logging.getLogger(__name__)


class FollowManager:

    def __init__(self,
                db_manager: DatabaseManager,
                browser_manager: Optional[BrowserManager] = None,
                headless: bool = True):
        self.db_manager = db_manager
        self.browser_manager = browser_manager
        self.headless = headless
        self.bot_account_model = BotAccount(db_manager)
        self.follow_activity_model = FollowActivity(db_manager)
        self.trending_post_model = TrendingPost(db_manager)

    async def initialize(self):
        if not self.browser_manager:
            self.browser_manager = await create_browser_instance(headless=self.headless)

    async def close(self):
        if self.browser_manager:
            await self.browser_manager.close()

    async def follow_trending_authors(self,
                                     bot_account_id: int,
                                     max_follows: int = 10) -> int:
        await self.initialize()

        bot_account = self.bot_account_model.get_account(bot_account_id)
        if not bot_account:
            logger.error(f"Bot account with ID {bot_account_id} not found")
            return 0

        daily_follows = bot_account.get("daily_follows", 0)
        if daily_follows >= MAX_FOLLOWS_PER_DAY:
            logger.warning(f"Bot account {bot_account['username']} has reached the daily follow limit")
            return 0

        remaining_follows = min(MAX_FOLLOWS_PER_DAY - daily_follows, max_follows)

        trending_posts = self.trending_post_model.get_unprocessed_posts(limit=remaining_follows * 2)
        if not trending_posts:
            logger.warning("No trending posts found to extract authors")
            return 0

        authors = []
        for post in trending_posts:
            username = post.get("author_username")
            if username and username not in authors:
                authors.append(username)
                if len(authors) >= remaining_follows:
                    break

        if not authors:
            logger.warning("No authors found to follow")
            return 0

        logged_in = await self._login_bot_account(bot_account)
        if not logged_in:
            logger.error(f"Failed to login with bot account {bot_account['username']}")
            return 0

        successful_follows = 0
        for username in authors:
            activity_id = self.follow_activity_model.add_activity(
                bot_account_id=bot_account_id,
                target_username=username,
                action_type="follow"
            )

            followed = await self._follow_user(username)

            if followed:
                self.follow_activity_model.update_status(activity_id, "completed")
                self.bot_account_model.update_activity_count(bot_account_id, "follow")
                successful_follows += 1
                logger.info(f"Bot {bot_account['username']} followed @{username}")
            else:
                self.follow_activity_model.update_status(activity_id, "failed")
                logger.warning(f"Failed to follow @{username}")

            await asyncio.sleep(random.uniform(30, 90))

        return successful_follows

    async def unfollow_inactive_users(self,
                                     bot_account_id: int,
                                     max_unfollows: int = 5,
                                     min_days_before_unfollow: int = 5) -> int:
        await self.initialize()

        bot_account = self.bot_account_model.get_account(bot_account_id)
        if not bot_account:
            logger.error(f"Bot account with ID {bot_account_id} not found")
            return 0

        with self.db_manager as cursor:
            cursor.execute('''
            SELECT fa.target_username
            FROM follow_activity fa
            WHERE fa.bot_account_id = ?
            AND fa.action_type = 'follow'
            AND fa.status = 'completed'
            AND fa.timestamp <= datetime('now', ? || ' days')
            AND fa.target_username NOT IN (
                SELECT fa2.target_username
                FROM follow_activity fa2
                WHERE fa2.bot_account_id = ?
                AND fa2.action_type = 'unfollow'
            )
            LIMIT ?
            ''', (bot_account_id, -min_days_before_unfollow, bot_account_id, max_unfollows))

            targets = cursor.fetchall()
            usernames_to_unfollow = [target[0] for target in targets]

        if not usernames_to_unfollow:
            logger.info(f"No users to unfollow for bot account {bot_account['username']}")
            return 0

        logged_in = await self._login_bot_account(bot_account)
        if not logged_in:
            logger.error(f"Failed to login with bot account {bot_account['username']}")
            return 0

        successful_unfollows = 0
        for username in usernames_to_unfollow:
            activity_id = self.follow_activity_model.add_activity(
                bot_account_id=bot_account_id,
                target_username=username,
                action_type="unfollow"
            )

            unfollowed = await self._unfollow_user(username)

            if unfollowed:
                self.follow_activity_model.update_status(activity_id, "completed")
                successful_unfollows += 1
                logger.info(f"Bot {bot_account['username']} unfollowed @{username}")
            else:
                self.follow_activity_model.update_status(activity_id, "failed")
                logger.warning(f"Failed to unfollow @{username}")

            await asyncio.sleep(random.uniform(30, 60))

        return successful_unfollows

    async def _login_bot_account(self, bot_account: Dict[str, Any]) -> bool:
        cookies_loaded = await self.browser_manager.load_cookies(bot_account["username"])
        if cookies_loaded:
            await self.browser_manager.navigate(THREADS_URLS["base_url"])

            try:
                logged_in = await self.browser_manager.page.evaluate("""
                () => {
                    return Boolean(
                        document.querySelector('a[href*="profile"]') ||
                        document.querySelector('img[alt*="profile"]')
                    );
                }
                """)

                if logged_in:
                    logger.info(f"Successfully loaded cookies for {bot_account['username']}")
                    self.bot_account_model.update_login_time(bot_account["id"])
                    return True
            except Exception:
                pass

        logger.info(f"Performing fresh login for {bot_account['username']}")
        login_success = await self.browser_manager.login(
            username=bot_account["username"],
            password=bot_account["password"],
            login_url=THREADS_URLS["login_url"]
        )

        if login_success:
            self.bot_account_model.update_login_time(bot_account["id"])
            return True

        return False

    async def _follow_user(self, username: str) -> bool:
        try:
            profile_url = THREADS_URLS["user_profile"](username)
            await self.browser_manager.navigate(profile_url)

            follow_button_js = """
            () => {
                const buttons = document.querySelectorAll('button');
                for (const button of buttons) {
                    const text = button.textContent.trim().toLowerCase();
                    if (text === 'follow') {
                        return true;
                    }
                }
                return false;
            }
            """

            has_follow_button = await self.browser_manager.page.evaluate(follow_button_js)

            if not has_follow_button:
                logger.warning(f"No follow button found for @{username} (might already be following)")
                return False

            follow_click_js = """
            () => {
                const buttons = document.querySelectorAll('button');
                for (const button of buttons) {
                    const text = button.textContent.trim().toLowerCase();
                    if (text === 'follow') {
                        button.click();
                        return true;
                    }
                }
                return false;
            }
            """

            await self.browser_manager.page.evaluate(follow_click_js)
            await asyncio.sleep(2)

            confirm_js = """
            () => {
                const buttons = document.querySelectorAll('button');
                for (const button of buttons) {
                    const text = button.textContent.trim().toLowerCase();
                    if (text === 'following' || text === 'requested' || text === 'pending') {
                        return true;
                    }
                }
                return false;
            }
            """

            is_following = await self.browser_manager.page.evaluate(confirm_js)
            return is_following

        except Exception as e:
            logger.error(f"Error following user @{username}: {str(e)}")
            return False

    async def _unfollow_user(self, username: str) -> bool:
        try:
            profile_url = THREADS_URLS["user_profile"](username)
            await self.browser_manager.navigate(profile_url)

            unfollow_button_js = """
            () => {
                const buttons = document.querySelectorAll('button');
                for (const button of buttons) {
                    const text = button.textContent.trim().toLowerCase();
                    if (text === 'following' || text === 'requested') {
                        return true;
                    }
                }
                return false;
            }
            """

            has_unfollow_button = await self.browser_manager.page.evaluate(unfollow_button_js)

            if not has_unfollow_button:
                logger.warning(f"No following button found for @{username} (might not be following)")
                return False

            following_click_js = """
            () => {
                const buttons = document.querySelectorAll('button');
                for (const button of buttons) {
                    const text = button.textContent.trim().toLowerCase();
                    if (text === 'following' || text === 'requested') {
                        button.click();
                        return true;
                    }
                }
                return false;
            }
            """

            await self.browser_manager.page.evaluate(following_click_js)
            await asyncio.sleep(1)

            confirm_unfollow_js = """
            () => {
                const dialogButtons = document.querySelectorAll('div[role="dialog"] button');
                for (const button of dialogButtons) {
                    const text = button.textContent.trim().toLowerCase();
                    if (text === 'unfollow' || text === 'cancel') {
                        button.click();
                        return true;
                    }
                }
                return false;
            }
            """

            await self.browser_manager.page.evaluate(confirm_unfollow_js)
            await asyncio.sleep(2)

            confirm_js = """
            () => {
                const buttons = document.querySelectorAll('button');
                for (const button of buttons) {
                    const text = button.textContent.trim().toLowerCase();
                    if (text === 'follow') {
                        return true;
                    }
                }
                return false;
            }
            """

            is_not_following = await self.browser_manager.page.evaluate(confirm_js)
            return is_not_following

        except Exception as e:
            logger.error(f"Error unfollowing user @{username}: {str(e)}")
            return False