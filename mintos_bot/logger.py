"""
Logger Configuration Module
Provides a centralized logging setup for the Mintos Telegram Bot.
"""
import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Optional, Union, Dict

# Default log settings if config can't be imported
DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOG_LEVEL = 'DEBUG'
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
DEFAULT_LOG_BACKUP_COUNT = 5

# Log level mapping
LOG_LEVELS: Dict[str, int] = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with file and console handlers.

    Args:
        name: The name of the logger to create

    Returns:
        logging.Logger: Configured logger instance

    Note:
        The logger will create both a file handler (with rotation)
        and a console handler, both using the same format and level.
        The log file will be created in the 'logs' directory.
    """
    try:
        # Try to import config, but fallback to defaults if it fails
        from .config import LOG_FORMAT, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT
    except ImportError:
        LOG_FORMAT = DEFAULT_LOG_FORMAT
        LOG_LEVEL = DEFAULT_LOG_LEVEL
        LOG_MAX_BYTES = DEFAULT_LOG_MAX_BYTES
        LOG_BACKUP_COUNT = DEFAULT_LOG_BACKUP_COUNT

    # Convert string log level to logging constant
    log_level: int = LOG_LEVELS.get(
        LOG_LEVEL if isinstance(LOG_LEVEL, str) else 'DEBUG',
        logging.DEBUG
    )

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    try:
        # File handler with rotation
        file_handler = RotatingFileHandler(
            filename='logs/mintos_bot.log',
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        file_handler.setLevel(log_level)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        console_handler.setLevel(log_level)

        # Remove existing handlers to prevent duplicate logging
        logger.handlers.clear()
        
        # Prevent propagation to parent loggers to avoid duplicates
        logger.propagate = False

        # Add both handlers
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        # Log logger setup completion with basic info
        logger.debug(
            f"Logger '{name}' initialized with level {LOG_LEVEL}, "
            f"format '{LOG_FORMAT}', rotation size {LOG_MAX_BYTES/1024/1024:.1f}MB"
        )

        return logger

    except Exception as e:
        # Fallback to basic configuration if something goes wrong
        logging.basicConfig(
            level=logging.INFO,
            format=DEFAULT_LOG_FORMAT
        )
        logger = logging.getLogger(name)
        logger.error(f"Failed to setup advanced logging: {e}. Using basic configuration.")
        return logger