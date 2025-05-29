"""
Custom exceptions for the Mintos Telegram Bot
Provides specific error types for better error handling and debugging.
"""

class MintosAPIError(Exception):
    """Raised when Mintos API requests fail"""
    pass

class DataProcessingError(Exception):
    """Raised when data processing operations fail"""
    pass

class DocumentScrapingError(Exception):
    """Raised when document scraping operations fail"""
    pass

class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing"""
    pass

class TelegramBotError(Exception):
    """Raised when Telegram bot operations fail"""
    pass