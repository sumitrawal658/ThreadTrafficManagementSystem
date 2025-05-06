import asyncio
import logging
import re
import time
from typing import Dict, Any, List, Optional

from bs4 import BeautifulSoup

from utils.browser import BrowserManager, create_browser_instance
from database.models import DatabaseManager, TrendingPost
from config.settings import THREADS_URLS


logger = logging.getLogger(__name__)


class ThreadsScraper:

    def __init__(self,
                db_manager: DatabaseManager,
                browser_manager: Optional[BrowserManager] = None,
                headless: bool = True):
        self.db_manager = db_manager
        self.browser_manager = browser_manager
        self.headless = headless
        self.trending_post_model = TrendingPost(db_manager)

    async def initialize(self):
        if not self.browser_manager:
            self.browser_manager = await create_browser_instance(headless=self.headless)

    async def close(self):
        if self.browser_manager:
            await self.browser_manager.close()

    async def scrape_trending_posts(self,
                                   limit: int = 50,
                                   scroll_count: int = 5) -> List[Dict[str, Any]]:
        await self.initialize()

        logger.info("Navigating to Threads explore page")
        await self.browser_manager.navigate(THREADS_URLS["explore_url"])

        logger.info(f"Scrolling {scroll_count} times to load more content")
        await self.browser_manager.scroll_page(scroll_count=scroll_count)

        posts = await self._extract_posts(limit)

        saved_posts = []
        for post in posts:
            try:
                post_id = self.trending_post_model.save(post)
                if post_id:
                    post["id"] = post_id
                    saved_posts.append(post)
                    logger.debug(f"Saved post {post['post_id']} by @{post['author_username']}")
            except Exception as e:
                logger.error(f"Error saving post: {str(e)}")

        logger.info(f"Scraped and saved {len(saved_posts)} trending posts")
        return saved_posts

    async def scrape_user_profile(self,
                                 username: str,
                                 extract_followers: bool = False) -> Dict[str, Any]:
        await self.initialize()

        profile_url = THREADS_URLS["user_profile"](username)
        logger.info(f"Navigating to user profile: {profile_url}")
        await self.browser_manager.navigate(profile_url)

        profile_data = await self._extract_profile_data()

        if extract_followers and profile_data:
            followers = await self._extract_followers(limit=20)
            profile_data["followers_sample"] = followers

        return profile_data

    async def scrape_post_details(self, post_url: str) -> Dict[str, Any]:
        await self.initialize()

        logger.info(f"Navigating to post: {post_url}")
        await self.browser_manager.navigate(post_url)

        await self.browser_manager.page.waitForSelector('article', {'timeout': 5000})

        html_content = await self.browser_manager.page.content()
        soup = BeautifulSoup(html_content, 'html.parser')

        post_elem = soup.select_one('article')
        if not post_elem:
            logger.warning("Could not find post element")
            return {}

        content_elem = post_elem.select_one('div[data-block="true"]')
        content = content_elem.text.strip() if content_elem else ""

        author_elem = post_elem.select_one('a[href*="@"]')
        author_username = ""
        if author_elem and author_elem.get('href'):
            author_username = author_elem.get('href').strip('/').replace('@', '')

        metrics = await self._extract_post_metrics()
        replies = await self._extract_post_replies(limit=10)

        post_data = {
            "post_id": self._extract_post_id_from_url(post_url),
            "post_url": post_url,
            "author_username": author_username,
            "content": content,
            "like_count": metrics.get("likes", 0),
            "reply_count": metrics.get("replies", 0),
            "repost_count": metrics.get("reposts", 0),
            "replies": replies,
            "timestamp": time.time(),
            "metadata": {"scraped_at": time.time()}
        }

        return post_data

    async def _extract_posts(self, limit: int) -> List[Dict[str, Any]]:
        await self.browser_manager.page.waitForSelector('article', {'timeout': 5000})

        html_content = await self.browser_manager.page.content()
        soup = BeautifulSoup(html_content, 'html.parser')

        post_elements = soup.select('article')

        posts = []
        for i, post_elem in enumerate(post_elements[:limit]):
            try:
                post_link_elem = post_elem.select_one('a[href*="/t/"]')
                if not post_link_elem or not post_link_elem.get('href'):
                    continue

                post_url = post_link_elem.get('href')
                if not post_url.startswith('http'):
                    post_url = f"https://www.threads.net{post_url}"

                post_id = self._extract_post_id_from_url(post_url)
                if not post_id:
                    continue

                author_elem = post_elem.select_one('a[href*="@"]')
                author_username = ""
                author_display_name = ""
                if author_elem:
                    if author_elem.get('href'):
                        author_username = author_elem.get('href').strip('/').replace('@', '')
                    author_display_name = author_elem.text.strip()

                content_elem = post_elem.select_one('div[data-block="true"]')
                content = content_elem.text.strip() if content_elem else ""

                metrics = await self._evaluate_post_metrics(i)

                post_data = {
                    "post_id": post_id,
                    "author_username": author_username,
                    "author_display_name": author_display_name,
                    "content": content,
                    "like_count": metrics.get("likes", 0),
                    "reply_count": metrics.get("replies", 0),
                    "repost_count": metrics.get("reposts", 0),
                    "post_url": post_url,
                    "metadata": {"scraped_at": time.time()}
                }

                posts.append(post_data)

            except Exception as e:
                logger.error(f"Error extracting post data: {str(e)}")
                continue

        return posts

    async def _evaluate_post_metrics(self, post_index: int) -> Dict[str, int]:
        try:
            metrics_js = f"""
            (() => {{
                const posts = document.querySelectorAll('article');
                if (!posts || !posts[{post_index}]) return {{}};

                const post = posts[{post_index}];
                const metricElements = post.querySelectorAll('span[role="button"]');

                let likes = 0;
                let replies = 0;
                let reposts = 0;

                for (const elem of metricElements) {{
                    const text = elem.textContent.trim();
                    const value = parseInt(text.replace(/[^0-9]/g, '')) || 0;

                    if (elem.querySelector('svg[aria-label*="like"]')) {{
                        likes = value;
                    }} else if (elem.querySelector('svg[aria-label*="comment"]') ||
                              elem.querySelector('svg[aria-label*="reply"]')) {{
                        replies = value;
                    }} else if (elem.querySelector('svg[aria-label*="repost"]')) {{
                        reposts = value;
                    }}
                }}

                return {{ likes, replies, reposts }};
            }})()
            """

            metrics = await self.browser_manager.page.evaluate(metrics_js)
            return metrics or {"likes": 0, "replies": 0, "reposts": 0}

        except Exception as e:
            logger.error(f"Error evaluating post metrics: {str(e)}")
            return {"likes": 0, "replies": 0, "reposts": 0}

    async def _extract_profile_data(self) -> Dict[str, Any]:
        try:
            await self.browser_manager.page.waitForSelector('header', {'timeout': 5000})

            html_content = await self.browser_manager.page.content()
            soup = BeautifulSoup(html_content, 'html.parser')

            header = soup.select_one('header')
            if not header:
                return {}

            username_elem = header.select_one('a[href*="@"]')
            username = ""
            if username_elem and username_elem.get('href'):
                username = username_elem.get('href').strip('/').replace('@', '')

            name_elem = header.select_one('h1, h2')
            display_name = name_elem.text.strip() if name_elem else ""

            bio_elem = header.select_one('div[data-block="true"]')
            bio = bio_elem.text.strip() if bio_elem else ""

            followers_js = """
            (() => {
                const counters = document.querySelectorAll('header a[href*="followers"] span');
                for (const counter of counters) {
                    const text = counter.textContent.trim();
                    if (text.includes('K') || text.includes('M') || /^[0-9.,]+$/.test(text)) {
                        if (text.includes('K')) {
                            return parseFloat(text.replace('K', '')) * 1000;
                        } else if (text.includes('M')) {
                            return parseFloat(text.replace('M', '')) * 1000000;
                        } else {
                            return parseInt(text.replace(/[^0-9]/g, '')) || 0;
                        }
                    }
                }
                return 0;
            })()
            """

            follower_count = await self.browser_manager.page.evaluate(followers_js)

            return {
                "username": username,
                "display_name": display_name,
                "bio": bio,
                "follower_count": follower_count,
                "profile_url": THREADS_URLS["user_profile"](username),
                "metadata": {"scraped_at": time.time()}
            }

        except Exception as e:
            logger.error(f"Error extracting profile data: {str(e)}")
            return {}

    async def _extract_followers(self, limit: int = 20) -> List[Dict[str, str]]:
        try:
            followers_selector = 'a[href*="followers"]'
            await self.browser_manager.page.waitForSelector(followers_selector, {'timeout': 5000})
            await self.browser_manager._human_click(followers_selector)

            modal_selector = 'div[role="dialog"]'
            await self.browser_manager.page.waitForSelector(modal_selector, {'timeout': 5000})

            for _ in range(3):
                await self.browser_manager.scroll_page(scroll_distance=300)

            followers_js = f"""
            (() => {{
                const followerItems = document.querySelectorAll('div[role="dialog"] a[href*="@"]');
                const followers = [];

                for (let i = 0; i < Math.min(followerItems.length, {limit}); i++) {{
                    const item = followerItems[i];
                    const href = item.getAttribute('href') || '';
                    const username = href.replace('/', '').replace('@', '');
                    const displayName = item.textContent.trim();

                    followers.push({{ username, displayName }});
                }}

                return followers;
            }})()
            """

            followers = await self.browser_manager.page.evaluate(followers_js)

            await self.browser_manager.page.mouse.click(10, 10)

            return followers

        except Exception as e:
            logger.error(f"Error extracting followers: {str(e)}")
            return []

    async def _extract_post_metrics(self) -> Dict[str, int]:
        try:
            metrics_js = """
            (() => {
                const metricElements = document.querySelectorAll('span[role="button"]');

                let likes = 0;
                let replies = 0;
                let reposts = 0;

                for (const elem of metricElements) {
                    const text = elem.textContent.trim();

                    let value = 0;
                    if (text.includes('K')) {
                        value = parseFloat(text.replace('K', '')) * 1000;
                    } else if (text.includes('M')) {
                        value = parseFloat(text.replace('M', '')) * 1000000;
                    } else {
                        value = parseInt(text.replace(/[^0-9]/g, '')) || 0;
                    }

                    if (elem.querySelector('svg[aria-label*="like"]')) {
                        likes = value;
                    } else if (elem.querySelector('svg[aria-label*="comment"]') ||
                              elem.querySelector('svg[aria-label*="reply"]')) {
                        replies = value;
                    } else if (elem.querySelector('svg[aria-label*="repost"]')) {
                        reposts = value;
                    }
                }

                return { likes, replies, reposts };
            })()
            """

            metrics = await self.browser_manager.page.evaluate(metrics_js)
            return metrics or {"likes": 0, "replies": 0, "reposts": 0}

        except Exception as e:
            logger.error(f"Error extracting post metrics: {str(e)}")
            return {"likes": 0, "replies": 0, "reposts": 0}

    async def _extract_post_replies(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            await asyncio.sleep(2)

            replies_js = f"""
            (() => {{
                const replyElements = document.querySelectorAll('article ~ div article');
                const replies = [];

                for (let i = 0; i < Math.min(replyElements.length, {limit}); i++) {{
                    const reply = replyElements[i];

                    const authorElem = reply.querySelector('a[href*="@"]');
                    const authorUsername = authorElem ?
                        authorElem.getAttribute('href').replace('/', '').replace('@', '') : '';
                    const authorDisplayName = authorElem ? authorElem.textContent.trim() : '';

                    const contentElem = reply.querySelector('div[data-block="true"]');
                    const content = contentElem ? contentElem.textContent.trim() : '';

                    const likeElem = reply.querySelector('span[role="button"]');
                    let likes = 0;
                    if (likeElem) {{
                        const likeText = likeElem.textContent.trim();
                        if (likeText.includes('K')) {{
                            likes = parseFloat(likeText.replace('K', '')) * 1000;
                        }} else if (likeText.includes('M')) {{
                            likes = parseFloat(likeText.replace('M', '')) * 1000000;
                        }} else {{
                            likes = parseInt(likeText.replace(/[^0-9]/g, '')) || 0;
                        }}
                    }}

                    replies.push({{
                        authorUsername,
                        authorDisplayName,
                        content,
                        likes
                    }});
                }}

                return replies;
            }})()
            """

            replies = await self.browser_manager.page.evaluate(replies_js)
            return replies or []

        except Exception as e:
            logger.error(f"Error extracting post replies: {str(e)}")
            return []

    def _extract_post_id_from_url(self, url: str) -> str:
        match = re.search(r'/t/([^/]+)', url)
        if match:
            return match.group(1)
        return ""