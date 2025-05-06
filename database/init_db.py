#!/usr/bin/env python3
"""
Initialize the database for the Threads Traffic Management System.
"""

import sys
import os
import logging
from pathlib import Path

# Add parent directory to path so we can import from other modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import DatabaseManager
from config.settings import DATABASE, BOT_ACCOUNTS


def init_database():
    """Initialize the database with tables and seed data."""
    logging.info("Initializing database...")
    
    db_manager = DatabaseManager()
    
    # Create tables
    db_manager.initialize_database()
    
    # If there are any bot accounts in the settings, add them to the database
    if BOT_ACCOUNTS:
        from database.models import BotAccount
        bot_account_model = BotAccount(db_manager)
        for account in BOT_ACCOUNTS:
            try:
                bot_account_model.add_account(
                    username=account["username"],
                    password=account["password"]
                )
                logging.info(f"Added bot account: {account['username']}")
            except Exception as e:
                logging.error(f"Failed to add bot account {account['username']}: {e}")
    
    logging.info("Database initialization complete!")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        init_database()
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")
        sys.exit(1) 