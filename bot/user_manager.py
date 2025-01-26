import json
import os
from .logger import setup_logger
from .config import USERS_FILE, DATA_DIR

logger = setup_logger(__name__)

class UserManager:
    def __init__(self):
        self.users = set()
        self._ensure_data_directory()
        self.load_users()

    def _ensure_data_directory(self):
        """Ensure the data directory exists"""
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(USERS_FILE):
            self.save_users()  # Create an empty users file if it doesn't exist
        logger.info(f"Data directory checked: {DATA_DIR}")

    def load_users(self):
        try:
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, 'r') as f:
                    self.users = set(json.load(f))
            logger.info(f"Loaded {len(self.users)} users")
        except Exception as e:
            logger.error(f"Error loading users: {e}")
            self.users = set()  # Reset to empty set on error

    def save_users(self):
        try:
            with open(USERS_FILE, 'w') as f:
                json.dump(list(self.users), f)
            logger.info("Users saved successfully")
        except Exception as e:
            logger.error(f"Error saving users: {e}")

    def add_user(self, chat_id):
        self.users.add(chat_id)
        self.save_users()
        logger.info(f"Added new user: {chat_id}")

    def get_all_users(self):
        return list(self.users)