import json
import os
import pandas as pd
from .logger import setup_logger
from .config import DATA_DIR, UPDATES_FILE

logger = setup_logger(__name__)

class DataManager:
    def __init__(self):
        self.ensure_data_directory()
        self._load_company_names()

    def ensure_data_directory(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            logger.info(f"Created data directory: {DATA_DIR}")

    def _load_company_names(self):
        try:
            # Load company names from CSV in attached_assets directory
            df = pd.read_csv('attached_assets/lo_names.csv')
            self.company_names = df.set_index('id')['name'].to_dict()
            logger.info(f"Loaded {len(self.company_names)} company names")
        except Exception as e:
            logger.error(f"Error loading company names: {e}")
            self.company_names = {}
            raise

    def load_previous_updates(self):
        try:
            if os.path.exists(UPDATES_FILE):
                with open(UPDATES_FILE, 'r') as f:
                    return json.load(f)
            logger.info("No previous updates found")
            return []
        except Exception as e:
            logger.error(f"Error loading previous updates: {e}")
            return []

    def save_updates(self, updates):
        try:
            with open(UPDATES_FILE, 'w') as f:
                json.dump(updates, f, indent=4)
            logger.info(f"Successfully saved {len(updates)} updates")
        except Exception as e:
            logger.error(f"Error saving updates: {e}")
            raise

    def get_company_name(self, lender_id):
        return self.company_names.get(lender_id, f"Unknown Company {lender_id}")

    def compare_updates(self, new_updates, previous_updates):
        new_updates_dict = {(update['lender_id'], update.get('lastUpdate', '')): update 
                           for update in new_updates}
        prev_updates_dict = {(update['lender_id'], update.get('lastUpdate', '')): update 
                             for update in previous_updates}

        added_updates = []
        for key, update in new_updates_dict.items():
            if key not in prev_updates_dict:
                company_name = self.get_company_name(update['lender_id'])
                update['company_name'] = company_name
                added_updates.append(update)

        logger.info(f"Found {len(added_updates)} new updates")
        return added_updates