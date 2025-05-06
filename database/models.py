"""
Database models for the Threads Traffic Management System.
"""

import sqlite3
import json
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

from config.settings import DATABASE


class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        """Initialize database manager with the database path."""
        self.db_path = db_path or DATABASE["path"]
        # Create parent directories if they don't exist
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = None
        
    def __enter__(self):
        """Context manager entry point that opens the database connection."""
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        return self.connection.cursor()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point that commits and closes the connection."""
        if self.connection:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
            self.connection.close()
        
    def initialize_database(self):
        """Create all the necessary tables if they don't exist."""
        with self as cursor:
            # Create TrendingPosts table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trending_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT UNIQUE,
                author_username TEXT NOT NULL,
                author_display_name TEXT,
                content TEXT,
                like_count INTEGER DEFAULT 0,
                reply_count INTEGER DEFAULT 0,
                repost_count INTEGER DEFAULT 0,
                post_url TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                is_processed BOOLEAN DEFAULT FALSE
            )
            ''')
            
            # Create BotAccounts table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                last_login DATETIME,
                account_status TEXT DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                proxy_id INTEGER,
                daily_follows INTEGER DEFAULT 0,
                daily_replies INTEGER DEFAULT 0,
                last_reset_date DATE
            )
            ''')
            
            # Create FollowActivity table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS follow_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_account_id INTEGER,
                target_username TEXT NOT NULL,
                action_type TEXT CHECK(action_type IN ('follow', 'unfollow')),
                status TEXT DEFAULT 'pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (bot_account_id) REFERENCES bot_accounts(id)
            )
            ''')
            
            # Create ReplyActivity table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reply_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_account_id INTEGER,
                post_id TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (bot_account_id) REFERENCES bot_accounts(id),
                FOREIGN KEY (post_id) REFERENCES trending_posts(post_id)
            )
            ''')
            
            # Create Proxies table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT,
                password TEXT,
                protocol TEXT DEFAULT 'http',
                country TEXT,
                last_used DATETIME,
                status TEXT DEFAULT 'active'
            )
            ''')
            
            # Create SystemMetrics table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                metadata TEXT
            )
            ''')


class TrendingPost:
    """Model for trending posts."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
    def save(self, post_data: Dict[str, Any]) -> int:
        """Save a trending post to the database."""
        with self.db_manager as cursor:
            # Convert metadata dict to JSON string if present
            if 'metadata' in post_data and isinstance(post_data['metadata'], dict):
                post_data['metadata'] = json.dumps(post_data['metadata'])
                
            # Insert or update the post
            cursor.execute('''
            INSERT OR REPLACE INTO trending_posts 
            (post_id, author_username, author_display_name, content, 
            like_count, reply_count, repost_count, post_url, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                post_data.get('post_id', ''),
                post_data.get('author_username', ''),
                post_data.get('author_display_name', ''),
                post_data.get('content', ''),
                post_data.get('like_count', 0),
                post_data.get('reply_count', 0),
                post_data.get('repost_count', 0),
                post_data.get('post_url', ''),
                post_data.get('metadata', '{}')
            ))
            return cursor.lastrowid
            
    def get_by_id(self, post_id: str) -> Dict[str, Any]:
        """Get post by post_id."""
        with self.db_manager as cursor:
            cursor.execute('SELECT * FROM trending_posts WHERE post_id = ?', (post_id,))
            post = cursor.fetchone()
            if post:
                post_dict = dict(post)
                # Parse JSON metadata if present
                if post_dict.get('metadata'):
                    try:
                        post_dict['metadata'] = json.loads(post_dict['metadata'])
                    except json.JSONDecodeError:
                        post_dict['metadata'] = {}
                return post_dict
            return {}
            
    def get_unprocessed_posts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get unprocessed trending posts."""
        with self.db_manager as cursor:
            cursor.execute('''
            SELECT * FROM trending_posts 
            WHERE is_processed = FALSE
            ORDER BY like_count DESC, reply_count DESC
            LIMIT ?
            ''', (limit,))
            
            posts = cursor.fetchall()
            result = []
            for post in posts:
                post_dict = dict(post)
                # Parse JSON metadata if present
                if post_dict.get('metadata'):
                    try:
                        post_dict['metadata'] = json.loads(post_dict['metadata'])
                    except json.JSONDecodeError:
                        post_dict['metadata'] = {}
                result.append(post_dict)
            return result
            
    def mark_as_processed(self, post_id: str) -> bool:
        """Mark a post as processed."""
        with self.db_manager as cursor:
            cursor.execute('''
            UPDATE trending_posts
            SET is_processed = TRUE
            WHERE post_id = ?
            ''', (post_id,))
            return cursor.rowcount > 0


