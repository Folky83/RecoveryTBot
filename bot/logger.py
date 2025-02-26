import logging
from logging.handlers import RotatingFileHandler
import os

# Default log settings if config can't be imported
DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOG_LEVEL = 'DEBUG'
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
DEFAULT_LOG_BACKUP_COUNT = 5

def setup_logger(name):
    try:
        # Try to import config, but fallback to defaults if it fails
        from .config import LOG_FORMAT, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT
    except ImportError:
        LOG_FORMAT = DEFAULT_LOG_FORMAT
        LOG_LEVEL = DEFAULT_LOG_LEVEL
        LOG_MAX_BYTES = DEFAULT_LOG_MAX_BYTES
        LOG_BACKUP_COUNT = DEFAULT_LOG_BACKUP_COUNT
    
    log_level = logging.getLevelName(LOG_LEVEL) if isinstance(LOG_LEVEL, str) else LOG_LEVEL
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # File handler with more detailed configuration
    file_handler = RotatingFileHandler(
        'logs/mintos_bot.log',
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    file_handler.setLevel(LOG_LEVEL)

    # Console handler with more detailed output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    console_handler.setLevel(LOG_LEVEL)

    # Remove existing handlers to prevent duplicate logging
    logger.handlers.clear()

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Log logger setup completion
    logger.debug(f"Logger '{name}' initialized with level {LOG_LEVEL}")

    return logger