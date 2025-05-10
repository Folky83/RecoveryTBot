#!/usr/bin/env python3
"""
Standalone Campaign Monitor for Mintos Telegram Bot

This completely self-contained script checks for new Mintos campaigns every minute
and sends notifications via Telegram. It can be run independently without any
dependencies on the main bot code.

Usage:
    python standalone_campaign_monitor.py [--check-interval SECONDS]

Options:
    --check-interval SECONDS    Check interval in seconds (default: 60 seconds)
"""

import asyncio
import argparse
import logging
import os
import sys
import signal
import time
import json
import re
import hashlib
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timezone
import traceback
import requests

# Import telegram components
try:
    from telegram import Bot
    from telegram.error import TelegramError, RetryAfter
except ImportError:
    print("Error: python-telegram-bot package is required.")
    print("Please install it with: pip install python-telegram-bot")
    sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("campaign_monitor")

# Configuration - use normalized paths for cross-platform compatibility
DATA_DIR = "data"
CAMPAIGNS_FILE = os.path.normpath(os.path.join(DATA_DIR, "campaigns.json"))
SENT_CAMPAIGNS_FILE = os.path.normpath(os.path.join(DATA_DIR, "sent_campaigns.json"))
BACKUP_SENT_CAMPAIGNS_FILE = os.path.normpath(os.path.join(DATA_DIR, "sent_campaigns.json.bak"))
USERS_FILE = os.path.normpath(os.path.join(DATA_DIR, "users.json"))
MINTOS_CAMPAIGNS_URL = "https://www.mintos.com/webapp/api/en/webapp-api/user/campaigns"
REQUEST_DELAY = 0.1  # seconds between requests
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
REQUEST_TIMEOUT = 30  # seconds

# Default test user - used if no users.json exists
DEFAULT_USER_ID = "114691530"  # Default to bot creator's ID

# Telegram bot token - hardcoded for local use
TELEGRAM_BOT_TOKEN = "7368080976:AAE0vM2--epmISjYnrq5zvshFFBFiIvUS9M"

class UserManager:
    """Manages user registration and data"""
    
    def __init__(self):
        """Initialize the user manager"""
        self.users = {}
        self._ensure_data_directory()
        self._load_users()
        
    def _ensure_data_directory(self) -> None:
        """Ensure data directory exists"""
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info(f"Data directory checked: {DATA_DIR}")
        
    def _load_users(self) -> None:
        """Load users from file"""
        try:
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, 'r') as f:
                    self.users = json.load(f)
                logger.info(f"Loaded {len(self.users)} users")
            else:
                logger.warning(f"Users file not found at {USERS_FILE}")
                # Create a default users file with the bot creator's ID
                self.users = {DEFAULT_USER_ID: "default_user"}
                self.save_users()
                logger.info(f"Created default users file with user ID: {DEFAULT_USER_ID}")
        except Exception as e:
            logger.error(f"Error loading users: {e}")
            # Create a default user if there was an error
            self.users = {DEFAULT_USER_ID: "default_user"}
            
    def save_users(self) -> None:
        """Save users to file"""
        try:
            with open(USERS_FILE, 'w') as f:
                json.dump(self.users, f)
            logger.info(f"Users saved successfully: {self.users}")
            
            # Verify the file was written correctly
            with open(USERS_FILE, 'r') as f:
                content = f.read()
                logger.info(f"Verification - users.json contains: {content}")
        except Exception as e:
            logger.error(f"Error saving users: {e}")
            
    def add_user(self, user_id: str, username: Optional[str] = None) -> None:
        """Add or update a user"""
        self.users[user_id] = username
        self.save_users()
        logger.info(f"Added/updated user: {user_id} (username: {username})")
        
    def remove_user(self, user_id: str) -> None:
        """Remove a user"""
        if user_id in self.users:
            del self.users[user_id]
            self.save_users()
            logger.info(f"Removed user: {user_id}")
        else:
            logger.warning(f"Attempted to remove non-existent user: {user_id}")
            
    def get_all_users(self) -> List[str]:
        """Get all users"""
        return list(self.users.keys())
        
    def get_user_info(self, user_id: str) -> Optional[str]:
        """Get user information"""
        return self.users.get(user_id)

