import os
import json

# Telegram Bot Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
USERS_FILE = os.path.join('data', 'users.json')

# Application Configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
REQUEST_TIMEOUT = 30  # seconds

# Data Storage
DATA_DIR = "data"
UPDATES_FILE = os.path.join(DATA_DIR, "recovery_updates.json")

# API Configuration
MINTOS_API_BASE = "https://www.mintos.com/webapp/api/marketplace-api/v1"
REQUEST_DELAY = 0.1  # seconds between requests

# Logging Configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'DEBUG'  # Changed from INFO to DEBUG to show scheduling logs
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5