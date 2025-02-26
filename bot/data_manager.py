import json
import os
import time
import hashlib
import pandas as pd
from .logger import setup_logger
from .config import DATA_DIR, UPDATES_FILE, CAMPAIGNS_FILE

logger = setup_logger(__name__)

class DataManager:
    def __init__(self):
        self.ensure_data_directory()
        self._load_company_names()
        self._load_sent_updates()
        
        # Initialize sent_campaigns set
        self.sent_campaigns = set()
        self.sent_campaigns_file = os.path.join(DATA_DIR, 'sent_campaigns.json')
        self.backup_sent_campaigns_file = os.path.join(DATA_DIR, 'sent_campaigns.json.bak')
        
        # Now load sent campaigns
        try:
            self._load_sent_campaigns()
        except Exception as e:
            logger.error(f"Error loading sent campaigns: {e}", exc_info=True)

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
        # Use MD5 hash for consistent results across program runs
        lender_id = str(update.get('lender_id', ''))
        date = str(update.get('date', ''))
        year = str(update.get('year', ''))
        description = str(update.get('description', ''))
        
        # Create a consistent string to hash
        hash_content = f"{lender_id}_{date}_{year}_{description}"
        # Generate a stable, unique hash
        return hashlib.md5(hash_content.encode()).hexdigest()
        
    def _create_campaign_id(self, campaign):
        """Create a unique identifier for a campaign"""
        # Use MD5 hash for consistent results across program runs
        campaign_id = str(campaign.get('id', ''))
        name = str(campaign.get('name', ''))
        valid_from = str(campaign.get('validFrom', ''))
        valid_to = str(campaign.get('validTo', ''))
        
        # Create a consistent string to hash
        hash_content = f"campaign_{campaign_id}_{name}_{valid_from}_{valid_to}"
        # Generate a stable, unique hash
        return hashlib.md5(hash_content.encode()).hexdigest()

    def _load_sent_updates(self):
        """Load set of already sent update IDs with verification and backup handling"""
        self.sent_updates_file = os.path.join(DATA_DIR, 'sent_updates.json')
        self.backup_sent_updates_file = os.path.join(DATA_DIR, 'sent_updates.json.bak')
        
        try:
            # First try to load from the main file
            if os.path.exists(self.sent_updates_file):
                with open(self.sent_updates_file, 'r') as f:
                    data = json.load(f)
                    self.sent_updates = set(data)
                logger.info(f"Loaded {len(self.sent_updates)} sent update IDs from main file")
                
                # Create backup if it doesn't exist
                if not os.path.exists(self.backup_sent_updates_file):
                    with open(self.backup_sent_updates_file, 'w') as f:
                        json.dump(list(self.sent_updates), f)
                    logger.info(f"Created backup of sent updates with {len(self.sent_updates)} IDs")
                    
            # If main file doesn't exist, try to load from backup
            elif os.path.exists(self.backup_sent_updates_file):
                logger.warning("Main sent updates file not found, loading from backup")
                with open(self.backup_sent_updates_file, 'r') as f:
                    data = json.load(f)
                    self.sent_updates = set(data)
                logger.info(f"Loaded {len(self.sent_updates)} sent update IDs from backup file")
                
                # Recreate the main file
                with open(self.sent_updates_file, 'w') as f:
                    json.dump(list(self.sent_updates), f)
                logger.info("Recreated main sent updates file from backup")
            else:
                logger.info("No sent updates files found, starting with empty set")
                self.sent_updates = set()
        except Exception as e:
            logger.error(f"Error loading sent updates: {e}", exc_info=True)
            self.sent_updates = set()

    def save_sent_update(self, update):
        """Mark an update as sent with backup"""
        try:
            update_id = self._create_update_id(update)
            self.sent_updates.add(update_id)
            
            # Save to main file
            with open(self.sent_updates_file, 'w') as f:
                json.dump(list(self.sent_updates), f)
                
            # Also save to backup file
            with open(self.backup_sent_updates_file, 'w') as f:
                json.dump(list(self.sent_updates), f)
                
            logger.info(f"Saved sent update ID: {update_id} (total: {len(self.sent_updates)})")
        except Exception as e:
            logger.error(f"Error saving sent update: {e}", exc_info=True)

    def is_update_sent(self, update):
        """Check if an update has already been sent"""
        return self._create_update_id(update) in self.sent_updates
        
    def _load_sent_campaigns(self):
        """Load set of already sent campaign IDs with verification and backup handling"""
        self.sent_campaigns_file = os.path.join(DATA_DIR, 'sent_campaigns.json')
        self.backup_sent_campaigns_file = os.path.join(DATA_DIR, 'sent_campaigns.json.bak')
        
        try:
            # First try to load from the main file
            if os.path.exists(self.sent_campaigns_file):
                with open(self.sent_campaigns_file, 'r') as f:
                    data = json.load(f)
                    self.sent_campaigns = set(data)
                logger.info(f"Loaded {len(self.sent_campaigns)} sent campaign IDs from main file")
                
                # Create backup if it doesn't exist
                if not os.path.exists(self.backup_sent_campaigns_file):
                    with open(self.backup_sent_campaigns_file, 'w') as f:
                        json.dump(list(self.sent_campaigns), f)
                    logger.info(f"Created backup of sent campaigns with {len(self.sent_campaigns)} IDs")
                    
            # If main file doesn't exist, try to load from backup
            elif os.path.exists(self.backup_sent_campaigns_file):
                logger.warning("Main sent campaigns file not found, loading from backup")
                with open(self.backup_sent_campaigns_file, 'r') as f:
                    data = json.load(f)
                    self.sent_campaigns = set(data)
                logger.info(f"Loaded {len(self.sent_campaigns)} sent campaign IDs from backup file")
                
                # Recreate the main file
                with open(self.sent_campaigns_file, 'w') as f:
                    json.dump(list(self.sent_campaigns), f)
                logger.info("Recreated main sent campaigns file from backup")
            else:
                logger.info("No sent campaigns files found, starting with empty set")
                self.sent_campaigns = set()
        except Exception as e:
            logger.error(f"Error loading sent campaigns: {e}", exc_info=True)
            self.sent_campaigns = set()
            
    def save_sent_campaign(self, campaign):
        """Mark a campaign as sent with backup"""
        try:
            campaign_id = self._create_campaign_id(campaign)
            self.sent_campaigns.add(campaign_id)
            
            # Save to main file
            with open(self.sent_campaigns_file, 'w') as f:
                json.dump(list(self.sent_campaigns), f)
                
            # Also save to backup file
            with open(self.backup_sent_campaigns_file, 'w') as f:
                json.dump(list(self.sent_campaigns), f)
                
            logger.info(f"Saved sent campaign ID: {campaign_id} (total: {len(self.sent_campaigns)})")
        except Exception as e:
            logger.error(f"Error saving sent campaign: {e}", exc_info=True)

    def is_campaign_sent(self, campaign):
        """Check if a campaign has already been sent"""
        return self._create_campaign_id(campaign) in self.sent_campaigns

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
            
    def get_campaigns_cache_age(self):
        """Get age of campaigns cache in seconds"""
        try:
            if os.path.exists(CAMPAIGNS_FILE):
                age = time.time() - os.path.getmtime(CAMPAIGNS_FILE)
                logger.debug(f"Campaigns cache age: {age:.2f} seconds")
                return age
            logger.debug("Campaigns cache file does not exist")
            return float('inf')
        except Exception as e:
            logger.error(f"Error checking campaigns cache age: {e}", exc_info=True)
            return float('inf')
    
    def load_previous_campaigns(self):
        """Load previous campaigns from cache file"""
        try:
            if os.path.exists(CAMPAIGNS_FILE):
                with open(CAMPAIGNS_FILE, 'r') as f:
                    campaigns = json.load(f)
                logger.info(f"Loaded {len(campaigns)} campaigns from cache")
                return campaigns
            logger.info("No previous campaigns found")
            return []
        except Exception as e:
            logger.error(f"Error loading previous campaigns: {e}", exc_info=True)
            return []
    
    def save_campaigns(self, campaigns):
        """Save campaigns to cache file"""
        try:
            with open(CAMPAIGNS_FILE, 'w') as f:
                json.dump(campaigns, f, indent=4)
            logger.info(f"Successfully saved {len(campaigns)} campaigns")
            logger.debug(f"Campaigns file size: {os.path.getsize(CAMPAIGNS_FILE)} bytes")
        except Exception as e:
            logger.error(f"Error saving campaigns: {e}", exc_info=True)
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
        
    def compare_campaigns(self, new_campaigns, previous_campaigns):
        """Compare campaigns to find new or updated ones"""
        logger.debug(f"Comparing {len(new_campaigns)} new campaigns with {len(previous_campaigns)} previous campaigns")
        
        if not new_campaigns:
            logger.info("No new campaigns to compare")
            return []
            
        # Create a dictionary of previous campaigns by ID for easier comparison
        prev_campaigns_dict = {campaign.get('id'): campaign for campaign in previous_campaigns if campaign.get('id')}
        
        added_campaigns = []
        for new_campaign in new_campaigns:
            campaign_id = new_campaign.get('id')
            if not campaign_id:
                logger.warning("Campaign without ID found, skipping")
                continue
                
            # Check if this is a new campaign or changed campaign
            if campaign_id not in prev_campaigns_dict:
                # This is a completely new campaign
                if not self.is_campaign_sent(new_campaign):
                    logger.debug(f"Found new campaign: {new_campaign.get('name', 'Unnamed')} (ID: {campaign_id})")
                    added_campaigns.append(new_campaign)
                else:
                    logger.debug(f"Found new campaign but already notified: {campaign_id}")
            else:
                # This campaign existed before, check if it was modified in important fields
                prev_campaign = prev_campaigns_dict[campaign_id]
                if not self._are_campaigns_identical(new_campaign, prev_campaign):
                    # The campaign has been updated in a significant way
                    if not self.is_campaign_sent(new_campaign):
                        logger.debug(f"Found updated campaign: {new_campaign.get('name', 'Unnamed')} (ID: {campaign_id})")
                        added_campaigns.append(new_campaign)
                    else:
                        logger.debug(f"Found updated campaign but already notified: {campaign_id}")
                        
        logger.info(f"Found {len(added_campaigns)} new or updated campaigns")
        return added_campaigns
        
    def _are_campaigns_identical(self, new_campaign, prev_campaign):
        """Compare two campaigns for equality in significant fields"""
        # Fields to compare that would make a meaningful difference to users
        significant_fields = [
            'name', 
            'shortDescription', 
            'validFrom', 
            'validTo', 
            'bonusAmount',
            'requiredPrincipalExposure',
            'termsConditionsLink'
        ]
        
        for field in significant_fields:
            # Compare each significant field
            if new_campaign.get(field) != prev_campaign.get(field):
                logger.debug(f"Campaign field '{field}' changed: {prev_campaign.get(field)} -> {new_campaign.get(field)}")
                return False
                
        return True