class BotAccount:
    """Model for bot accounts."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
    def add_account(self, username: str, password: str, proxy_id: Optional[int] = None) -> int:
        """Add a new bot account."""
        with self.db_manager as cursor:
            cursor.execute('''
            INSERT INTO bot_accounts (username, password, proxy_id, last_reset_date)
            VALUES (?, ?, ?, DATE('now'))
            ''', (username, password, proxy_id))
            return cursor.lastrowid
            
    def get_account(self, account_id: int) -> Dict[str, Any]:
        """Get account by ID."""
        with self.db_manager as cursor:
            cursor.execute('SELECT * FROM bot_accounts WHERE id = ?', (account_id,))
            account = cursor.fetchone()
            if account:
                return dict(account)
            return {}
            
    def get_available_accounts(self, 
                              max_follows: int, 
                              max_replies: int,
                              limit: int = 5) -> List[Dict[str, Any]]:
        """Get accounts that haven't reached their daily limits."""
        today = datetime.date.today().isoformat()
        with self.db_manager as cursor:
            cursor.execute('''
            SELECT * FROM bot_accounts
            WHERE account_status = 'active'
            AND (last_reset_date != DATE('now') OR 
                 (daily_follows < ? AND daily_replies < ?))
            LIMIT ?
            ''', (max_follows, max_replies, limit))
            
            accounts = cursor.fetchall()
            return [dict(account) for account in accounts]
            
    def update_activity_count(self, account_id: int, 
                             activity_type: str, 
                             count: int = 1) -> bool:
        """Update follow or reply count for a bot account."""
        today = datetime.date.today().isoformat()
        with self.db_manager as cursor:
            # Reset counts if it's a new day
            cursor.execute('''
            UPDATE bot_accounts
            SET daily_follows = CASE WHEN last_reset_date != DATE('now') THEN 0 ELSE daily_follows END,
                daily_replies = CASE WHEN last_reset_date != DATE('now') THEN 0 ELSE daily_replies END,
                last_reset_date = DATE('now')
            WHERE id = ?
            ''', (account_id,))
            
            # Update the appropriate counter
            if activity_type == 'follow':
                cursor.execute('''
                UPDATE bot_accounts
                SET daily_follows = daily_follows + ?
                WHERE id = ?
                ''', (count, account_id))
            elif activity_type == 'reply':
                cursor.execute('''
                UPDATE bot_accounts
                SET daily_replies = daily_replies + ?
                WHERE id = ?
                ''', (count, account_id))
                
            return cursor.rowcount > 0
            
    def update_login_time(self, account_id: int) -> bool:
        """Update the last login time for a bot account."""
        with self.db_manager as cursor:
            cursor.execute('''
            UPDATE bot_accounts
            SET last_login = CURRENT_TIMESTAMP
            WHERE id = ?
            ''', (account_id,))
            return cursor.rowcount > 0
            
    def update_status(self, account_id: int, status: str) -> bool:
        """Update the status of a bot account."""
        with self.db_manager as cursor:
            cursor.execute('''
            UPDATE bot_accounts
            SET account_status = ?
            WHERE id = ?
            ''', (status, account_id))
            return cursor.rowcount > 0


class FollowActivity:
    """Model for follow activities."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
    def add_activity(self, bot_account_id: int, 
                    target_username: str, 
                    action_type: str = 'follow') -> int:
        """Add a new follow/unfollow activity."""
        with self.db_manager as cursor:
            cursor.execute('''
            INSERT INTO follow_activity 
            (bot_account_id, target_username, action_type, status)
            VALUES (?, ?, ?, 'pending')
            ''', (bot_account_id, target_username, action_type))
            return cursor.lastrowid
            
    def update_status(self, activity_id: int, status: str) -> bool:
        """Update the status of a follow activity."""
        with self.db_manager as cursor:
            cursor.execute('''
            UPDATE follow_activity
            SET status = ?
            WHERE id = ?
            ''', (status, activity_id))
            return cursor.rowcount > 0
            
    def get_pending_activities(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get pending follow activities."""
        with self.db_manager as cursor:
            cursor.execute('''
            SELECT fa.*, ba.username as bot_username 
            FROM follow_activity fa
            JOIN bot_accounts ba ON fa.bot_account_id = ba.id
            WHERE fa.status = 'pending'
            ORDER BY fa.timestamp ASC
            LIMIT ?
            ''', (limit,))
            
            activities = cursor.fetchall()
            return [dict(activity) for activity in activities]


