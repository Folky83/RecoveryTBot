"""
Base manager class providing common functionality
Reduces code duplication across manager classes.
"""
import os
import json
import logging
from typing import Any, Dict, List, Optional
from .utils import FileBackupManager
from .constants import DATA_DIR

logger = logging.getLogger(__name__)

class BaseManager:
    """Base class for all manager classes"""
    
    def __init__(self, data_file: str, backup_enabled: bool = True):
        """Initialize base manager
        
        Args:
            data_file: Path to the main data file
            backup_enabled: Whether to enable automatic backups
        """
        self.data_file = data_file
        self.backup_file = f"{data_file}.bak" if backup_enabled else None
        self.ensure_data_directory()
    
    def ensure_data_directory(self) -> None:
        """Ensure data directory exists"""
        os.makedirs(DATA_DIR, exist_ok=True)
    
    def load_data(self, default: Any = None) -> Any:
        """Load data from file with backup fallback"""
        return FileBackupManager.safe_json_load(self.data_file, default)
    
    def save_data(self, data: Any) -> bool:
        """Save data to file with backup"""
        return FileBackupManager.safe_json_save(
            self.data_file, 
            data, 
            create_backup=self.backup_file is not None
        )
    
    def get_file_age(self) -> float:
        """Get age of data file in seconds"""
        try:
            if os.path.exists(self.data_file):
                import time
                return time.time() - os.path.getmtime(self.data_file)
            return float('inf')
        except Exception as e:
            logger.error(f"Error getting file age: {e}")
            return float('inf')