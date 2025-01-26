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
        """Compare updates with improved handling of nested year-based structure"""
        new_updates_dict = {}
        for update in new_updates:
            if "items" in update:  # year-based items
                lender_id = update.get('lender_id')
                for year_data in update["items"]:
                    year = year_data.get('year')
                    status = year_data.get('status')
                    substatus = year_data.get('substatus')

                    for item in year_data.get("items", []):
                        key = (lender_id, year, item.get('date', ''))
                        item_with_metadata = {
                            'lender_id': lender_id,
                            'year': year,
                            'status': status,
                            'substatus': substatus,
                            'company_name': self.get_company_name(lender_id),
                            **item
                        }
                        new_updates_dict[key] = item_with_metadata
                        logger.debug(f"Processed update for {self.get_company_name(lender_id)} on {item.get('date')}")

        prev_updates_dict = {}
        for update in previous_updates:
            if "items" in update:
                lender_id = update.get('lender_id')
                for year_data in update["items"]:
                    year = year_data.get('year')
                    for item in year_data.get("items", []):
                        key = (lender_id, year, item.get('date', ''))
                        prev_updates_dict[key] = item

        added_updates = []
        for key, update in new_updates_dict.items():
            if key not in prev_updates_dict:
                added_updates.append(update)

        logger.info(f"Found {len(added_updates)} new updates")
        return added_updates