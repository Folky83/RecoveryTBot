"""
Utility functions for the Mintos Telegram Bot
Provides common functionality and type-safe operations.
"""
import json
import os
import time
import shutil
import logging
from typing import Dict, List, Any, Optional, Union
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

logger = logging.getLogger(__name__)

class SafeElementHandler:
    """Provides type-safe operations for BeautifulSoup elements"""
    
    @staticmethod
    def safe_get_attribute(element: Union[Tag, NavigableString, None], attr_name: str, default: str = "") -> str:
        """Safely get an attribute from a BeautifulSoup element"""
        if element is None or isinstance(element, NavigableString):
            return default
        
        if not isinstance(element, Tag):
            return default
            
        attr_value = element.get(attr_name, default)
        if isinstance(attr_value, list):
            return " ".join(str(v) for v in attr_value) if attr_value else default
        
        return str(attr_value) if attr_value is not None else default
    
    @staticmethod
    def safe_get_text(element: Union[Tag, NavigableString, None], default: str = "") -> str:
        """Safely get text content from a BeautifulSoup element"""
        if element is None:
            return default
        
        if isinstance(element, NavigableString):
            return str(element).strip()
        
        if isinstance(element, Tag):
            return element.get_text().strip()
        
        return default
    
    @staticmethod
    def safe_find_all(element: Union[Tag, NavigableString, None], *args, **kwargs) -> List[Tag]:
        """Safely find all matching elements"""
        if element is None or isinstance(element, NavigableString):
            return []
        
        if not isinstance(element, Tag):
            return []
        
        try:
            results = element.find_all(*args, **kwargs)
            return [r for r in results if isinstance(r, Tag)]
        except Exception as e:
            logger.debug(f"Error in safe_find_all: {e}")
            return []
    
    @staticmethod
    def is_pdf_link(href: Optional[str]) -> bool:
        """Check if href points to a PDF file"""
        if not href or not isinstance(href, str):
            return False
        return href.lower().endswith('.pdf')
    
    @staticmethod
    def normalize_url(href: str, base_url: str = "https://www.mintos.com") -> str:
        """Normalize a URL to ensure it's absolute"""
        if not href:
            return ""
        
        if href.startswith(('http://', 'https://')):
            return href
        
        if href.startswith('/'):
            return f"{base_url}{href}"
        
        return f"{base_url}/{href}"

class FileBackupManager:
    """Manages file operations with automatic backup creation"""
    
    @staticmethod
    def create_backup(file_path: str) -> bool:
        """Create a backup of the specified file"""
        if not os.path.exists(file_path):
            return False
        
        backup_path = f"{file_path}.bak"
        try:
            shutil.copy2(file_path, backup_path)
            return True
        except Exception as e:
            logger.error(f"Failed to create backup of {file_path}: {e}")
            return False
    
    @staticmethod
    def restore_from_backup(file_path: str) -> bool:
        """Restore a file from its backup"""
        backup_path = f"{file_path}.bak"
        if not os.path.exists(backup_path):
            return False
        
        try:
            shutil.copy2(backup_path, file_path)
            return True
        except Exception as e:
            logger.error(f"Failed to restore {file_path} from backup: {e}")
            return False
    
    @staticmethod
    def safe_json_load(file_path: str, default: Any = None) -> Any:
        """Safely load JSON data with backup fallback"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error loading {file_path}: {e}")
            
            # Try backup
            backup_path = f"{file_path}.bak"
            if os.path.exists(backup_path):
                try:
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        logger.info(f"Loaded data from backup: {backup_path}")
                        
                        # Restore main file from backup
                        shutil.copy2(backup_path, file_path)
                        return data
                except (json.JSONDecodeError, IOError) as backup_e:
                    logger.error(f"Backup file also corrupted: {backup_e}")
        
        return default
    
    @staticmethod
    def safe_json_save(file_path: str, data: Any, create_backup: bool = True) -> bool:
        """Safely save JSON data with backup"""
        try:
            # Create backup first
            if create_backup and os.path.exists(file_path):
                FileBackupManager.create_backup(file_path)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save data
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            logger.error(f"Failed to save {file_path}: {e}")
            return False

def create_unique_id(*components: Any) -> str:
    """Create a unique identifier from multiple components"""
    import hashlib
    content = "_".join(str(c) for c in components if c is not None)
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def format_timestamp(timestamp: Optional[float] = None) -> str:
    """Format timestamp to readable string"""
    if timestamp is None:
        timestamp = time.time()
    
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

def get_current_date() -> str:
    """Get current date in YYYY-MM-DD format"""
    return time.strftime("%Y-%m-%d")

def is_same_day(timestamp1: float, timestamp2: float) -> bool:
    """Check if two timestamps are on the same day"""
    date1 = time.strftime("%Y-%m-%d", time.localtime(timestamp1))
    date2 = time.strftime("%Y-%m-%d", time.localtime(timestamp2))
    return date1 == date2