class DataManager:
    """Manages data persistence and caching"""
    
    def __init__(self):
        """Initialize the data manager"""
        self._sent_campaigns = set()
        self._ensure_data_directory()
        self._load_sent_campaigns()
        
    def _ensure_data_directory(self) -> None:
        """Ensure data directory exists"""
        os.makedirs(DATA_DIR, exist_ok=True)
        
    def _load_sent_campaigns(self) -> None:
        """Load set of already sent campaign IDs with verification and backup"""
        try:
            if os.path.exists(SENT_CAMPAIGNS_FILE):
                with open(SENT_CAMPAIGNS_FILE, 'r') as f:
                    data = json.load(f)
                    self._sent_campaigns = set(data)
                logger.info(f"Loaded {len(self._sent_campaigns)} sent campaign IDs")
            else:
                logger.warning(f"Sent campaigns file not found at {SENT_CAMPAIGNS_FILE}")
                self._sent_campaigns = set()
                
                # Create an empty file with proper structure
                with open(SENT_CAMPAIGNS_FILE, 'w') as f:
                    json.dump([], f)
                logger.info(f"Created empty sent campaigns file at {SENT_CAMPAIGNS_FILE}")
                
            # Create backup if file exists but no backup
            if os.path.exists(SENT_CAMPAIGNS_FILE) and not os.path.exists(BACKUP_SENT_CAMPAIGNS_FILE):
                logger.info("Creating backup of sent campaigns file")
                with open(SENT_CAMPAIGNS_FILE, 'r') as f:
                    data = f.read()
                with open(BACKUP_SENT_CAMPAIGNS_FILE, 'w') as f:
                    f.write(data)
        except Exception as e:
            logger.error(f"Error loading sent campaigns: {e}")
            
            # Try to recover from backup
            if os.path.exists(BACKUP_SENT_CAMPAIGNS_FILE):
                try:
                    logger.info("Attempting to recover sent campaigns from backup")
                    with open(BACKUP_SENT_CAMPAIGNS_FILE, 'r') as f:
                        data = json.load(f)
                        self._sent_campaigns = set(data)
                    logger.info(f"Recovered {len(self._sent_campaigns)} sent campaign IDs from backup")
                except Exception as backup_error:
                    logger.error(f"Failed to recover from backup: {backup_error}")
                    self._sent_campaigns = set()
                    
                    # Create a new empty file as last resort
                    with open(SENT_CAMPAIGNS_FILE, 'w') as f:
                        json.dump([], f)
                    logger.info(f"Created new empty sent campaigns file at {SENT_CAMPAIGNS_FILE}")
            else:
                self._sent_campaigns = set()
                
                # Create a new empty file as last resort
                with open(SENT_CAMPAIGNS_FILE, 'w') as f:
                    json.dump([], f)
                logger.info(f"Created new empty sent campaigns file at {SENT_CAMPAIGNS_FILE}")
                
    def save_sent_campaign(self, campaign: Dict[str, Any]) -> None:
        """Mark a campaign as sent with backup and timestamp"""
        campaign_id = self._create_campaign_id(campaign)
        
        if campaign_id:
            logger.debug(f"Marking campaign {campaign_id} as sent")
            self._sent_campaigns.add(campaign_id)
            
            # Save to file
            try:
                with open(SENT_CAMPAIGNS_FILE, 'w') as f:
                    json.dump(list(self._sent_campaigns), f)
                    
                # Create backup
                with open(BACKUP_SENT_CAMPAIGNS_FILE, 'w') as f:
                    json.dump(list(self._sent_campaigns), f)
                    
                logger.debug(f"Saved {len(self._sent_campaigns)} sent campaign IDs")
            except Exception as e:
                logger.error(f"Error saving sent campaigns: {e}")
                
    def is_campaign_sent(self, campaign: Dict[str, Any]) -> bool:
        """Check if a campaign has already been sent"""
        campaign_id = self._create_campaign_id(campaign)
        return campaign_id in self._sent_campaigns if campaign_id else False
        
    def _create_campaign_id(self, campaign: Dict[str, Any]) -> str:
        """Create a unique identifier for a campaign"""
        try:
            # Use campaign ID if available
            if 'id' in campaign:
                return str(campaign['id'])
                
            # Fallback to hash of name and validity period
            identifier = f"{campaign.get('name', '')}-{campaign.get('validFrom', '')}-{campaign.get('validTo', '')}"
            return hashlib.md5(identifier.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Error creating campaign ID: {e}")
            return ""
            
    def get_campaigns_cache_age(self) -> float:
        """Get age of campaigns cache in seconds"""
        try:
            if os.path.exists(CAMPAIGNS_FILE):
                file_modified_time = os.path.getmtime(CAMPAIGNS_FILE)
                current_time = time.time()
                age = current_time - file_modified_time
                logger.debug(f"Campaigns cache age: {age:.2f} seconds")
                return age
            return float('inf')  # Return infinity if file doesn't exist
        except Exception as e:
            logger.error(f"Error getting cache age: {e}")
            return float('inf')
            
    def load_previous_campaigns(self) -> List[Dict[str, Any]]:
        """Load previous campaigns from cache file"""
        try:
            if os.path.exists(CAMPAIGNS_FILE):
                with open(CAMPAIGNS_FILE, 'r') as f:
                    campaigns = json.load(f)
                logger.info(f"Loaded {len(campaigns)} campaigns from cache")
                return campaigns
            return []
        except Exception as e:
            logger.error(f"Error loading previous campaigns: {e}")
            return []
            
    def save_campaigns(self, campaigns: List[Dict[str, Any]]) -> None:
        """Save campaigns to cache file"""
        try:
            with open(CAMPAIGNS_FILE, 'w') as f:
                json.dump(campaigns, f)
            logger.info(f"Successfully saved {len(campaigns)} campaigns")
            logger.debug(f"Campaigns file size: {os.path.getsize(CAMPAIGNS_FILE)} bytes")
        except Exception as e:
            logger.error(f"Error saving campaigns: {e}")
            
    def compare_campaigns(self, new_campaigns: List[Dict[str, Any]], 
                        previous_campaigns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compare campaigns to find new or updated ones"""
        logger.debug(f"Comparing {len(new_campaigns)} new campaigns with {len(previous_campaigns)} previous campaigns")
        
        # If there were no previous campaigns, all are new
        if not previous_campaigns:
            logger.info(f"Found {len(new_campaigns)} new campaigns (no previous campaigns)")
            return new_campaigns
            
        added_campaigns = []
        prev_campaigns_map = {self._create_campaign_id(c): c for c in previous_campaigns if self._create_campaign_id(c)}
        
        for new_campaign in new_campaigns:
            campaign_id = self._create_campaign_id(new_campaign)
            if not campaign_id:
                continue
                
            # Check if campaign is new or updated
            if campaign_id not in prev_campaigns_map:
                logger.debug(f"Found new campaign: {campaign_id}")
                added_campaigns.append(new_campaign)
            elif not self._are_campaigns_identical(new_campaign, prev_campaigns_map[campaign_id]):
                logger.debug(f"Found updated campaign: {campaign_id}")
                added_campaigns.append(new_campaign)
                
        logger.info(f"Found {len(added_campaigns)} new or updated campaigns")
        return added_campaigns
        
    def _are_campaigns_identical(self, new_campaign: Dict[str, Any], 
                               prev_campaign: Dict[str, Any]) -> bool:
        """Compare two campaigns for equality in significant fields"""
        try:
            # Define which fields we consider significant for comparison
            significant_fields = [
                'name', 'shortDescription', 'validFrom', 'validTo', 
                'bonusAmount', 'requiredPrincipalExposure', 
                'additionalBonusEnabled', 'bonusCoefficient'
            ]
            
            for field in significant_fields:
                if new_campaign.get(field) != prev_campaign.get(field):
                    logger.debug(f"Field '{field}' differs: {new_campaign.get(field)} vs {prev_campaign.get(field)}")
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"Error comparing campaigns: {e}")
            return False  # Conservative approach: if error, treat as different

class MintosClient:
    """Client for the Mintos API"""
    
    def __init__(self):
        """Initialize the client"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.mintos.com/en/',
            'Origin': 'https://www.mintos.com'
        })
        
    def _make_request(self, url: str) -> Optional[Any]:
        """Make a request to the Mintos API with retries"""
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Making request to {url} (attempt {attempt + 1}/{MAX_RETRIES})")
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)
                time.sleep(REQUEST_DELAY)  # Avoid rate limiting
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"Request failed with status code {response.status_code}: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {e}")
                
            # Wait before retry
            logger.debug(f"Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)
            
        logger.error(f"Failed to make request to {url} after {MAX_RETRIES} attempts")
        return None
        
    def get_campaigns(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch current Mintos campaigns"""
        response = self._make_request(MINTOS_CAMPAIGNS_URL)
        
        if response:
            logger.info(f"Successfully retrieved {len(response)} campaigns")
            return response
            
        logger.error(f"Failed to get campaigns after {MAX_RETRIES} attempts")
        return None

class CampaignMonitor:
    """Monitor for Mintos campaigns with Telegram notifications"""
    
    def __init__(self, check_interval: int = 60):
        """Initialize the campaign monitor"""
        self.check_interval = check_interval
        self.data_manager = DataManager()
        self.mintos_client = MintosClient()
        self.user_manager = UserManager()
        self.bot: Optional[Bot] = None
        self._failed_messages = []
        self.running = False
        
        # Use the hardcoded token variable
        self.telegram_token = TELEGRAM_BOT_TOKEN
        if not self.telegram_token:
            logger.error("Telegram bot token not available")
            raise ValueError("The hardcoded Telegram bot token is not valid. Please check the TELEGRAM_BOT_TOKEN value in the script.")
            
        logger.info(f"Campaign monitor initialized with {check_interval}s check interval")
        
    async def initialize(self) -> None:
        """Initialize Telegram bot"""
        self.bot = Bot(token=self.telegram_token)
        
        # Verify connection to Telegram
        try:
            bot_info = await self.bot.get_me()
            logger.info(f"Connected to Telegram as {bot_info.username}")
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            raise
            
    def _is_campaign_active(self, campaign: Dict[str, Any]) -> bool:
        """Check if a campaign is currently active based on its dates"""
        try:
            valid_from = campaign.get('validFrom')
            valid_to = campaign.get('validTo')
            
            if not valid_from or not valid_to:
                # Default to active if dates aren't provided
                return True
                
            # Convert string dates to datetime objects
            from_date = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
            to_date = datetime.fromisoformat(valid_to.replace('Z', '+00:00'))
            
            # Get current time in UTC
            now = datetime.now(timezone.utc)
            
            # Check if current time is within the campaign validity period
            return from_date <= now <= to_date
        except Exception as e:
            logger.warning(f"Error checking campaign activity: {e}")
            # Default to active if there's an error parsing dates
            return True
            
    async def format_campaign_message(self, campaign: Dict[str, Any]) -> str:
        """Format campaign message with rich information from Mintos API"""
        logger.debug(f"Formatting campaign message for ID: {campaign.get('id')}")

        # Set up the header
        message = "🎯 <b>Mintos Campaign</b>\n\n"

        # Name (some campaigns have no name)
        if campaign.get('name'):
            message += f"<b>{campaign.get('name')}</b>\n\n"

        # Campaign type information
        campaign_type = campaign.get('type')
        if campaign_type == 1:
            message += "📱 <b>Type:</b> Refer a Friend\n"
        elif campaign_type == 2:
            message += "💰 <b>Type:</b> Cashback\n"
        elif campaign_type == 4:
            message += "🌟 <b>Type:</b> Special Promotion\n"
        else:
            message += f"📊 <b>Type:</b> Campaign (Type {campaign_type})\n"

        # Validity period
        valid_from = campaign.get('validFrom')
        valid_to = campaign.get('validTo')
        if valid_from and valid_to:
            # Parse and format the dates (example format: "2025-01-31T22:00:00.000000Z")
            try:
                from_date = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                to_date = datetime.fromisoformat(valid_to.replace('Z', '+00:00'))
                message += f"📅 <b>Valid:</b> {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}\n"
            except ValueError:
                # Fallback if date parsing fails
                message += f"📅 <b>Valid:</b> {valid_from} to {valid_to}\n"

        # Bonus amount
        if campaign.get('bonusAmount'):
            try:
                # Handle European number formatting (period as thousands separator)
                bonus_text = campaign.get('bonusAmount')

                # Try to convert to float and handle formatting properly
                try:
                    # If it's a number with thousands separator like "50.000"
                    if '.' in bonus_text and not bonus_text.endswith('0'):
                        # Check if it's likely a thousands separator (should end with 3 digits after period)
                        parts = bonus_text.split('.')
                        if len(parts) == 2 and len(parts[1]) == 3:
                            # This is likely a thousands separator, replace with empty string
                            bonus_value = float(bonus_text.replace('.', ''))
                            message += f"🎁 <b>Bonus:</b> €{int(bonus_value)}\n"
                        else:
                            # Keep as is
                            message += f"🎁 <b>Bonus:</b> €{bonus_text}\n"
                    else:
                        # Normal case - try to convert to float
                        bonus_value = float(bonus_text)
                        if bonus_value.is_integer():
                            message += f"🎁 <b>Bonus:</b> €{int(bonus_value)}\n"
                        else:
                            message += f"🎁 <b>Bonus:</b> €{bonus_value:.2f}\n"
                except ValueError:
                    # If conversion fails, just use the original text
                    message += f"🎁 <b>Bonus:</b> €{bonus_text}\n"
            except Exception:
                # Fallback to original value if any error occurs
                message += f"🎁 <b>Bonus:</b> €{campaign.get('bonusAmount')}\n"

        # Required investment
        if campaign.get('requiredPrincipalExposure'):
            try:
                required_amount = float(campaign.get('requiredPrincipalExposure'))
                message += f"💸 <b>Required Investment:</b> €{required_amount:,.2f}\n"
            except (ValueError, TypeError):
                message += f"💸 <b>Required Investment:</b> {campaign.get('requiredPrincipalExposure')}\n"

        # Additional bonus information
        if campaign.get('additionalBonusEnabled'):
            message += f"✨ <b>Extra Bonus:</b> {campaign.get('bonusCoefficient', '?')}%"
            if campaign.get('additionalBonusDays'):
                message += f" (for first {campaign.get('additionalBonusDays')} days)\n"
            else:
                message += "\n"

        # Description if available
        if campaign.get('shortDescription'):
            # Clean HTML tags and safely handle entity references
            description = campaign.get('shortDescription', '')

            # First, handle escaped characters
            description = description.replace('\u003C', '<').replace('\u003E', '>')

            # Handle common HTML entities
            description = (description
                .replace('&#39;', "'")
                .replace('&rsquo;', "'")
                .replace('&euro;', '€')
                .replace('&nbsp;', ' ')
                .replace('&lt;', '<')
                .replace('&gt;', '>')
                .replace('&amp;', '&'))

            # Replace common line-breaking tags with newlines first
            description = (description
                .replace('<br>', '\n')
                .replace('<br/>', '\n')
                .replace('<br />', '\n')
                .replace('</p>', '\n')
                .replace('</div>', '\n')
                .replace('</li>', '\n'))

            # Special handling for list items to preserve formatting
            description = description.replace('<li>', '• ')

            # Strip all remaining HTML tags
            description = re.sub(r'<[^>]*>', '', description)

            # Clean up whitespace
            description = description.strip()
            description = re.sub(r'\n{3,}', '\n\n', description)  # Replace 3+ newlines with 2
            description = re.sub(r'\s{2,}', ' ', description)      # Replace 2+ spaces with 1

            # Add to message
            message += f"\n📝 <b>Description:</b>\n{description}\n"

        # Terms and conditions link
        if campaign.get('termsConditionsLink'):
            message += f"\n📜 <a href='{campaign.get('termsConditionsLink')}'>Terms & Conditions</a>\n"

        # Add link to campaigns page
        message += f"\n🔗 <a href='https://www.mintos.com/en/campaigns/'>View on Mintos</a>"

        return message.strip()
            
    async def send_message(self, chat_id: str, text: str, 
                         disable_web_page_preview: bool = False, 
                         parse_mode: Optional[str] = None) -> None:
        """Send a message to a Telegram chat"""
        if not self.bot:
            logger.error("Bot not initialized")
            raise RuntimeError("Bot not initialized")
            
        max_retries = 3
        base_delay = 1.0
        
        # Calculate delay based on message length
        message_length = len(text)
        adaptive_delay = min(2.0 + (message_length / 1000), 5.0)  # Max 5 second delay for very long messages
        
        for attempt in range(max_retries):
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode or 'HTML',
                    disable_web_page_preview=disable_web_page_preview
                )
                logger.debug(f"Message sent successfully to {chat_id} (length: {message_length} chars)")
                logger.debug(f"Waiting {adaptive_delay}s before next message")
                # Adaptive delay after successful send based on message length
                await asyncio.sleep(adaptive_delay)
                return
                
            except RetryAfter as e:
                # Telegram rate limit - wait the required time plus a small buffer
                wait_time = e.retry_after + 0.5
                logger.warning(f"Rate limited by Telegram. Waiting {wait_time} seconds")
                await asyncio.sleep(wait_time)
                # Try again immediately after waiting
                continue
                
            except TelegramError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Error sending message to {chat_id}: {e}")
                    # Store failed message for later retry
                    self._failed_messages.append({
                        'chat_id': chat_id,
                        'text': text,
                        'parse_mode': parse_mode,
                        'disable_web_page_preview': disable_web_page_preview
                    })
                    raise
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Telegram error, retrying in {delay} seconds: {e}")
                await asyncio.sleep(delay)
                
    async def retry_failed_messages(self) -> None:
        """Retry sending failed messages"""
        if not self._failed_messages:
            return
            
        logger.info(f"Attempting to resend {len(self._failed_messages)} failed messages")
        retry_messages = self._failed_messages.copy()
        self._failed_messages.clear()
        
        for msg in retry_messages:
            try:
                await self.send_message(
                    msg['chat_id'],
                    msg['text'],
                    msg.get('disable_web_page_preview', True),
                    msg.get('parse_mode', 'HTML')
                )
                logger.info(f"Successfully resent message to {msg['chat_id']}")
            except Exception as e:
                logger.error(f"Failed to resend message: {e}")
                self._failed_messages.append(msg)
                
    async def check_campaigns(self) -> None:
        """Check for new Mintos campaigns and send notifications"""
        try:
            logger.info("Checking for new campaigns...")
            
            # Get cache file age before update
            campaigns_cache_age = self.data_manager.get_campaigns_cache_age()
            logger.info(f"Campaigns cache age: {campaigns_cache_age/3600:.1f} hours")
            
            # Load previous campaigns
            previous_campaigns = self.data_manager.load_previous_campaigns()
            logger.info(f"Loaded {len(previous_campaigns)} previous campaigns")
            
            # Fetch new campaigns
            new_campaigns = self.mintos_client.get_campaigns()
            if not new_campaigns:
                logger.warning("Failed to fetch campaigns or no campaigns available")
                return
                
            logger.info(f"Fetched {len(new_campaigns)} new campaigns from API")
            
            # Compare campaigns
            added_campaigns = self.data_manager.compare_campaigns(new_campaigns, previous_campaigns)
            logger.info(f"Found {len(added_campaigns)} new or updated campaigns after comparison")
            
            if added_campaigns:
                users = self.user_manager.get_all_users()
                logger.info(f"Found {len(added_campaigns)} new campaigns to process for {len(users)} users")
                
                # Filter out Special Promotion (type 4) campaigns and unsent campaigns
                unsent_campaigns = [
                    campaign for campaign in added_campaigns 
                    if not self.data_manager.is_campaign_sent(campaign) and campaign.get('type') != 4
                ]
                logger.info(f"Found {len(unsent_campaigns)} unsent campaigns")
                
                if unsent_campaigns:
                    # Filter active campaigns
                    active_campaigns = [
                        campaign for campaign in unsent_campaigns
                        if self._is_campaign_active(campaign)
                    ]
                    
                    if active_campaigns:
                        logger.info(f"Sending {len(active_campaigns)} active unsent campaigns to {len(users)} users")
                        
                        # Send notification about the number of new campaigns
                        if len(active_campaigns) > 1:
                            header_message = f"🎯 Found {len(active_campaigns)} new Mintos campaigns!"
                            for user_id in users:
                                try:
                                    await self.send_message(user_id, header_message, disable_web_page_preview=True)
                                except Exception as e:
                                    logger.error(f"Failed to send header message to user {user_id}: {e}")
                        
                        # Send each campaign
                        for i, campaign in enumerate(active_campaigns):
                            try:
                                message = await self.format_campaign_message(campaign)
                                
                                for user_id in users:
                                    try:
                                        await self.send_message(user_id, message, disable_web_page_preview=True)
                                        logger.info(f"Successfully sent campaign {i+1}/{len(active_campaigns)} to user {user_id}")
                                    except Exception as e:
                                        logger.error(f"Failed to send campaign to user {user_id}: {e}")
                                        
                                # Mark campaign as sent regardless of individual user failures
                                self.data_manager.save_sent_campaign(campaign)
                            except Exception as e:
                                logger.error(f"Error formatting or sending campaign {campaign.get('id')}: {e}")
                    else:
                        logger.info("Found new campaigns but none are currently active")
                else:
                    logger.info("No new unsent campaigns to send")
                    
            # Save campaigns to file
            try:
                self.data_manager.save_campaigns(new_campaigns)
                logger.info(f"Successfully saved {len(new_campaigns)} campaigns")
            except Exception as e:
                logger.error(f"Error saving campaigns: {e}")
                
            logger.info(f"Campaign check completed. Found {len(added_campaigns)} new campaigns.")
            
        except Exception as e:
            logger.error(f"Error during campaign check: {e}", exc_info=True)
            for user_id in self.user_manager.get_all_users():
                try:
                    await self.send_message(user_id, "⚠️ Error occurred while checking for campaigns", disable_web_page_preview=True)
                except Exception as nested_e:
                    logger.error(f"Failed to send error notification to user {user_id}: {nested_e}")
                    
    async def run(self) -> None:
        """Run the campaign monitor loop"""
        try:
            # Initialize the bot
            await self.initialize()
            
            # Set running flag
            self.running = True
            
            logger.info(f"Campaign monitor started with {self.check_interval}s check interval")
            
            # Send startup notification to all users
            users = self.user_manager.get_all_users()
            startup_msg = "🚀 Campaign monitor started. Will check for new Mintos campaigns every minute."
            
            for user_id in users:
                try:
                    await self.send_message(user_id, startup_msg, disable_web_page_preview=True)
                except Exception as e:
                    logger.warning(f"Failed to send startup message to user {user_id}: {e}")
            
            # Main monitoring loop
            last_check_time = 0
            
            while self.running:
                try:
                    current_time = time.time()
                    elapsed = current_time - last_check_time
                    
                    # Check if it's time to check for campaigns
                    if elapsed >= self.check_interval:
                        await self.check_campaigns()
                        last_check_time = time.time()
                        
                        # Try to resend any failed messages
                        await self.retry_failed_messages()
                    
                    # Sleep for a short time to prevent high CPU usage
                    await asyncio.sleep(1)
                    
                except asyncio.CancelledError:
                    logger.info("Monitor task cancelled")
                    break
                    
                except Exception as e:
                    logger.error(f"Error in monitor loop: {e}", exc_info=True)
                    # Sleep a bit longer after errors to prevent rapid failure loops
                    await asyncio.sleep(10)
                    
        except Exception as e:
            logger.error(f"Fatal error in campaign monitor: {e}", exc_info=True)
            raise
            
        finally:
            self.running = False
            logger.info("Campaign monitor stopped")
    
    async def stop(self) -> None:
        """Stop the campaign monitor"""
        logger.info("Stopping campaign monitor...")
        self.running = False

def signal_handler(monitor, loop):
    """Handle termination signals"""
    def _handle_signal(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        if monitor and monitor.running:
            asyncio.run_coroutine_threadsafe(monitor.stop(), loop)
    return _handle_signal

async def main() -> None:
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Mintos Campaign Monitor")
    parser.add_argument("--check-interval", type=int, default=60,
                      help="Check interval in seconds (default: 60)")
    args = parser.parse_args()
    
    # Create data directory if it doesn't exist
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Create monitor instance
    try:
        monitor = CampaignMonitor(check_interval=args.check_interval)
        
        # Set up signal handlers
        loop = asyncio.get_event_loop()
        handler = signal_handler(monitor, loop)
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)
        
        try:
            # Run the monitor
            await monitor.run()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            # Ensure graceful shutdown
            if monitor.running:
                await monitor.stop()
            logger.info("Campaign monitor shutdown complete")
    except ValueError as e:
        # Handle token error gracefully
        logger.error(f"Error: {e}")
        print(f"\nERROR: {e}")
        print("\nThere was a problem with the Telegram bot token.")
        print("Please check that the hardcoded token in the script is valid.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {traceback.format_exc()}")
        print(f"\nFatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())