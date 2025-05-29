import json
import os
from .logger import setup_logger
from .config import USERS_FILE, DATA_DIR

logger = setup_logger(__name__)

class UserManager:
    def __init__(self):
        self.users = {}  # Changed from set to dict to store username with chat_id
        self.rss_preferences_file = os.path.join(DATA_DIR, 'rss_user_preferences.json')
        self.rss_preferences = {}  # Store RSS notification preferences
        self._ensure_data_directory()
        self.load_users()
        self._load_rss_preferences()

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

    def _load_rss_preferences(self):
        """Load RSS notification preferences"""
        try:
            if os.path.exists(self.rss_preferences_file):
                with open(self.rss_preferences_file, 'r') as f:
                    self.rss_preferences = json.load(f)
                logger.info(f"Loaded RSS preferences for {len(self.rss_preferences)} users")
            else:
                self.rss_preferences = {}
        except Exception as e:
            logger.error(f"Error loading RSS preferences: {e}")
            self.rss_preferences = {}

    def _save_rss_preferences(self):
        """Save RSS notification preferences"""
        try:
            with open(self.rss_preferences_file, 'w') as f:
                json.dump(self.rss_preferences, f, indent=2)
            logger.info(f"Saved RSS preferences for {len(self.rss_preferences)} users")
        except Exception as e:
            logger.error(f"Error saving RSS preferences: {e}")

    def set_rss_preference(self, chat_id, enabled):
        """Set RSS notifications preference for a user"""
        chat_id = str(chat_id)
        self.rss_preferences[chat_id] = enabled
        self._save_rss_preferences()
        logger.info(f"RSS notifications {'enabled' if enabled else 'disabled'} for user {chat_id}")

    def get_rss_preference(self, chat_id):
        """Get RSS notifications preference for a user (default: False)"""
        return self.rss_preferences.get(str(chat_id), False)

    def get_users_with_rss_enabled(self):
        """Get list of users who have RSS notifications enabled"""
        return [chat_id for chat_id, enabled in self.rss_preferences.items() if enabled]