class ReplyActivity:
    """Model for reply activities."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
    def add_activity(self, bot_account_id: int, 
                    post_id: str, 
                    content: str) -> int:
        """Add a new reply activity."""
        with self.db_manager as cursor:
            cursor.execute('''
            INSERT INTO reply_activity 
            (bot_account_id, post_id, content, status)
            VALUES (?, ?, ?, 'pending')
            ''', (bot_account_id, post_id, content))
            return cursor.lastrowid
            
    def update_status(self, activity_id: int, status: str) -> bool:
        """Update the status of a reply activity."""
        with self.db_manager as cursor:
            cursor.execute('''
            UPDATE reply_activity
            SET status = ?
            WHERE id = ?
            ''', (status, activity_id))
            return cursor.rowcount > 0
            
    def get_pending_activities(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get pending reply activities."""
        with self.db_manager as cursor:
            cursor.execute('''
            SELECT ra.*, ba.username as bot_username, tp.post_url
            FROM reply_activity ra
            JOIN bot_accounts ba ON ra.bot_account_id = ba.id
            JOIN trending_posts tp ON ra.post_id = tp.post_id
            WHERE ra.status = 'pending'
            ORDER BY ra.timestamp ASC
            LIMIT ?
            ''', (limit,))
            
            activities = cursor.fetchall()
            return [dict(activity) for activity in activities]


class Proxy:
    """Model for proxies."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
    def add_proxy(self, ip_address: str, port: int, 
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 protocol: str = 'http',
                 country: Optional[str] = None) -> int:
        """Add a new proxy."""
        with self.db_manager as cursor:
            cursor.execute('''
            INSERT INTO proxies 
            (ip_address, port, username, password, protocol, country)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (ip_address, port, username, password, protocol, country))
            return cursor.lastrowid
            
    def get_available_proxy(self, strategy: str = 'round_robin') -> Dict[str, Any]:
        """Get an available proxy based on the strategy."""
        with self.db_manager as cursor:
            if strategy == 'round_robin':
                cursor.execute('''
                SELECT * FROM proxies
                WHERE status = 'active'
                ORDER BY last_used ASC NULLS FIRST
                LIMIT 1
                ''')
            else:  # random
                cursor.execute('''
                SELECT * FROM proxies
                WHERE status = 'active'
                ORDER BY RANDOM()
                LIMIT 1
                ''')
                
            proxy = cursor.fetchone()
            if proxy:
                proxy_dict = dict(proxy)
                # Update last used time
                cursor.execute('''
                UPDATE proxies
                SET last_used = CURRENT_TIMESTAMP
                WHERE id = ?
                ''', (proxy_dict['id'],))
                return proxy_dict
            return {}
            
    def update_status(self, proxy_id: int, status: str) -> bool:
        """Update the status of a proxy."""
        with self.db_manager as cursor:
            cursor.execute('''
            UPDATE proxies
            SET status = ?
            WHERE id = ?
            ''', (status, proxy_id))
            return cursor.rowcount > 0


class SystemMetric:
    """Model for system metrics."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
    def log_metric(self, metric_name: str, 
                  metric_value: Union[int, float], 
                  metadata: Optional[Dict[str, Any]] = None) -> int:
        """Log a system metric."""
        with self.db_manager as cursor:
            metadata_json = json.dumps(metadata) if metadata else None
            cursor.execute('''
            INSERT INTO system_metrics 
            (metric_name, metric_value, metadata)
            VALUES (?, ?, ?)
            ''', (metric_name, metric_value, metadata_json))
            return cursor.lastrowid
            
    def get_metrics(self, metric_name: str, 
                   limit: int = 100, 
                   hours: int = 24) -> List[Dict[str, Any]]:
        """Get system metrics for a specific name within a time range."""
        with self.db_manager as cursor:
            cursor.execute('''
            SELECT * FROM system_metrics
            WHERE metric_name = ?
            AND timestamp >= datetime('now', ? || ' hours')
            ORDER BY timestamp DESC
            LIMIT ?
            ''', (metric_name, -hours, limit))
            
            metrics = cursor.fetchall()
            result = []
            for metric in metrics:
                metric_dict = dict(metric)
                # Parse JSON metadata if present
                if metric_dict.get('metadata'):
                    try:
                        metric_dict['metadata'] = json.loads(metric_dict['metadata'])
                    except json.JSONDecodeError:
                        metric_dict['metadata'] = {}
                result.append(metric_dict)
            return result 