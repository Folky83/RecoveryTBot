"""
Constants and configuration for the Mintos Telegram Bot
Centralizes all configuration values for better maintainability.
"""
import os
from aiohttp import ClientTimeout

# Application Configuration
APP_NAME = "Mintos Telegram Bot"
DATA_DIR = "data"
ATTACHED_ASSETS_DIR = "attached_assets"

# File Paths
UPDATES_FILE = os.path.join(DATA_DIR, 'updates_cache.json')
CAMPAIGNS_FILE = os.path.join(DATA_DIR, 'campaigns_cache.json')
DOCUMENTS_CACHE_FILE = os.path.join(DATA_DIR, 'documents_cache.json')

# Backup Files
SENT_UPDATES_FILE = os.path.join(DATA_DIR, 'sent_updates.json')
SENT_UPDATES_BACKUP = os.path.join(DATA_DIR, 'sent_updates.json.bak')
SENT_CAMPAIGNS_FILE = os.path.join(DATA_DIR, 'sent_campaigns.json')
SENT_CAMPAIGNS_BACKUP = os.path.join(DATA_DIR, 'sent_campaigns.json.bak')
SENT_DOCUMENTS_FILE = os.path.join(DATA_DIR, 'sent_documents.json')
SENT_DOCUMENTS_BACKUP = os.path.join(DATA_DIR, 'sent_documents.json.bak')

# CSV Files - fallback paths if package data not found
COMPANY_NAMES_CSV = os.path.join(ATTACHED_ASSETS_DIR, 'lo_names.csv')
COMPANY_PAGES_CSV = os.path.join(ATTACHED_ASSETS_DIR, 'company_pages.csv')

# Process Management
LOCK_FILE = 'bot.lock'
STREAMLIT_PORT = 5000

# Timeouts (in seconds)
STARTUP_TIMEOUT = 60
BOT_STARTUP_TIMEOUT = 30
CLEANUP_WAIT = 5
PROCESS_KILL_WAIT = 3
HTTP_TIMEOUT = 10
HTTP_RETRY_DELAY = 1

# HTTP Configuration
MAX_HTTP_RETRIES = 3
HTTP_CLIENT_TIMEOUT = ClientTimeout(total=HTTP_TIMEOUT)
DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# Cache Configuration
DEFAULT_CACHE_TTL = 3600  # 1 hour in seconds
DOCUMENT_CACHE_TTL = 1800  # 30 minutes for documents

# Document Types
DOCUMENT_TYPES = ['presentation', 'financials', 'loan_agreement']

# Logging Configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'

# Rate Limiting
MAX_CONCURRENT_REQUESTS = 5
REQUEST_DELAY = 0.5  # seconds between requests

# Environment Variables
TELEGRAM_BOT_TOKEN_VAR = 'TELEGRAM_BOT_TOKEN'

# Error Messages
ERROR_MISSING_TOKEN = f"{TELEGRAM_BOT_TOKEN_VAR} environment variable is not set"
ERROR_INVALID_LENDER_ID = "Invalid lender ID format"
ERROR_DATA_LOADING = "Error loading data from file"
ERROR_DATA_SAVING = "Error saving data to file"