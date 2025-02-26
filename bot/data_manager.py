import json
import os
import time
import pandas as pd
from .logger import setup_logger
from .config import DATA_DIR, UPDATES_FILE

logger = setup_logger(__name__)

class DataManager:
    def __init__(self):
        self.ensure_data_directory()
        self._load_company_names()
        self._load_sent_updates()

    def ensure_data_directory(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            logger.info(f"Created data directory: {DATA_DIR}")

    def _load_company_names(self):
        try:
            # Ensure attached_assets directory exists
            if not os.path.exists('attached_assets'):
                os.makedirs('attached_assets')
                logger.info("Created attached_assets directory")
                
            # Load company names from CSV in attached_assets directory
            csv_path = 'attached_assets/lo_names.csv'
            if os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path)
                    self.company_names = df.set_index('id')['name'].to_dict()
                    logger.info(f"Loaded {len(self.company_names)} company names")
                    logger.debug(f"Company IDs loaded: {list(self.company_names.keys())}")
                except pd.errors.EmptyDataError:
                    logger.warning(f"CSV file {csv_path} is empty. Using empty company names dictionary")
                    self.company_names = {}
                except pd.errors.ParserError:
                    logger.warning(f"Could not parse CSV file {csv_path}. Using empty company names dictionary")
                    self.company_names = {}
            else:
                logger.warning(f"CSV file {csv_path} not found. Using empty company names dictionary")
                self.company_names = {}
        except Exception as e:
            logger.error(f"Error loading company names: {e}", exc_info=True)
            self.company_names = {}

    def _create_update_id(self, update):
        """Create a unique identifier for an update"""
        return f"{update.get('lender_id')}_{update.get('date')}_{hash(update.get('description', ''))}"

    def _load_sent_updates(self):
        """Load set of already sent update IDs"""
        self.sent_updates_file = os.path.join(DATA_DIR, 'sent_updates.json')
        try:
            if os.path.exists(self.sent_updates_file):
                with open(self.sent_updates_file, 'r') as f:
                    self.sent_updates = set(json.load(f))
            else:
                self.sent_updates = set()
            logger.info(f"Loaded {len(self.sent_updates)} sent update IDs")
        except Exception as e:
            logger.error(f"Error loading sent updates: {e}", exc_info=True)
            self.sent_updates = set()

    def save_sent_update(self, update):
        """Mark an update as sent"""
        try:
            update_id = self._create_update_id(update)
            self.sent_updates.add(update_id)
            with open(self.sent_updates_file, 'w') as f:
                json.dump(list(self.sent_updates), f)
            logger.debug(f"Saved sent update ID: {update_id}")
        except Exception as e:
            logger.error(f"Error saving sent update: {e}", exc_info=True)

    def is_update_sent(self, update):
        """Check if an update has already been sent"""
        return self._create_update_id(update) in self.sent_updates

    def get_cache_age(self):
        """Get age of cache in seconds"""
        try:
            if os.path.exists(UPDATES_FILE):
                age = time.time() - os.path.getmtime(UPDATES_FILE)
                logger.debug(f"Cache age: {age:.2f} seconds")
                return age
            logger.debug("Cache file does not exist")
            return float('inf')
        except Exception as e:
            logger.error(f"Error checking cache age: {e}", exc_info=True)
            return float('inf')

    def load_previous_updates(self):
        try:
            if os.path.exists(UPDATES_FILE):
                with open(UPDATES_FILE, 'r') as f:
                    updates = json.load(f)
                logger.info(f"Loaded {len(updates)} company updates from cache")
                logger.debug("Update structure:")
                for update in updates[:3]:  # Log first 3 updates for debugging
                    logger.debug(f"Company ID: {update.get('lender_id')}")
                    if 'items' in update:
                        logger.debug(f"Number of year items: {len(update['items'])}")
                return updates
            logger.info("No previous updates found")
            return []
        except Exception as e:
            logger.error(f"Error loading previous updates: {e}", exc_info=True)
            return []

    def save_updates(self, updates):
        try:
            with open(UPDATES_FILE, 'w') as f:
                json.dump(updates, f, indent=4)
            logger.info(f"Successfully saved {len(updates)} updates")
            logger.debug(f"Updates file size: {os.path.getsize(UPDATES_FILE)} bytes")
        except Exception as e:
            logger.error(f"Error saving updates: {e}", exc_info=True)
            raise

    def get_company_name(self, lender_id):
        name = self.company_names.get(lender_id)
        if name is None:
            logger.warning(f"Company name not found for lender_id: {lender_id}")
            name = f"Unknown Company {lender_id}"
        return name

    def compare_updates(self, new_updates, previous_updates):
        """Compare updates with improved handling of nested year-based structure"""
        logger.debug(f"Comparing {len(new_updates)} new updates with {len(previous_updates)} previous updates")

        new_updates_dict = {}
        for update in new_updates:
            if "items" in update:  # year-based items
                lender_id = update.get('lender_id')
                logger.debug(f"Processing new updates for lender_id: {lender_id}")

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
                # Check if this is truly a new update by comparing content
                is_new = True
                for prev_key, prev_update in prev_updates_dict.items():
                    if (prev_key[0] == key[0]  # Same lender_id
                        and prev_update.get('description') == update.get('description')
                        and prev_update.get('date') == update.get('date')):
                        is_new = False
                        break
                if is_new:
                    added_updates.append(update)
                    logger.debug(f"Found new update for {update.get('company_name')} on {update.get('date')}")

        logger.info(f"Found {len(added_updates)} new updates")
        return added_updates