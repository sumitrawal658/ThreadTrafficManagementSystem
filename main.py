#!/usr/bin/env python3

import os
import sys
import logging
import time
import argparse
import threading
import signal
from pathlib import Path
import asyncio
import subprocess

from database.models import DatabaseManager
from database.init_db import init_database
from orchestration.scheduler import Scheduler
from config.settings import DATABASE, DASHBOARD


def setup_logging(log_level):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "threads_traffic.log"

    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )


def signal_handler(sig, frame):
    logging.info("Shutdown signal received, stopping system...")

    if scheduler and scheduler.is_running:
        scheduler.stop()

    logging.info("System shutdown complete")
    sys.exit(0)


def start_dashboard():
    dashboard_process = subprocess.Popen(
        ["streamlit", "run", "dashboard.py", "--server.port", str(DASHBOARD.get("port", 8501))]
    )
    return dashboard_process


def parse_args():
    parser = argparse.ArgumentParser(description="Threads Traffic Management System")

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode"
    )

    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Disable the dashboard"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level"
    )

    parser.add_argument(
        "--init-db-only",
        action="store_true",
        help="Initialize the database and exit"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_level)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        init_database()
        logging.info("Database initialized successfully")

        if args.init_db_only:
            logging.info("Database initialization completed, exiting as requested")
            sys.exit(0)
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")
        sys.exit(1)

    db_manager = DatabaseManager()
    scheduler = Scheduler(db_manager, headless=args.headless)

    dashboard_process = None
    if not args.no_dashboard:
        try:
            dashboard_process = start_dashboard()
            logging.info(f"Dashboard started on port {DASHBOARD.get('port', 8501)}")
        except Exception as e:
            logging.error(f"Failed to start dashboard: {e}")

    try:
        scheduler.start()
        logging.info("Scheduler started successfully")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received, shutting down...")

    except Exception as e:
        logging.error(f"Error in main thread: {e}")

    finally:
        if scheduler.is_running:
            scheduler.stop()

        if dashboard_process:
            dashboard_process.terminate()