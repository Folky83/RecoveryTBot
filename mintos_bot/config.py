import os
import json

# Telegram Bot Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')  # Remove default value to ensure proper error handling
USERS_FILE = os.path.join('data', 'users.json')

# Application Configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
REQUEST_TIMEOUT = 30  # seconds

# Cache Configuration
CACHE_MAX_AGE_MINUTES = 360  # 6 hours - threshold to consider cache as old
CACHE_REFRESH_THRESHOLD_MINUTES = 120  # 2 hours - threshold to show refresh button

# Data Storage
DATA_DIR = "data"
UPDATES_FILE = os.path.join(DATA_DIR, "recovery_updates.json")
CAMPAIGNS_FILE = os.path.join(DATA_DIR, "campaigns.json")
DOCUMENTS_FILE = os.path.join(DATA_DIR, "documents.json")
DOCUMENTS_CACHE_FILE = os.path.join(DATA_DIR, "documents_cache.json")
SENT_DOCUMENTS_FILE = os.path.join(DATA_DIR, "sent_documents.json")
BACKUP_SENT_DOCUMENTS_FILE = os.path.join(DATA_DIR, "sent_documents.json.bak")

# API Configuration
MINTOS_API_BASE = "https://www.mintos.com/webapp/api/marketplace-api/v1"
MINTOS_CAMPAIGNS_URL = "https://www.mintos.com/webapp/api/en/webapp-api/user/campaigns"
REQUEST_DELAY = 0.1  # seconds between requests

# Proxy Configuration
PROXY_HOST = os.getenv('PROXY_HOST', 'geo.iproyal.com:12321')
PROXY_AUTH = os.getenv('PROXY_AUTH', '9E6VfuiSZHtXLtt7:CUDTgmiajB4wOCrv_streaming-1')
USE_PROXY = os.getenv('USE_PROXY', 'true').lower() == 'true'

# Document Scraper Configuration
DOCUMENT_SCRAPE_INTERVAL_HOURS = 24  # Scrape documents once a day
DOCUMENT_TYPES = {
    'presentation': 'Presentation',
    'financials': 'Financials',
    'loan_agreement': 'Loan Agreement'
}

# Logging Configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'DEBUG'  # Changed from INFO to DEBUG to show scheduling logs
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5