"""
Data Manager for the Mintos Telegram Bot
Handles data persistence, caching, and updates management.
"""
import hashlib
import json
import logging
import os
import shutil
import time
from typing import Dict, List, Optional, Set, Any, Union
import pandas as pd
from .base_manager import BaseManager
from .constants import (
    DATA_DIR, UPDATES_FILE, CAMPAIGNS_FILE, COMPANY_NAMES_CSV,
    SENT_UPDATES_FILE, SENT_CAMPAIGNS_FILE
)
from .utils import create_unique_id, FileBackupManager

logger = logging.getLogger(__name__)

class DataManager(BaseManager):
    """Manages data persistence and caching for the bot"""

    def __init__(self):
        """Initialize DataManager with necessary data structures"""
        super().__init__(UPDATES_FILE)
        self.company_names: Dict[int, str] = {}
        self.sent_updates: Set[str] = set()
        self.sent_campaigns: Set[str] = set()
        
        # File paths for tracking sent items
        self.sent_updates_file = SENT_UPDATES_FILE
        self.sent_campaigns_file = SENT_CAMPAIGNS_FILE
        self.backup_sent_updates_file = f"{SENT_UPDATES_FILE}.bak"
        self.backup_sent_campaigns_file = f"{SENT_CAMPAIGNS_FILE}.bak"
        
        self._load_company_names()
        self._load_sent_updates()
        self._load_sent_campaigns()

    def _load_company_names(self) -> None:
        """Load company names from CSV file"""
        try:
            # Ensure attached_assets directory exists
            if not os.path.exists('attached_assets'):
                os.makedirs('attached_assets')
                logger.info("Created attached_assets directory")

            csv_path = COMPANY_NAMES_CSV
            self.company_names: Dict[int, str] = {}

            if os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path)
                    self.company_names = df.set_index('id')['name'].to_dict()
                    logger.info(f"Loaded {len(self.company_names)} company names")
                    logger.debug(f"Company IDs loaded: {list(self.company_names.keys())}")
                except pd.errors.EmptyDataError:
                    logger.warning(f"CSV file {csv_path} is empty")
                except pd.errors.ParserError:
                    logger.warning(f"Could not parse CSV file {csv_path}")
            else:
                logger.warning(f"CSV file {csv_path} not found")
        except Exception as e:
            logger.error(f"Error loading company names: {e}", exc_info=True)



    def _create_update_id(self, update: Dict[str, Any]) -> str:
        """Create a unique identifier for an update"""
        return create_unique_id(
            update.get('lender_id', ''),
            update.get('date', ''),
            update.get('year', ''),
            update.get('description', '')
        )

    def _create_campaign_id(self, campaign: Dict[str, Any]) -> str:
        """Create a unique identifier for a campaign"""
        return create_unique_id(
            f"campaign_{campaign.get('id', '')}",
            campaign.get('name', ''),
            campaign.get('validFrom', ''),
            campaign.get('validTo', '')
        )

    def _load_sent_updates(self) -> None:
        """Load set of already sent update IDs with verification and backup"""
        self.sent_updates: Set[str] = set()

        try:
            if os.path.exists(self.sent_updates_file):
                with open(self.sent_updates_file, 'r') as f:
                    data = json.load(f)
                    # Extract just the IDs from dictionaries if necessary
                    if data and isinstance(data, list):
                        if all(isinstance(item, dict) and 'id' in item for item in data):
                            # Format with IDs and timestamps
                            self.sent_updates = set(item['id'] for item in data)
                        else:
                            # Old format with just IDs
                            self.sent_updates = set(data)
                logger.info(f"Loaded {len(self.sent_updates)} sent update IDs")

                # Create backup if needed
                if not os.path.exists(self.backup_sent_updates_file):
                    with open(self.backup_sent_updates_file, 'w') as f:
                        # Use the same format as the main file for consistency
                        if os.path.exists(self.sent_updates_file):
                            with open(self.sent_updates_file, 'r') as main_f:
                                shutil.copyfileobj(main_f, f)
                        else:
                            json.dump(list(self.sent_updates), f)
                    logger.info("Created backup of sent updates")
            elif os.path.exists(self.backup_sent_updates_file):
                logger.warning("Main sent updates file not found, loading from backup")
                with open(self.backup_sent_updates_file, 'r') as f:
                    data = json.load(f)
                    # Extract just the IDs from dictionaries if necessary
                    if data and isinstance(data, list):
                        if all(isinstance(item, dict) and 'id' in item for item in data):
                            # Format with IDs and timestamps
                            self.sent_updates = set(item['id'] for item in data)
                        else:
                            # Old format with just IDs
                            self.sent_updates = set(data)
                logger.info(f"Loaded {len(self.sent_updates)} sent update IDs from backup")

                # Recreate main file
                with open(self.sent_updates_file, 'w') as f:
                    # Use the same format as the backup file for consistency
                    if os.path.exists(self.backup_sent_updates_file):
                        with open(self.backup_sent_updates_file, 'r') as backup_f:
                            shutil.copyfileobj(backup_f, f)
                    else:
                        json.dump(list(self.sent_updates), f)
        except Exception as e:
            logger.error(f"Error loading sent updates: {e}", exc_info=True)

    def save_sent_update(self, update: Dict[str, Any]) -> None:
        """Mark an update as sent with backup and timestamp"""
        try:
            update_id = self._create_update_id(update)
            self.sent_updates.add(update_id)
            
            # Load existing data
            sent_data = []
            try:
                with open(self.sent_updates_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        sent_data = [entry if isinstance(entry, dict) else {'id': entry} for entry in data]
            except (FileNotFoundError, json.JSONDecodeError):
                pass
                
            # Add or update entry
            now = time.time()
            updated = False
            for entry in sent_data:
                if entry.get('id') == update_id:
                    entry['timestamp'] = now
                    updated = True
                    break
            
            if not updated:
                sent_data.append({'id': update_id, 'timestamp': now})

            # Save to both main and backup files
            for file_path in [self.sent_updates_file, self.backup_sent_updates_file]:
                with open(file_path, 'w') as f:
                    json.dump(sent_data, f)

            logger.info(f"Saved sent update ID: {update_id}")
        except Exception as e:
            logger.error(f"Error saving sent update: {e}", exc_info=True)

    def is_update_sent(self, update: Dict[str, Any]) -> bool:
        """Check if an update has already been sent on the same day"""
        update_id = self._create_update_id(update)
        
        # First check if it's in sent updates
        if update_id not in self.sent_updates:
            return False
            
        # Check when it was last sent
        try:
            with open(self.sent_updates_file, 'r') as f:
                sent_data = json.load(f)
                
            # Get timestamp if available
            for entry in sent_data:
                if isinstance(entry, dict) and entry.get('id') == update_id:
                    last_sent = entry.get('timestamp', 0)
                    
                    # Get the date from timestamp
                    last_sent_date = time.strftime("%Y-%m-%d", time.localtime(last_sent))
                    current_date = time.strftime("%Y-%m-%d")
                    
                    # Don't resend if it was sent today (same calendar day)
                    if last_sent_date == current_date:
                        logger.info(f"Update {update_id} already sent today ({current_date}), skipping")
                        return True
                    
                    # Don't resend if same day as in the update
                    update_date = update.get('date', '')
                    if update_date and last_sent_date == update_date:
                        logger.info(f"Update {update_id} already sent on the update date ({update_date}), skipping")
                        return True
                    
                    # If we reach here, it wasn't sent today or on update date
                    logger.info(f"Update {update_id} was last sent on {last_sent_date}, can send again today")
                    return False
                    
            # If no timestamp found but ID is in sent_updates, assume it was sent
            logger.info(f"Update {update_id} is in sent list but has no timestamp, assuming sent")
            return True  
        except Exception as e:
            logger.error(f"Error checking update timestamp: {e}")
            return True

    def _load_sent_campaigns(self) -> None:
        """Load set of already sent campaign IDs with verification and backup"""
        try:
            if os.path.exists(self.sent_campaigns_file):
                with open(self.sent_campaigns_file, 'r') as f:
                    data = json.load(f)
                    # Extract just the IDs from dictionaries if necessary
                    if data and isinstance(data, list):
                        if all(isinstance(item, dict) and 'id' in item for item in data):
                            # Format with IDs and timestamps
                            self.sent_campaigns = set(item['id'] for item in data)
                        else:
                            # Old format with just IDs
                            self.sent_campaigns = set(data)
                logger.info(f"Loaded {len(self.sent_campaigns)} sent campaign IDs")

                # Create backup if needed
                if not os.path.exists(self.backup_sent_campaigns_file):
                    with open(self.backup_sent_campaigns_file, 'w') as f:
                        # Use the same format as the main file for consistency
                        if os.path.exists(self.sent_campaigns_file):
                            with open(self.sent_campaigns_file, 'r') as main_f:
                                shutil.copyfileobj(main_f, f)
                        else:
                            json.dump(list(self.sent_campaigns), f)
                    logger.info("Created backup of sent campaigns")
            elif os.path.exists(self.backup_sent_campaigns_file):
                logger.warning("Main sent campaigns file not found, loading from backup")
                with open(self.backup_sent_campaigns_file, 'r') as f:
                    data = json.load(f)
                    # Extract just the IDs from dictionaries if necessary
                    if data and isinstance(data, list):
                        if all(isinstance(item, dict) and 'id' in item for item in data):
                            # Format with IDs and timestamps
                            self.sent_campaigns = set(item['id'] for item in data)
                        else:
                            # Old format with just IDs
                            self.sent_campaigns = set(data)
                logger.info(f"Loaded {len(self.sent_campaigns)} sent campaign IDs from backup")

                # Recreate main file
                with open(self.sent_campaigns_file, 'w') as f:
                    # Use the same format as the backup file for consistency
                    if os.path.exists(self.backup_sent_campaigns_file):
                        with open(self.backup_sent_campaigns_file, 'r') as backup_f:
                            shutil.copyfileobj(backup_f, f)
                    else:
                        json.dump(list(self.sent_campaigns), f)
        except Exception as e:
            logger.error(f"Error loading sent campaigns: {e}", exc_info=True)

    def save_sent_campaign(self, campaign: Dict[str, Any]) -> None:
        """Mark a campaign as sent with backup and timestamp"""
        try:
            campaign_id = self._create_campaign_id(campaign)
            self.sent_campaigns.add(campaign_id)
            
            # Load existing data
            sent_data = []
            try:
                with open(self.sent_campaigns_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        sent_data = [entry if isinstance(entry, dict) else {'id': entry} for entry in data]
            except (FileNotFoundError, json.JSONDecodeError):
                pass
                
            # Add or update entry
            now = time.time()
            updated = False
            for entry in sent_data:
                if entry.get('id') == campaign_id:
                    entry['timestamp'] = now
                    updated = True
                    break
            
            if not updated:
                sent_data.append({'id': campaign_id, 'timestamp': now})

            # Save to both main and backup files
            for file_path in [self.sent_campaigns_file, self.backup_sent_campaigns_file]:
                with open(file_path, 'w') as f:
                    json.dump(sent_data, f)

            logger.info(f"Saved sent campaign ID: {campaign_id}")
        except Exception as e:
            logger.error(f"Error saving sent campaign: {e}", exc_info=True)

    def is_campaign_sent(self, campaign: Dict[str, Any]) -> bool:
        """Check if a campaign has already been sent"""
        return self._create_campaign_id(campaign) in self.sent_campaigns

    def get_cache_age(self) -> float:
        """Get age of cache in seconds"""
        return self.get_file_age()

    def load_previous_updates(self) -> List[Dict[str, Any]]:
        """Load previous updates from cache file"""
        updates = self.load_data([])
        logger.info(f"Loaded {len(updates)} company updates from cache")
        return updates

    def save_updates(self, updates: List[Dict[str, Any]]) -> None:
        """Save updates to cache file"""
        if self.save_data(updates):
            logger.info(f"Successfully saved {len(updates)} updates")
        else:
            logger.error("Failed to save updates")
            raise Exception("Failed to save updates")

    def get_company_name(self, lender_id: Any) -> str:
        """Get company name by lender ID, falling back to ID if name not found"""
        try:
            lender_id = int(lender_id)
            name = self.company_names.get(lender_id)
            if name is None:
                logger.debug(f"Company name not found for lender_id: {lender_id}, using ID")
                return str(lender_id)  # Just return the ID, not "Unknown Company"
            return name
        except (ValueError, TypeError):
            logger.warning(f"Invalid lender_id format: {lender_id}")
            return str(lender_id) if lender_id else "Invalid ID"

    def compare_updates(self, new_updates: List[Dict[str, Any]], previous_updates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compare updates to find new ones"""
        logger.debug(f"Comparing {len(new_updates)} new updates with {len(previous_updates)} previous updates")

        new_updates_dict = {}
        for update in new_updates:
            if "items" not in update:
                continue

            lender_id = update.get('lender_id')
            for year_data in update["items"]:
                year = year_data.get('year')
                status = year_data.get('status')
                substatus = year_data.get('substatus')

                for item in year_data.get("items", []):
                    key = (lender_id, year, item.get('date', ''))
                    new_updates_dict[key] = {
                        'lender_id': lender_id,
                        'year': year,
                        'status': status,
                        'substatus': substatus,
                        'company_name': self.get_company_name(lender_id),
                        **item
                    }

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
            if key not in prev_updates_dict or not self._updates_match(update, prev_updates_dict[key]):
                added_updates.append(update)

        logger.info(f"Found {len(added_updates)} new updates")
        return added_updates

    def _updates_match(self, update1: Dict[str, Any], update2: Dict[str, Any]) -> bool:
        """Compare two updates for equality in significant fields"""
        significant_fields = ['description', 'date', 'recoveredAmount', 'remainingAmount']
        return all(update1.get(field) == update2.get(field) for field in significant_fields)

    def compare_campaigns(self, new_campaigns: List[Dict[str, Any]], previous_campaigns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compare campaigns to find new or updated ones"""
        logger.debug(f"Comparing {len(new_campaigns)} new campaigns with {len(previous_campaigns)} previous campaigns")

        if not new_campaigns:
            return []

        prev_campaigns_dict = {c.get('id'): c for c in previous_campaigns if c.get('id')}
        added_campaigns = []

        for new_campaign in new_campaigns:
            campaign_id = new_campaign.get('id')
            if not campaign_id:
                continue

            if campaign_id not in prev_campaigns_dict:
                if not self.is_campaign_sent(new_campaign):
                    added_campaigns.append(new_campaign)
            elif not self._are_campaigns_identical(new_campaign, prev_campaigns_dict[campaign_id]):
                if not self.is_campaign_sent(new_campaign):
                    added_campaigns.append(new_campaign)

        logger.info(f"Found {len(added_campaigns)} new or updated campaigns")
        return added_campaigns

    def _are_campaigns_identical(self, new_campaign: Dict[str, Any], prev_campaign: Dict[str, Any]) -> bool:
        """Compare two campaigns for equality in significant fields"""
        significant_fields = [
            'name', 'shortDescription', 'validFrom', 'validTo',
            'bonusAmount', 'requiredPrincipalExposure', 'termsConditionsLink'
        ]

        return all(new_campaign.get(field) == prev_campaign.get(field) 
                  for field in significant_fields)

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