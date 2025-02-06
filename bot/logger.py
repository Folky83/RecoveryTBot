import logging
from logging.handlers import RotatingFileHandler
import os
from .config import LOG_FORMAT, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT

def setup_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)

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