import json
import os
from .logger import setup_logger
from .config import USERS_FILE

logger = setup_logger(__name__)

class UserManager:
    def __init__(self):
        self.users = set()
        self.load_users()

    def load_users(self):
        try:
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, 'r') as f:
                    self.users = set(json.load(f))
            logger.info(f"Loaded {len(self.users)} users")
        except Exception as e:
            logger.error(f"Error loading users: {e}")

    def save_users(self):
        try:
            os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
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
