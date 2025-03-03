"""
Data Manager for the Mintos Telegram Bot
Handles data persistence, caching, and updates management.
"""
import json
import os
import time
import hashlib
import logging
from typing import Dict, List, Optional, Set, Any, Union
import pandas as pd
from .logger import setup_logger
from .config import (
    DATA_DIR, 
    UPDATES_FILE, 
    CAMPAIGNS_FILE, 
    DOCUMENTS_FILE,
    COMPANY_MAPPING_FILE
)

logger = setup_logger(__name__)

class DataManager:
    """Manages data persistence and caching for the bot"""

    def __init__(self):
        """Initialize DataManager with necessary data structures"""
        self.ensure_data_directory()
        self._load_company_names()
        self._load_sent_updates()

        # Initialize sent_campaigns tracking
        self.sent_campaigns: Set[str] = set()
        self.sent_campaigns_file = os.path.join(DATA_DIR, 'sent_campaigns.json')
        self.backup_sent_campaigns_file = os.path.join(DATA_DIR, 'sent_campaigns.json.bak')

        try:
            self._load_sent_campaigns()
        except Exception as e:
            logger.error(f"Error loading sent campaigns: {e}", exc_info=True)
            
        # Initialize document tracking
        self.initialize_document_tracking()

    def ensure_data_directory(self) -> None:
        """Ensure data directory exists"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            logger.info(f"Created data directory: {DATA_DIR}")

    def _load_company_names(self) -> None:
        """Load company names from CSV file"""
        try:
            # Ensure attached_assets directory exists
            if not os.path.exists('attached_assets'):
                os.makedirs('attached_assets')
                logger.info("Created attached_assets directory")

            csv_path = 'attached_assets/lo_names.csv'
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
        hash_content = "_".join([
            str(update.get('lender_id', '')),
            str(update.get('date', '')),
            str(update.get('year', '')),
            str(update.get('description', ''))
        ])
        return hashlib.md5(hash_content.encode()).hexdigest()

    def _create_campaign_id(self, campaign: Dict[str, Any]) -> str:
        """Create a unique identifier for a campaign"""
        hash_content = "_".join([
            f"campaign_{campaign.get('id', '')}",
            str(campaign.get('name', '')),
            str(campaign.get('validFrom', '')),
            str(campaign.get('validTo', ''))
        ])
        return hashlib.md5(hash_content.encode()).hexdigest()

    def _load_sent_updates(self) -> None:
        """Load set of already sent update IDs with verification and backup"""
        self.sent_updates_file = os.path.join(DATA_DIR, 'sent_updates.json')
        self.backup_sent_updates_file = os.path.join(DATA_DIR, 'sent_updates.json.bak')
        self.sent_updates: Set[str] = set()

        try:
            if os.path.exists(self.sent_updates_file):
                with open(self.sent_updates_file, 'r') as f:
                    self.sent_updates = set(json.load(f))
                logger.info(f"Loaded {len(self.sent_updates)} sent update IDs")

                # Create backup if needed
                if not os.path.exists(self.backup_sent_updates_file):
                    with open(self.backup_sent_updates_file, 'w') as f:
                        json.dump(list(self.sent_updates), f)
                    logger.info("Created backup of sent updates")
            elif os.path.exists(self.backup_sent_updates_file):
                logger.warning("Main sent updates file not found, loading from backup")
                with open(self.backup_sent_updates_file, 'r') as f:
                    self.sent_updates = set(json.load(f))
                logger.info(f"Loaded {len(self.sent_updates)} sent update IDs from backup")

                # Recreate main file
                with open(self.sent_updates_file, 'w') as f:
                    json.dump(list(self.sent_updates), f)
        except Exception as e:
            logger.error(f"Error loading sent updates: {e}", exc_info=True)

    def save_sent_update(self, update: Dict[str, Any]) -> None:
        """Mark an update as sent with backup"""
        try:
            update_id = self._create_update_id(update)
            self.sent_updates.add(update_id)

            # Save to both main and backup files
            for file_path in [self.sent_updates_file, self.backup_sent_updates_file]:
                with open(file_path, 'w') as f:
                    json.dump(list(self.sent_updates), f)

            logger.info(f"Saved sent update ID: {update_id}")
        except Exception as e:
            logger.error(f"Error saving sent update: {e}", exc_info=True)

    def is_update_sent(self, update: Dict[str, Any]) -> bool:
        """Check if an update has already been sent"""
        return self._create_update_id(update) in self.sent_updates

    def _load_sent_campaigns(self) -> None:
        """Load set of already sent campaign IDs with verification and backup"""
        try:
            if os.path.exists(self.sent_campaigns_file):
                with open(self.sent_campaigns_file, 'r') as f:
                    self.sent_campaigns = set(json.load(f))
                logger.info(f"Loaded {len(self.sent_campaigns)} sent campaign IDs")

                # Create backup if needed
                if not os.path.exists(self.backup_sent_campaigns_file):
                    with open(self.backup_sent_campaigns_file, 'w') as f:
                        json.dump(list(self.sent_campaigns), f)
            elif os.path.exists(self.backup_sent_campaigns_file):
                logger.warning("Main sent campaigns file not found, loading from backup")
                with open(self.backup_sent_campaigns_file, 'r') as f:
                    self.sent_campaigns = set(json.load(f))

                # Recreate main file
                with open(self.sent_campaigns_file, 'w') as f:
                    json.dump(list(self.sent_campaigns), f)
        except Exception as e:
            logger.error(f"Error loading sent campaigns: {e}", exc_info=True)

    def save_sent_campaign(self, campaign: Dict[str, Any]) -> None:
        """Mark a campaign as sent with backup"""
        try:
            campaign_id = self._create_campaign_id(campaign)
            self.sent_campaigns.add(campaign_id)

            # Save to both main and backup files
            for file_path in [self.sent_campaigns_file, self.backup_sent_campaigns_file]:
                with open(file_path, 'w') as f:
                    json.dump(list(self.sent_campaigns), f)

            logger.info(f"Saved sent campaign ID: {campaign_id}")
        except Exception as e:
            logger.error(f"Error saving sent campaign: {e}", exc_info=True)

    def is_campaign_sent(self, campaign: Dict[str, Any]) -> bool:
        """Check if a campaign has already been sent"""
        return self._create_campaign_id(campaign) in self.sent_campaigns

    def get_cache_age(self) -> float:
        """Get age of cache in seconds"""
        try:
            if os.path.exists(UPDATES_FILE):
                age = time.time() - os.path.getmtime(UPDATES_FILE)
                logger.debug(f"Cache age: {age:.2f} seconds")
                return age
            return float('inf')
        except Exception as e:
            logger.error(f"Error checking cache age: {e}", exc_info=True)
            return float('inf')

    def load_previous_updates(self) -> List[Dict[str, Any]]:
        """Load previous updates from cache file"""
        try:
            if os.path.exists(UPDATES_FILE):
                with open(UPDATES_FILE, 'r') as f:
                    updates = json.load(f)
                logger.info(f"Loaded {len(updates)} company updates from cache")
                return updates
            logger.info("No previous updates found")
            return []
        except Exception as e:
            logger.error(f"Error loading previous updates: {e}", exc_info=True)
            return []

    def save_updates(self, updates: List[Dict[str, Any]]) -> None:
        """Save updates to cache file"""
        try:
            with open(UPDATES_FILE, 'w') as f:
                json.dump(updates, f, indent=4)
            logger.info(f"Successfully saved {len(updates)} updates")
        except Exception as e:
            logger.error(f"Error saving updates: {e}", exc_info=True)
            raise

    def get_company_name(self, lender_id: Union[int, str]) -> str:
        """Get company name by lender ID"""
        try:
            lender_id = int(lender_id)
            name = self.company_names.get(lender_id)
            if name is None:
                logger.warning(f"Company name not found for lender_id: {lender_id}")
                name = f"Unknown Company {lender_id}"
            return name
        except (ValueError, TypeError):
            logger.error(f"Invalid lender_id format: {lender_id}")
            return f"Invalid Company ID {lender_id}"

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
    
    # Methods for handling company mappings for document scraping
    
    def save_company_mapping(self, mapping: Dict[str, str]) -> None:
        """Save company ID to name mapping (for document scraping)
        
        Args:
            mapping: Dictionary mapping company IDs (string) to company names
        """
        try:
            with open(COMPANY_MAPPING_FILE, 'w') as f:
                json.dump(mapping, f, indent=4)
            logger.info(f"Successfully saved mapping for {len(mapping)} companies")
        except Exception as e:
            logger.error(f"Error saving company mapping: {e}", exc_info=True)
            raise
    
    def load_company_mapping(self) -> Dict[str, str]:
        """Load company ID to name mapping
        
        Returns:
            Dictionary mapping company IDs to names
        """
        try:
            if os.path.exists(COMPANY_MAPPING_FILE):
                with open(COMPANY_MAPPING_FILE, 'r') as f:
                    mapping = json.load(f)
                logger.info(f"Loaded mapping for {len(mapping)} companies")
                return mapping
            
            # If no mapping file exists yet, create a default one based on company names
            mapping = self._create_default_company_mapping()
            self.save_company_mapping(mapping)
            return mapping
        except Exception as e:
            logger.error(f"Error loading company mapping: {e}", exc_info=True)
            return {}
    
    def _create_default_company_mapping(self) -> Dict[str, str]:
        """Create default company mapping based on available company names
        
        This is a best-effort function that attempts to create URL-friendly IDs
        from company names.
        
        Returns:
            Dictionary mapping company IDs to names
        """
        mapping = {}
        
        # Convert company names to URL-friendly slugs
        for lender_id, name in self.company_names.items():
            if not name:
                continue
                
            # Create a slug by converting to lowercase and replacing spaces with hyphens
            slug = name.lower().replace(' ', '-').replace('.', '')
            
            # Remove any special characters
            import re
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            
            # Add to mapping if slug is not empty
            if slug:
                mapping[slug] = name
        
        logger.info(f"Created default company mapping with {len(mapping)} entries")
        return mapping
    
    # Methods for tracking sent document notifications
    
    def _create_document_id(self, document: Dict[str, Any]) -> str:
        """Create a unique identifier for a document
        
        Args:
            document: Document information dictionary
            
        Returns:
            String hash identifier
        """
        company_id = document.get('company_id', '')
        doc = document.get('document', {})
        
        hash_content = "_".join([
            str(company_id),
            str(doc.get('title', '')),
            str(doc.get('url', '')),
            str(doc.get('date', ''))
        ])
        
        return hashlib.md5(hash_content.encode()).hexdigest()
    
    def initialize_document_tracking(self) -> None:
        """Initialize document tracking"""
        self.sent_documents_file = os.path.join(DATA_DIR, 'sent_documents.json')
        self.backup_sent_documents_file = os.path.join(DATA_DIR, 'sent_documents.json.bak')
        self.sent_documents: Set[str] = set()
        
        try:
            self._load_sent_documents()
        except Exception as e:
            logger.error(f"Error initializing document tracking: {e}", exc_info=True)
    
    def _load_sent_documents(self) -> None:
        """Load set of already sent document IDs"""
        try:
            if os.path.exists(self.sent_documents_file):
                with open(self.sent_documents_file, 'r') as f:
                    self.sent_documents = set(json.load(f))
                logger.info(f"Loaded {len(self.sent_documents)} sent document IDs")
                
                # Create backup if needed
                if not os.path.exists(self.backup_sent_documents_file):
                    with open(self.backup_sent_documents_file, 'w') as f:
                        json.dump(list(self.sent_documents), f)
            elif os.path.exists(self.backup_sent_documents_file):
                logger.warning("Main sent documents file not found, loading from backup")
                with open(self.backup_sent_documents_file, 'r') as f:
                    self.sent_documents = set(json.load(f))
                
                # Recreate main file
                with open(self.sent_documents_file, 'w') as f:
                    json.dump(list(self.sent_documents), f)
        except Exception as e:
            logger.error(f"Error loading sent documents: {e}", exc_info=True)
            self.sent_documents = set()
    
    def save_sent_document(self, document: Dict[str, Any]) -> None:
        """Mark a document as sent
        
        Args:
            document: Document information dictionary
        """
        try:
            document_id = self._create_document_id(document)
            self.sent_documents.add(document_id)
            
            # Save to both main and backup files
            for file_path in [self.sent_documents_file, self.backup_sent_documents_file]:
                with open(file_path, 'w') as f:
                    json.dump(list(self.sent_documents), f)
            
            logger.info(f"Saved sent document ID: {document_id}")
        except Exception as e:
            logger.error(f"Error saving sent document: {e}", exc_info=True)
    
    def is_document_sent(self, document: Dict[str, Any]) -> bool:
        """Check if a document has already been sent
        
        Args:
            document: Document information dictionary
            
        Returns:
            True if the document has already been sent, False otherwise
        """
        return self._create_document_id(document) in self.sent_documents