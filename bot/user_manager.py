import json
import os
from .logger import setup_logger
from .config import USERS_FILE, DATA_DIR

logger = setup_logger(__name__)

class UserManager:
    def __init__(self):
        self.users = {}  # Changed from set to dict to store username with chat_id
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
                    data = json.load(f)
                    # Handle both old format (list of chat_ids) and new format (dict with usernames)
                    if isinstance(data, list):
                        # Convert old format to new format
                        self.users = {chat_id: None for chat_id in data}
                        logger.info(f"Converted {len(data)} users from old format to new format")
                    else:
                        self.users = data
                logger.info(f"Loaded {len(self.users)} users")
            else:
                self.users = {}
        except Exception as e:
            logger.error(f"Error loading users: {e}")
            self.users = {}  # Reset to empty dict on error

    def save_users(self):
        try:
            with open(USERS_FILE, 'w') as f:
                json.dump(self.users, f)
            logger.info(f"Users saved successfully: {self.users}")
            
            # Verify the file was written correctly
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, 'r') as f:
                    saved_data = f.read().strip()
                    logger.info(f"Verification - users.json contains: {saved_data}")
            else:
                logger.error(f"Verification failed - {USERS_FILE} does not exist after save")
        except Exception as e:
            logger.error(f"Error saving users: {e}", exc_info=True)

    def add_user(self, chat_id, username=None):
        """Add or update a user with optional username"""
        chat_id = str(chat_id)
        self.users[chat_id] = username
        self.save_users()
        if username:
            logger.info(f"Added/updated user: {chat_id} (username: {username})")
        else:
            logger.info(f"Added/updated user: {chat_id}")

    def remove_user(self, chat_id):
        """Remove a user from the saved users list"""
        chat_id = str(chat_id)
        if chat_id in self.users:
            username = self.users.pop(chat_id)
            self.save_users()
            if username:
                logger.info(f"Removed user: {chat_id} (username: {username})")
            else:
                logger.info(f"Removed user: {chat_id}")

    def get_all_users(self):
        """Get list of all user chat IDs"""
        return list(self.users.keys())
    
    def get_user_info(self, chat_id):
        """Get username for a given chat_id"""
        chat_id = str(chat_id)
        return self.users.get(chat_id)

    def has_user(self, chat_id):
        """Check if a user exists in the saved users list"""
        return str(chat_id) in self.users