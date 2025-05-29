"""
Utility functions for the Mintos Telegram Bot
Provides common helper functions and safe operations.
"""
import hashlib
import json
import logging
import os
import shutil
from typing import Any, Optional, Union
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

logger = logging.getLogger(__name__)

def create_unique_id(*args) -> str:
    """Create a unique identifier from multiple arguments"""
    hash_content = "_".join(str(arg) for arg in args)
    return hashlib.md5(hash_content.encode()).hexdigest()

def safe_get_text(element: Optional[Union[Tag, NavigableString]], default: str = "") -> str:
    """Safely extract text from BeautifulSoup element"""
    if element is None:
        return default
    if isinstance(element, NavigableString):
        return str(element).strip()
    if hasattr(element, 'get_text'):
        return element.get_text(strip=True)
    return str(element).strip()

def safe_get_attribute(element: Optional[Union[Tag, NavigableString]], 
                      attr: str, default: str = "") -> str:
    """Safely get attribute from BeautifulSoup element"""
    if element is None:
        return default
    if isinstance(element, Tag) and hasattr(element, 'get'):
        value = element.get(attr, default)
        return str(value) if value is not None else default
    return default

def safe_find(soup: BeautifulSoup, *args, **kwargs) -> Optional[Tag]:
    """Safely find element in BeautifulSoup"""
    try:
        result = soup.find(*args, **kwargs)
        return result if isinstance(result, Tag) else None
    except Exception as e:
        logger.warning(f"Error in safe_find: {e}")
        return None

def safe_find_all(soup: BeautifulSoup, *args, **kwargs) -> list:
    """Safely find all elements in BeautifulSoup"""
    try:
        return soup.find_all(*args, **kwargs)
    except Exception as e:
        logger.warning(f"Error in safe_find_all: {e}")
        return []

class FileBackupManager:
    """Manages file operations with backup support"""
    
    @staticmethod
    def safe_json_load(file_path: str, default: Any = None) -> Any:
        """Safely load JSON file with backup fallback"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load {file_path}, trying backup: {e}")
            backup_path = f"{file_path}.bak"
            try:
                if os.path.exists(backup_path):
                    with open(backup_path, 'r') as f:
                        data = json.load(f)
                    logger.info(f"Successfully restored from backup: {backup_path}")
                    return data
            except Exception as backup_e:
                logger.error(f"Failed to load backup {backup_path}: {backup_e}")
        
        return default
    
    @staticmethod
    def safe_json_save(file_path: str, data: Any, create_backup: bool = True) -> bool:
        """Safely save JSON file with backup"""
        try:
            # Create backup if requested and file exists
            if create_backup and os.path.exists(file_path):
                backup_path = f"{file_path}.bak"
                shutil.copy2(file_path, backup_path)
            
            # Save the data
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
            
            logger.debug(f"Successfully saved data to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save data to {file_path}: {e}")
            return False

def normalize_lender_id(lender_id: Any) -> Optional[int]:
    """Normalize lender ID to integer"""
    if lender_id is None:
        return None
    try:
        return int(lender_id)
    except (ValueError, TypeError):
        logger.warning(f"Invalid lender_id format: {lender_id}")
        return None

def format_currency(amount: Optional[float], currency: str = "€") -> str:
    """Format currency amount"""
    if amount is None:
        return "N/A"
    try:
        return f"{currency}{amount:,.2f}"
    except (TypeError, ValueError):
        return "N/A"

def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to specified length"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."