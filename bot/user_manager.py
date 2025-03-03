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
            user_list = list(self.users)
            with open(USERS_FILE, 'w') as f:
                json.dump(user_list, f)
            logger.info(f"Users saved successfully: {user_list}")
            
            # Verify the file was written correctly
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, 'r') as f:
                    saved_data = f.read().strip()
                    logger.info(f"Verification - users.json contains: {saved_data}")
            else:
                logger.error(f"Verification failed - {USERS_FILE} does not exist after save")
        except Exception as e:
            logger.error(f"Error saving users: {e}", exc_info=True)

    def add_user(self, chat_id):
        self.users.add(str(chat_id))
        self.save_users()
        logger.info(f"Added new user: {chat_id}")

    def remove_user(self, chat_id):
        """Remove a user from the saved users list"""
        chat_id = str(chat_id)
        if chat_id in self.users:
            self.users.remove(chat_id)
            self.save_users()
            logger.info(f"Removed user: {chat_id}")

    def get_all_users(self):
        return list(self.users)

    def has_user(self, chat_id):
        """Check if a user exists in the saved users list"""
        return str(chat_id) in self.users