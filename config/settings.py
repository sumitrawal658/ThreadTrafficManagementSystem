"""
Configuration settings for the Threads Traffic Management System.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# Database
DATABASE = {
    "path": os.getenv("DATABASE_PATH", str(BASE_DIR / "database" / "threads_traffic.db"))
}

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Threads Account Credentials
MAIN_ACCOUNT = {
    "username": os.getenv("MAIN_ACCOUNT_USERNAME", ""),
    "password": os.getenv("MAIN_ACCOUNT_PASSWORD", "")
}

# Bot Accounts
BOT_ACCOUNTS = []
i = 1
while True:
    username = os.getenv(f"BOT_ACCOUNT_{i}_USERNAME")
    password = os.getenv(f"BOT_ACCOUNT_{i}_PASSWORD")
    if not username or not password:
        break
    BOT_ACCOUNTS.append({
        "username": username,
        "password": password
    })
    i += 1

# Dolphin Anty Configuration
DOLPHIN_ANTY = {
    "api_key": os.getenv("DOLPHIN_ANTY_API_KEY", ""),
    "api_url": os.getenv("DOLPHIN_ANTY_API_URL", "https://anty-api.com")
}

# System Configuration
MAX_FOLLOWS_PER_DAY = int(os.getenv("MAX_FOLLOWS_PER_DAY", 50))
MAX_REPLIES_PER_DAY = int(os.getenv("MAX_REPLIES_PER_DAY", 100))
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", 60))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# AI Configuration
AI_CONFIG = {
    "model": os.getenv("DEFAULT_AI_MODEL", "gpt-4"),
    "temperature": float(os.getenv("AI_TEMPERATURE", 0.7)),
    "max_tokens": int(os.getenv("AI_MAX_TOKENS", 150))
}

# Safety Settings
SAFETY = {
    "browser_cooldown_min_seconds": float(os.getenv("BROWSER_COOLDOWN_MIN_SECONDS", 3)),
    "browser_cooldown_max_seconds": float(os.getenv("BROWSER_COOLDOWN_MAX_SECONDS", 8)),
    "typing_speed_min_cps": float(os.getenv("TYPING_SPEED_MIN_CPS", 5)),
    "typing_speed_max_cps": float(os.getenv("TYPING_SPEED_MAX_CPS", 12)),
}

# Proxy Configuration
PROXY = {
    "use_proxies": os.getenv("USE_PROXIES", "true").lower() == "true",
    "rotation_strategy": os.getenv("PROXY_ROTATION_STRATEGY", "round_robin")
}

# Threads URLs
THREADS_URLS = {
    "base_url": "https://www.threads.net",
    "login_url": "https://www.threads.net/login",
    "explore_url": "https://www.threads.net/explore",
    "user_profile": lambda username: f"https://www.threads.net/@{username}"
}

# Monitoring
DASHBOARD = {
    "port": int(os.getenv("DASHBOARD_PORT", 8501)),
    "update_interval_seconds": int(os.getenv("DASHBOARD_UPDATE_INTERVAL", 60))
} 