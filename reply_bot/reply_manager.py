"""
Reply bot module to generate engagement through AI-driven contextual comments.
"""

import asyncio
import logging
import random
import time
from typing import Dict, Any, List, Optional, Tuple

from database.models import DatabaseManager, BotAccount, ReplyActivity, TrendingPost
from utils.browser import BrowserManager, create_browser_instance
from utils.ai_integration import generate_contextual_reply
from config.settings import THREADS_URLS, MAX_REPLIES_PER_DAY


logger = logging.getLogger(__name__)


class ReplyManager:
    """Manager for reply operations."""
    
    def __init__(self, 
                db_manager: DatabaseManager,
                browser_manager: Optional[BrowserManager] = None,
                headless: bool = True):
        """Initialize the reply manager.
        
        Args:
            db_manager: Database manager instance
            browser_manager: Optional browser manager (will be created if None)
            headless: Whether to run browser in headless mode
        """
        self.db_manager = db_manager
        self.browser_manager = browser_manager
        self.headless = headless
        self.bot_account_model = BotAccount(db_manager)
        self.reply_activity_model = ReplyActivity(db_manager)
        self.trending_post_model = TrendingPost(db_manager)
        
    async def initialize(self):
        """Initialize the reply manager if browser manager doesn't exist."""
        if not self.browser_manager:
            self.browser_manager = await create_browser_instance(headless=self.headless)
    
    async def close(self):
        """Close browser connections."""
        if self.browser_manager:
            await self.browser_manager.close()
            
    async def reply_to_trending_posts(self, 
                                     bot_account_id: int,
                                     max_replies: int = 5) -> int:
        """Reply to trending posts using AI-generated comments.
        
        Args:
            bot_account_id: ID of the bot account to use
            max_replies: Maximum number of posts to reply to
            
        Returns:
            Number of successfully posted replies
        """
        await self.initialize()
        
        # Get bot account info
        bot_account = self.bot_account_model.get_account(bot_account_id)
        if not bot_account:
            logger.error(f"Bot account with ID {bot_account_id} not found")
            return 0
            
        # Check if the account can post more replies today
        daily_replies = bot_account.get("daily_replies", 0)
        if daily_replies >= MAX_REPLIES_PER_DAY:
            logger.warning(f"Bot account {bot_account['username']} has reached the daily reply limit")
            return 0
            
        # Calculate how many replies we can do
        remaining_replies = min(MAX_REPLIES_PER_DAY - daily_replies, max_replies)
        
        # Get trending posts to reply to
        trending_posts = self.trending_post_model.get_unprocessed_posts(limit=remaining_replies)
        if not trending_posts:
            logger.warning("No trending posts found to reply to")
            return 0
            
        # Login with bot account
        logged_in = await self._login_bot_account(bot_account)
        if not logged_in:
            logger.error(f"Failed to login with bot account {bot_account['username']}")
            return 0
            
        # Reply to each post
        successful_replies = 0
        for post in trending_posts:
            try:
                # Generate AI reply
                reply_content = await generate_contextual_reply(post)
                
                # Add reply activity to the database as pending
                activity_id = self.reply_activity_model.add_activity(
                    bot_account_id=bot_account_id,
                    post_id=post["post_id"],
                    content=reply_content
                )
                
                # Post the reply
                replied = await self._post_reply(post["post_url"], reply_content)
                
                if replied:
                    # Update activity status
                    self.reply_activity_model.update_status(activity_id, "completed")
                    # Update bot account reply count
                    self.bot_account_model.update_activity_count(bot_account_id, "reply")
                    # Mark post as processed
                    self.trending_post_model.mark_as_processed(post["post_id"])
                    
                    successful_replies += 1
                    logger.info(f"Bot {bot_account['username']} replied to post by @{post.get('author_username', 'unknown')}")
                else:
                    # Update activity status
                    self.reply_activity_model.update_status(activity_id, "failed")
                    logger.warning(f"Failed to reply to post {post.get('post_id', 'unknown')}")
                    
                # Add random delay between replies (45-120 seconds)
                await asyncio.sleep(random.uniform(45, 120))
                
            except Exception as e:
                logger.error(f"Error processing reply for post {post.get('post_id', 'unknown')}: {str(e)}")
                continue
            
        return successful_replies
    
    async def _login_bot_account(self, bot_account: Dict[str, Any]) -> bool:
        """Login with a bot account.
        
        Args:
            bot_account: Bot account data
            
        Returns:
            True if login successful, False otherwise
        """
        # First try to use existing cookies
        cookies_loaded = await self.browser_manager.load_cookies(bot_account["username"])
        if cookies_loaded:
            # Navigate to a page to check if cookies are valid
            success = await self.browser_manager.navigate(THREADS_URLS["base_url"])
            
            # Check if we're logged in by looking for user menu or profile link
            try:
                logged_in = await self.browser_manager.page.evaluate("""
                () => {
                    // Look for elements that indicate we're logged in
                    return Boolean(
                        document.querySelector('a[href*="profile"]') || 
                        document.querySelector('img[alt*="profile"]')
                    );
                }
                """)
                
                if logged_in:
                    logger.info(f"Successfully loaded cookies for {bot_account['username']}")
                    # Update login time
                    self.bot_account_model.update_login_time(bot_account["id"])
                    return True
            except Exception:
                pass
                
        # If cookies didn't work, try normal login
        logger.info(f"Performing fresh login for {bot_account['username']}")
        login_success = await self.browser_manager.login(
            username=bot_account["username"],
            password=bot_account["password"],
            login_url=THREADS_URLS["login_url"]
        )
        
        if login_success:
            # Update login time
            self.bot_account_model.update_login_time(bot_account["id"])
            return True
            
        return False
    
    async def _post_reply(self, post_url: str, reply_content: str) -> bool:
        """Post a reply to a specific post.
        
        Args:
            post_url: URL of the post to reply to
            reply_content: Content of the reply
            
        Returns:
            True if reply successful, False otherwise
        """
        try:
            # Navigate to post URL
            logger.info(f"Navigating to post: {post_url}")
            await self.browser_manager.navigate(post_url)
            
            # Wait for post content to load
            await self.browser_manager.page.waitForSelector('article', {'timeout': 10000})
            
            # Click on reply input area or reply button
            reply_button_js = """
            () => {
                // Attempt to find the reply UI elements
                
                // First try to find a dedicated reply button
                const replyButtons = document.querySelectorAll('button');
                for (const button of replyButtons) {
                    if (button.textContent.trim().toLowerCase() === 'reply' || 
                        button.querySelector('svg[aria-label*="reply"]')) {
                        button.click();
                        return 'button';
                    }
                }
                
                // Next try to find a reply input/textarea
                const inputArea = document.querySelector('textarea[placeholder*="Reply"], input[placeholder*="Reply"]');
                if (inputArea) {
                    inputArea.click();
                    return 'input';
                }
                
                return null;  // Could not find reply UI element
            }
            """
            
            clicked_element_type = await self.browser_manager.page.evaluate(reply_button_js)
            
            if not clicked_element_type:
                logger.warning("Could not find reply UI element")
                return False
                
            # If we clicked a button, wait for input field to appear
            if clicked_element_type == 'button':
                await asyncio.sleep(1)
            
            # Look for the reply textarea to type in
            await self.browser_manager.page.waitForSelector('textarea, div[contenteditable="true"]', {'timeout': 5000})
            
            # Type the reply with human-like behavior
            await self._type_reply(reply_content)
            
            # Click post/reply button to submit
            post_button_js = """
            () => {
                // Find all buttons and look for Post or Reply button
                const buttons = document.querySelectorAll('button');
                for (const button of buttons) {
                    const text = button.textContent.trim().toLowerCase();
                    if (text === 'post' || text === 'reply' || text === 'send') {
                        if (!button.disabled) {
                            button.click();
                            return true;
                        }
                    }
                }
                return false;
            }
            """
            
            posted = await self.browser_manager.page.evaluate(post_button_js)
            
            if not posted:
                logger.warning("Could not click post/reply button")
                return False
                
            # Wait for the post to be submitted
            await asyncio.sleep(3)
            
            # Check if our reply appears in the page (basic verification)
            verify_js = f"""
            () => {{
                // Look for elements containing our reply text
                const elements = document.querySelectorAll('article, div[role="article"]');
                const searchText = "{reply_content.replace('"', '\\"').replace("'", "\\'")}".substring(0, 30);
                
                for (const elem of elements) {{
                    if (elem.textContent.includes(searchText)) {{
                        return true;
                    }}
                }}
                
                return false;
            }}
            """
            
            verified = await self.browser_manager.page.evaluate(verify_js)
            
            return posted and verified
            
        except Exception as e:
            logger.error(f"Error posting reply: {str(e)}")
            return False
    
    async def _type_reply(self, reply_content: str):
        """Type a reply with human-like behavior.
        
        Args:
            reply_content: Content of the reply to type
        """
        try:
            # Find the reply textarea or contenteditable div
            input_selector = 'textarea, div[contenteditable="true"]'
            
            # Clear the input field if needed
            await self.browser_manager.page.evaluate(f"""
            () => {{
                const input = document.querySelector('{input_selector}');
                if (input && input.value) {{
                    input.value = '';
                }}
            }}
            """)
            
            # Type with human-like delays
            await self.browser_manager._human_type(input_selector, reply_content)
            
        except Exception as e:
            logger.error(f"Error typing reply: {str(e)}")
            raise 