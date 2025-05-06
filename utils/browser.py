"""
Browser automation utilities for the Threads Traffic Management System.
"""

import asyncio
import random
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
import json
import os
from pathlib import Path

import pyppeteer
from pyppeteer import launch
from pyppeteer.browser import Browser
from pyppeteer.page import Page
from fake_useragent import UserAgent

from config.settings import SAFETY


logger = logging.getLogger(__name__)


class BrowserManager:
    """Manage browser instances with stealth and safety features."""
    
    def __init__(self, headless: bool = True, proxy: Optional[Dict[str, Any]] = None):
        """Initialize the browser manager.
        
        Args:
            headless: Whether to run in headless mode
            proxy: Proxy configuration dict with keys: ip_address, port, username, password, protocol
        """
        self.headless = headless
        self.proxy = proxy
        self.browser = None
        self.page = None
        self.user_agent = UserAgent().random
        
        # Safety settings
        self.min_cooldown = SAFETY["browser_cooldown_min_seconds"]
        self.max_cooldown = SAFETY["browser_cooldown_max_seconds"]
        self.typing_speed_min = SAFETY["typing_speed_min_cps"]
        self.typing_speed_max = SAFETY["typing_speed_max_cps"]
        
    async def launch(self) -> Browser:
        """Launch a browser instance with stealth settings."""
        args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-infobars',
            '--window-position=0,0',
            '--ignore-certifcate-errors',
            '--ignore-certifcate-errors-spki-list',
            f'--user-agent={self.user_agent}'
        ]
        
        # Add proxy if configured
        if self.proxy:
            proxy_url = f"{self.proxy['protocol']}://"
            if self.proxy.get('username') and self.proxy.get('password'):
                proxy_url += f"{self.proxy['username']}:{self.proxy['password']}@"
            proxy_url += f"{self.proxy['ip_address']}:{self.proxy['port']}"
            args.append(f'--proxy-server={proxy_url}')
        
        self.browser = await launch(
            headless=self.headless,
            args=args,
            ignoreHTTPSErrors=True,
            autoClose=False
        )
        return self.browser
    
    async def new_page(self) -> Page:
        """Create a new page with stealth settings."""
        if not self.browser:
            await self.launch()
            
        self.page = await self.browser.newPage()
        
        # Set random viewport size
        await self.page.setViewport({
            'width': random.randint(1366, 1920),
            'height': random.randint(768, 1080)
        })
        
        # Set user agent
        await self.page.setUserAgent(self.user_agent)
        
        # Apply stealth settings
        await self._apply_stealth_settings()
        
        return self.page
    
    async def _apply_stealth_settings(self):
        """Apply stealth settings to avoid detection."""
        # Disable webdriver
        await self.page.evaluateOnNewDocument("""
        () => {
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
            
            // Plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        0: {type: "application/x-google-chrome-pdf"},
                        name: "Chrome PDF Plugin",
                        filename: "internal-pdf-viewer",
                        description: "Portable Document Format"
                    }
                ]
            });
            
            // Languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ["en-US", "en"]
            });
            
            // WebGL vendor
            const getParameter = WebGLRenderingContext.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter(parameter);
            };
        }
        """)
    
    async def close(self):
        """Close the browser instance."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None
    
    async def navigate(self, url: str, wait_for: str = 'networkidle0') -> bool:
        """Navigate to a URL with safety measures."""
        if not self.page:
            await self.new_page()
            
        try:
            response = await self.page.goto(url, {
                'waitUntil': wait_for,
                'timeout': 60000
            })
            await self._random_delay()
            return response.ok
        except Exception as e:
            logger.error(f"Navigation error: {str(e)}")
            return False
    
    async def login(self, username: str, password: str, login_url: str) -> bool:
        """Perform login with human-like behavior."""
        try:
            # Navigate to login page
            await self.navigate(login_url)
            
            # Find and fill username field
            username_selector = 'input[name="username"]'
            await self.page.waitForSelector(username_selector)
            await self._human_type(username_selector, username)
            
            # Find and fill password field
            password_selector = 'input[name="password"]'
            await self.page.waitForSelector(password_selector)
            await self._human_type(password_selector, password)
            
            # Click login button
            login_button = 'button[type="submit"]'
            await self.page.waitForSelector(login_button)
            await self._random_delay(min_delay=0.5, max_delay=1.5)
            await self._human_click(login_button)
            
            # Wait for navigation and check if login successful
            await self.page.waitForNavigation({'waitUntil': 'networkidle0'})
            
            # Check for successful login - this will depend on Threads specific elements
            # Here's a generic approach that looks for error messages
            error_elements = await self.page.querySelectorAll('.error-message')
            if error_elements and len(error_elements) > 0:
                logger.error("Login failed: Error message displayed")
                return False
                
            # Store cookies for later use
            cookies = await self.page.cookies()
            self._save_cookies(username, cookies)
            
            return True
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return False
    
    async def _human_type(self, selector: str, text: str):
        """Type like a human with variable speed."""
        await self.page.click(selector)
        for char in text:
            await self.page.type(selector, char)
            typing_delay = 1.0 / random.uniform(self.typing_speed_min, self.typing_speed_max)
            await asyncio.sleep(typing_delay)
    
    async def _human_click(self, selector: str):
        """Click like a human with mouse movement."""
        # Get the dimensions and position of the element
        dimensions = await self.page.evaluate(f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {{
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height
            }};
        }})()
        """)
        
        if not dimensions:
            # Fallback to direct click if we can't get dimensions
            await self.page.click(selector)
            return
            
        # Calculate a random point within the element
        x = dimensions['x'] + random.uniform(10, dimensions['width'] - 10)
        y = dimensions['y'] + random.uniform(5, dimensions['height'] - 5)
        
        # Move mouse to the element with human-like motion
        await self.page.mouse.move(x, y, {'steps': random.randint(5, 15)})
        
        # Short pause before clicking
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # Click the element
        await self.page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await self.page.mouse.up()
    
    async def _random_delay(self, min_delay: float = None, max_delay: float = None):
        """Introduce random delay to mimic human behavior."""
        min_delay = min_delay or self.min_cooldown
        max_delay = max_delay or self.max_cooldown
        delay = random.uniform(min_delay, max_delay)
        await asyncio.sleep(delay)
    
    def _save_cookies(self, username: str, cookies: List[Dict[str, Any]]):
        """Save cookies to a file for later use."""
        cookies_dir = Path("data") / "cookies"
        cookies_dir.mkdir(parents=True, exist_ok=True)
        
        cookie_file = cookies_dir / f"{username}.json"
        with open(cookie_file, 'w') as f:
            json.dump(cookies, f)
    
    async def load_cookies(self, username: str) -> bool:
        """Load cookies from file and apply them to the current page."""
        if not self.page:
            await self.new_page()
            
        cookie_file = Path("data") / "cookies" / f"{username}.json"
        if not cookie_file.exists():
            return False
            
        try:
            with open(cookie_file, 'r') as f:
                cookies = json.load(f)
                
            for cookie in cookies:
                await self.page.setCookie(cookie)
                
            return True
        except Exception as e:
            logger.error(f"Error loading cookies: {str(e)}")
            return False
    
    async def scroll_page(self, scroll_distance: int = None, 
                         scroll_count: int = 1, 
                         scroll_delay: Tuple[float, float] = (0.5, 2.0)):
        """Scroll the page with human-like behavior."""
        if not self.page:
            return
            
        for _ in range(scroll_count):
            # Either scroll a specific distance or a random amount
            if scroll_distance is None:
                # Random scroll between 100 and 800 pixels
                distance = random.randint(100, 800)
            else:
                distance = scroll_distance
                
            # Execute scroll with smooth behavior
            await self.page.evaluate(f'''
            () => {{
                window.scrollBy({{
                    top: {distance},
                    left: 0,
                    behavior: 'smooth'
                }});
            }}
            ''')
            
            # Random delay between scrolls
            delay = random.uniform(scroll_delay[0], scroll_delay[1])
            await asyncio.sleep(delay)


async def create_browser_instance(headless: bool = True, 
                                 proxy: Optional[Dict[str, Any]] = None) -> BrowserManager:
    """Helper function to create and initialize a browser instance."""
    browser_manager = BrowserManager(headless=headless, proxy=proxy)
    await browser_manager.launch()
    await browser_manager.new_page()
    return browser_manager 