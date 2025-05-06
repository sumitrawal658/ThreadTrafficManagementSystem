"""
Orchestration layer to coordinate bot activities and schedule tasks.
"""

import asyncio
import logging
import random
import time
import schedule
import threading
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import os
import signal
import sys

from database.models import DatabaseManager, BotAccount, SystemMetric, TrendingPost
from scraper.threads_scraper import ThreadsScraper
from follow_bot.follow_manager import FollowManager
from reply_bot.reply_manager import ReplyManager
from config.settings import SCRAPE_INTERVAL_MINUTES, MAX_FOLLOWS_PER_DAY, MAX_REPLIES_PER_DAY


logger = logging.getLogger(__name__)


class Scheduler:
    """Scheduler for coordinating bot activities."""
    
    def __init__(self, db_manager: DatabaseManager, headless: bool = True):
        """Initialize the scheduler.
        
        Args:
            db_manager: Database manager instance
            headless: Whether to run browser in headless mode
        """
        self.db_manager = db_manager
        self.headless = headless
        self.is_running = False
        self.stop_event = threading.Event()
        self.bot_account_model = BotAccount(db_manager)
        self.system_metric_model = SystemMetric(db_manager)
        self.trending_post_model = TrendingPost(db_manager)
        
        # Create directory for emergency shutdown file
        os.makedirs('data', exist_ok=True)
        self.emergency_file = os.path.join('data', 'emergency_shutdown')
    
    def start(self):
        """Start the scheduler and initialize tasks."""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
            
        self.is_running = True
        self.stop_event.clear()
        
        # Setup task schedule
        self._setup_task_schedule()
        
        # Start the scheduler thread
        scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        scheduler_thread.start()
        
        # Start emergency shutdown monitor thread
        monitor_thread = threading.Thread(target=self._emergency_monitor, daemon=True)
        monitor_thread.start()
        
        logger.info("Scheduler started successfully")
        
    def stop(self):
        """Stop the scheduler and all tasks."""
        if not self.is_running:
            logger.warning("Scheduler is not running")
            return
            
        self.is_running = False
        self.stop_event.set()
        schedule.clear()
        logger.info("Scheduler stopped successfully")
        
    def _setup_task_schedule(self):
        """Setup scheduled tasks."""
        # Clear any existing schedules
        schedule.clear()
        
        # Schedule scraping task every X minutes
        schedule.every(SCRAPE_INTERVAL_MINUTES).minutes.do(self._run_scraper_task)
        
        # Schedule follow tasks throughout the day
        follow_intervals = [
            "09:30", "11:15", "13:45", "16:20", "18:30", "20:10"
        ]
        for time_str in follow_intervals:
            schedule.every().day.at(time_str).do(self._run_follow_task)
            
        # Schedule reply tasks throughout the day
        reply_intervals = [
            "08:45", "10:30", "12:15", "14:00", "15:45", "17:30",
            "19:15", "21:00", "22:45"
        ]
        for time_str in reply_intervals:
            schedule.every().day.at(time_str).do(self._run_reply_task)
            
        # Schedule a daily cleanup task
        schedule.every().day.at("03:00").do(self._run_cleanup_task)
        
        # Schedule a daily metrics task
        schedule.every().day.at("00:05").do(self._log_daily_metrics)
        
        logger.info("Task schedule initialized successfully")
    
    def _scheduler_loop(self):
        """Main loop for running scheduled tasks."""
        while not self.stop_event.is_set():
            schedule.run_pending()
            time.sleep(1)
    
    def _emergency_monitor(self):
        """Monitor for emergency shutdown signal."""
        while not self.stop_event.is_set():
            if os.path.exists(self.emergency_file):
                logger.critical("Emergency shutdown file detected! Stopping all operations...")
                os.remove(self.emergency_file)
                self.stop()
                # Send signal to main process
                os.kill(os.getpid(), signal.SIGTERM)
                break
            time.sleep(5)
    
    def _run_scraper_task(self):
        """Run the scraper task to discover trending posts."""
        if not self.is_running:
            return
            
        logger.info("Starting scraper task...")
        
        async def run_scraper():
            scraper = ThreadsScraper(self.db_manager, headless=self.headless)
            try:
                # Discover trending posts
                posts = await scraper.scrape_trending_posts(limit=30, scroll_count=5)
                
                # Log metrics
                self.system_metric_model.log_metric(
                    metric_name="posts_discovered",
                    metric_value=len(posts),
                    metadata={"timestamp": time.time()}
                )
                
                logger.info(f"Scraper task completed: {len(posts)} posts discovered")
                
            except Exception as e:
                logger.error(f"Error in scraper task: {str(e)}")
            finally:
                await scraper.close()
        
        # Run the async task in a new event loop
        asyncio.run(run_scraper())
        
        # Add some randomness to the interval
        if random.random() < 0.3:  # 30% chance
            jitter = random.randint(-10, 10)
            next_run = schedule.next_run()
            if next_run:
                schedule.cancel_job(self._run_scraper_task)
                next_time = next_run + timedelta(minutes=jitter)
                schedule.every().day.at(next_time.strftime("%H:%M")).do(self._run_scraper_task)
                logger.info(f"Added jitter to scraper task: {jitter} minutes")
    
    def _run_follow_task(self):
        """Run the follow task to increase profile visibility."""
        if not self.is_running:
            return
            
        logger.info("Starting follow task...")
        
        async def run_follow():
            # Get available bot accounts
            accounts = self.bot_account_model.get_available_accounts(
                max_follows=MAX_FOLLOWS_PER_DAY,
                max_replies=MAX_REPLIES_PER_DAY,
                limit=2  # Use at most 2 accounts per run
            )
            
            if not accounts:
                logger.warning("No available bot accounts for follow task")
                return
                
            # Select a random account
            account = random.choice(accounts)
            
            follow_manager = FollowManager(self.db_manager, headless=self.headless)
            try:
                # Determine how many follows to do in this run (5-10)
                max_follows = random.randint(5, 10)
                
                # Follow trending authors
                followed_count = await follow_manager.follow_trending_authors(
                    bot_account_id=account["id"],
                    max_follows=max_follows
                )
                
                # Occasionally unfollow inactive users (20% chance)
                if random.random() < 0.2:
                    logger.info("Running unfollow task for inactive users")
                    unfollowed_count = await follow_manager.unfollow_inactive_users(
                        bot_account_id=account["id"],
                        max_unfollows=3,
                        min_days_before_unfollow=5
                    )
                    logger.info(f"Unfollowed {unfollowed_count} inactive users")
                
                # Log metrics
                self.system_metric_model.log_metric(
                    metric_name="follows_completed",
                    metric_value=followed_count,
                    metadata={
                        "bot_account_id": account["id"],
                        "bot_username": account["username"],
                        "timestamp": time.time()
                    }
                )
                
                logger.info(f"Follow task completed: {followed_count} users followed by {account['username']}")
                
            except Exception as e:
                logger.error(f"Error in follow task: {str(e)}")
            finally:
                await follow_manager.close()
        
        # Run the async task in a new event loop
        asyncio.run(run_follow())
    
    def _run_reply_task(self):
        """Run the reply task to generate engagement."""
        if not self.is_running:
            return
            
        logger.info("Starting reply task...")
        
        async def run_reply():
            # Get available bot accounts
            accounts = self.bot_account_model.get_available_accounts(
                max_follows=MAX_FOLLOWS_PER_DAY,
                max_replies=MAX_REPLIES_PER_DAY,
                limit=3  # Use at most 3 accounts per run
            )
            
            if not accounts:
                logger.warning("No available bot accounts for reply task")
                return
                
            # Select a random account
            account = random.choice(accounts)
            
            reply_manager = ReplyManager(self.db_manager, headless=self.headless)
            try:
                # Determine how many replies to do in this run (3-8)
                max_replies = random.randint(3, 8)
                
                # Reply to trending posts
                reply_count = await reply_manager.reply_to_trending_posts(
                    bot_account_id=account["id"],
                    max_replies=max_replies
                )
                
                # Log metrics
                self.system_metric_model.log_metric(
                    metric_name="replies_posted",
                    metric_value=reply_count,
                    metadata={
                        "bot_account_id": account["id"],
                        "bot_username": account["username"],
                        "timestamp": time.time()
                    }
                )
                
                logger.info(f"Reply task completed: {reply_count} replies posted by {account['username']}")
                
            except Exception as e:
                logger.error(f"Error in reply task: {str(e)}")
            finally:
                await reply_manager.close()
        
        # Run the async task in a new event loop
        asyncio.run(run_reply())
    
    def _run_cleanup_task(self):
        """Run daily cleanup and maintenance tasks."""
        if not self.is_running:
            return
            
        logger.info("Starting daily cleanup task...")
        
        try:
            with self.db_manager as cursor:
                # Reset daily activity counters for all accounts
                cursor.execute('''
                UPDATE bot_accounts
                SET daily_follows = 0,
                    daily_replies = 0,
                    last_reset_date = DATE('now')
                ''')
                
                # Archive old trending posts
                one_week_ago = (datetime.now() - timedelta(days=7)).isoformat()
                cursor.execute('''
                DELETE FROM trending_posts
                WHERE timestamp < ?
                ''', (one_week_ago,))
                
                # Clean up old metrics data
                one_month_ago = (datetime.now() - timedelta(days=30)).isoformat()
                cursor.execute('''
                DELETE FROM system_metrics
                WHERE timestamp < ?
                ''', (one_month_ago,))
                
            logger.info("Daily cleanup task completed successfully")
            
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
    
    def _log_daily_metrics(self):
        """Log daily activity metrics."""
        if not self.is_running:
            return
            
        logger.info("Logging daily metrics...")
        
        try:
            with self.db_manager as cursor:
                # Get total follow count for the day
                cursor.execute('''
                SELECT COUNT(*) FROM follow_activity
                WHERE action_type = 'follow'
                AND status = 'completed'
                AND DATE(timestamp) = DATE('now')
                ''')
                follow_count = cursor.fetchone()[0]
                
                # Get total reply count for the day
                cursor.execute('''
                SELECT COUNT(*) FROM reply_activity
                WHERE status = 'completed'
                AND DATE(timestamp) = DATE('now')
                ''')
                reply_count = cursor.fetchone()[0]
                
                # Get total posts discovered today
                cursor.execute('''
                SELECT COUNT(*) FROM trending_posts
                WHERE DATE(timestamp) = DATE('now')
                ''')
                post_count = cursor.fetchone()[0]
                
                # Get success rates
                cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success
                FROM follow_activity
                WHERE DATE(timestamp) = DATE('now')
                ''')
                follow_result = cursor.fetchone()
                follow_success_rate = 0
                if follow_result and follow_result[0] > 0:
                    follow_success_rate = (follow_result[1] / follow_result[0]) * 100
                
                cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success
                FROM reply_activity
                WHERE DATE(timestamp) = DATE('now')
                ''')
                reply_result = cursor.fetchone()
                reply_success_rate = 0
                if reply_result and reply_result[0] > 0:
                    reply_success_rate = (reply_result[1] / reply_result[0]) * 100
            
            # Log daily metrics
            self.system_metric_model.log_metric(
                metric_name="daily_summary",
                metric_value=1,  # Just a placeholder
                metadata={
                    "date": datetime.now().date().isoformat(),
                    "follows": follow_count,
                    "replies": reply_count,
                    "posts_discovered": post_count,
                    "follow_success_rate": follow_success_rate,
                    "reply_success_rate": reply_success_rate
                }
            )
            
            logger.info("Daily metrics logged successfully")
            
        except Exception as e:
            logger.error(f"Error logging daily metrics: {str(e)}")
    
    def create_emergency_shutdown(self):
        """Create an emergency shutdown file to stop all operations."""
        try:
            with open(self.emergency_file, 'w') as f:
                f.write(f"Emergency shutdown triggered at {datetime.now().isoformat()}")
            logger.warning("Emergency shutdown initiated")
            return True
        except Exception as e:
            logger.error(f"Failed to create emergency shutdown file: {str(e)}")
            return False
            
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of system metrics for the dashboard."""
        try:
            # Get today's metrics
            today_follows = self.system_metric_model.get_metrics("follows_completed", hours=24)
            today_replies = self.system_metric_model.get_metrics("replies_posted", hours=24)
            
            # Calculate totals
            total_follows = sum(metric["metric_value"] for metric in today_follows)
            total_replies = sum(metric["metric_value"] for metric in today_replies)
            
            # Get recent posts
            with self.db_manager as cursor:
                cursor.execute('''
                SELECT COUNT(*) FROM trending_posts
                WHERE timestamp >= datetime('now', '-24 hours')
                ''')
                recent_posts = cursor.fetchone()[0]
                
                # Get active accounts
                cursor.execute('''
                SELECT COUNT(*) FROM bot_accounts
                WHERE account_status = 'active'
                ''')
                active_accounts = cursor.fetchone()[0]
                
                # Get processing status
                cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_processed = 1 THEN 1 ELSE 0 END) as processed
                FROM trending_posts
                WHERE timestamp >= datetime('now', '-24 hours')
                ''')
                processing_result = cursor.fetchone()
                processing_rate = 0
                if processing_result and processing_result[0] > 0:
                    processing_rate = (processing_result[1] / processing_result[0]) * 100
            
            return {
                "active_accounts": active_accounts,
                "follows_today": total_follows,
                "replies_today": total_replies,
                "posts_discovered": recent_posts,
                "processing_rate": processing_rate,
                "last_updated": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting metrics summary: {str(e)}")
            return {
                "error": str(e),
                "last_updated": datetime.now().isoformat()
            } 