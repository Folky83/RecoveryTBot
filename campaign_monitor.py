#!/usr/bin/env python3
"""
Campaign Monitor for Mintos Telegram Bot

This standalone script checks for new Mintos campaigns every minute and sends
notifications via Telegram. It can be run independently from the main bot.

Usage:
    python campaign_monitor.py [--check-interval SECONDS]

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
from typing import Optional, Dict, Any, List
from datetime import datetime
import traceback

# Add the current directory to sys.path to ensure imports work properly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import bot modules
from bot.data_manager import DataManager
from bot.mintos_client import MintosClient
from bot.user_manager import UserManager
from bot.logger import setup_logger
from bot.config import TELEGRAM_TOKEN

# Import telegram components
from telegram import Bot
from telegram.error import TelegramError, RetryAfter

# Set up logging
logger = setup_logger("campaign_monitor")

class CampaignMonitor:
    """Monitor for Mintos campaigns with Telegram notifications"""
    
    def __init__(self, check_interval: int = 60):
        """Initialize the campaign monitor
        
        Args:
            check_interval: Check interval in seconds (default: 60)
        """
        self.check_interval = check_interval
        self.data_manager = DataManager()
        self.mintos_client = MintosClient()
        self.user_manager = UserManager()
        self.bot: Optional[Bot] = None
        self._failed_messages = []
        self.running = False
        
        # Verify TELEGRAM_TOKEN is set
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN environment variable not set")
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
        
        logger.info(f"Campaign monitor initialized with {check_interval}s check interval")
        
    async def initialize(self) -> None:
        """Initialize Telegram bot"""
        self.bot = Bot(token=TELEGRAM_TOKEN)
        
        # Verify connection to Telegram
        try:
            bot_info = await self.bot.get_me()
            logger.info(f"Connected to Telegram as {bot_info.username}")
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            raise
            
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
            import re
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
            
    async def send_message(self, chat_id: str, text: str, 
                         disable_web_page_preview: bool = False, 
                         parse_mode: Optional[str] = None) -> None:
        """Send a message to a Telegram chat
        
        Args:
            chat_id: Telegram chat ID
            text: Message text
            disable_web_page_preview: Whether to disable web page previews
            parse_mode: Parse mode for the message
        """
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
                    logger.error(f"Error sending message to {chat_id}: {e}", exc_info=True)
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
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    
    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    # Create monitor instance
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
    except Exception as e:
        logger.error(f"Fatal error: {traceback.format_exc()}")
        sys.exit(1)
    finally:
        # Ensure graceful shutdown
        if monitor.running:
            await monitor.stop()
        logger.info("Campaign monitor shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())