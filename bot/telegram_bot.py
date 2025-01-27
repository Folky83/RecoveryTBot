import asyncio
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError
import time
import datetime
import math
from .logger import setup_logger
from .config import TELEGRAM_TOKEN
from .data_manager import DataManager
from .mintos_client import MintosClient
from .user_manager import UserManager

logger = setup_logger(__name__)

class MintosBot:
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    _polling_task = None
    _update_task = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    def __init__(self):
        if not self._initialized:
            logger.info("Initializing Mintos Bot...")
            if not TELEGRAM_TOKEN:
                raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

            self.application = None
            self.data_manager = DataManager()
            self.mintos_client = MintosClient()
            self.user_manager = UserManager()
            self._initialized = True
            logger.info("Bot instance created")

    async def cleanup(self):
        """Cleanup bot resources"""
        try:
            logger.info("Starting cleanup process...")

            # Cancel running tasks first
            if self._polling_task and not self._polling_task.done():
                self._polling_task.cancel()
                try:
                    await self._polling_task
                except asyncio.CancelledError:
                    pass
                self._polling_task = None

            if self._update_task and not self._update_task.done():
                self._update_task.cancel()
                try:
                    await self._update_task
                except asyncio.CancelledError:
                    pass
                self._update_task = None

            if self.application:
                try:
                    # Stop the updater if it's running
                    if hasattr(self.application, 'updater') and self.application.updater.running:
                        await self.application.updater.stop()
                        await asyncio.sleep(1)

                    # Clean up webhook and updates
                    if hasattr(self.application, 'bot'):
                        await self.application.bot.delete_webhook(drop_pending_updates=True)
                        await self.application.bot.get_updates(offset=-1)

                    # Stop and shutdown the application
                    try:
                        await self.application.stop()
                    except Exception:
                        pass
                    try:
                        await self.application.shutdown()
                    except Exception:
                        pass

                    self.application = None
                    self._initialized = False
                except Exception as e:
                    logger.error(f"Error during application cleanup: {e}")

            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

    async def initialize(self):
        """Initialize bot application with proper cleanup"""
        async with self._lock:
            try:
                # Always cleanup existing instance
                await self.cleanup()
                await asyncio.sleep(2)  # Give time for cleanup

                # Create new application instance
                self.application = Application.builder().token(TELEGRAM_TOKEN).build()

                # Clean up any existing webhooks and updates
                await self.application.bot.delete_webhook(drop_pending_updates=True)
                await self.application.bot.get_updates(offset=-1)

                # Register handlers
                self.application.add_handler(CommandHandler("start", self.start_command))
                self.application.add_handler(CommandHandler("company", self.company_command))
                self.application.add_handler(CommandHandler("today", self.today_command))
                self.application.add_handler(CommandHandler("refresh", self.refresh_command))
                self.application.add_handler(CallbackQueryHandler(self.handle_callback))

                self._initialized = True
                logger.info("Bot initialized and handlers registered")
                return True
            except Exception as e:
                logger.error(f"Error during bot initialization: {e}", exc_info=True)
                return False

    async def scheduled_updates(self):
        """Handle scheduled updates"""
        while True:
            try:
                if await self.should_check_updates():
                    logger.info("Running scheduled update check")
                    try:
                        await asyncio.sleep(1)  # Small delay to avoid conflicts
                        await self.check_updates()
                        logger.info("Update check completed")
                        await asyncio.sleep(55 * 60)  # Wait 55 minutes before next check
                    except Exception as check_error:
                        logger.error(f"Error in update check: {check_error}", exc_info=True)
                        await asyncio.sleep(60)  # Wait before retry
                else:
                    await asyncio.sleep(5 * 60)  # Check every 5 minutes
            except asyncio.CancelledError:
                logger.info("Scheduled updates task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in scheduled updates: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retry

    async def run(self):
        """Run the bot with both polling and scheduled updates"""
        logger.info("Starting Mintos Update Bot")
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Ensure clean state
                await self.cleanup()
                await asyncio.sleep(2)

                # Initialize bot
                if not await self.initialize():
                    raise Exception("Failed to initialize bot")

                # Start polling
                await self.application.initialize()
                await self.application.start()

                # Only create one polling task
                self._polling_task = asyncio.create_task(
                    self.application.updater.start_polling(
                        drop_pending_updates=True,
                        allowed_updates=["message", "callback_query"]
                    )
                )

                # Create scheduled updates task
                self._update_task = asyncio.create_task(self.scheduled_updates())

                # Wait for both tasks
                await asyncio.gather(self._polling_task, self._update_task)
                return

            except Exception as e:
                logger.error(f"Error in main run loop: {e}", exc_info=True)
                retry_count += 1
                if retry_count < max_retries:
                    logger.info(f"Retrying bot startup (attempt {retry_count + 1}/{max_retries})...")
                    await asyncio.sleep(5)
                else:
                    logger.error("Max retries reached, shutting down...")
                    raise
            finally:
                await self.cleanup()

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command - register new users"""
        try:
            chat_id = update.effective_chat.id
            user = update.effective_user
            logger.info(f"Received /start command from user {user.username} (chat_id: {chat_id})")

            self.user_manager.add_user(str(chat_id))
            welcome_message = (
                "🚀 Welcome to Mintos Update Bot!\n\n"
                "📅 Update Schedule:\n"
                "• Automatic updates on weekdays at 4 PM, 5 PM, and 6 PM\n\n"
                "Available Commands:\n"
                "• /company - Check updates for a specific company\n"
                "• /today - View all updates from today\n"
                "• /refresh - Force an immediate update check\n"
                "• /start - Show this welcome message\n\n"
                "You'll receive updates about lending companies automatically. Stay tuned!"
            )
            await self.send_message(chat_id, welcome_message)
            logger.info(f"User {user.username} successfully registered")

        except Exception as e:
            logger.error(f"Error in start_command: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error processing your command. Please try again.")
            raise

    async def company_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /company command - display company selection menu with live data"""
        try:
            chat_id = update.effective_chat.id
            company_buttons = []
            # Create buttons for each company, 2 per row
            companies = sorted(self.data_manager.company_names.items(), key=lambda x: x[1])
            for i in range(0, len(companies), 2):
                row = []
                for company_id, company_name in companies[i:i+2]:
                    row.append(InlineKeyboardButton(
                        company_name,
                        callback_data=f"company_{company_id}"
                    ))
                company_buttons.append(row)

            # Add cancel button as the last row
            company_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
            reply_markup = InlineKeyboardMarkup(company_buttons)
            await update.message.reply_text(
                "Select a company to view updates:",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error in company_command: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error displaying company list. Please try again.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboard buttons"""
        try:
            query = update.callback_query
            await query.answer()

            if query.data.startswith("company_"):
                company_id = int(query.data.split("_")[1])
                company_name = self.data_manager.get_company_name(company_id)

                # Show update type selection
                buttons = [
                    [InlineKeyboardButton("Latest Update", callback_data=f"latest_{company_id}")],
                    [InlineKeyboardButton("All Updates", callback_data=f"all_{company_id}_0")]  # Added page number
                ]
                reply_markup = InlineKeyboardMarkup(buttons)
                await query.edit_message_text(
                    f"Select update type for {company_name}:",
                    reply_markup=reply_markup
                )

            elif query.data == "cancel":
                await query.edit_message_text("Operation cancelled.")
                return

            elif query.data.startswith(("latest_", "all_")):
                parts = query.data.split("_")
                update_type = parts[0]
                company_id = int(parts[1])
                page = int(parts[2]) if len(parts) > 2 else 0
                company_name = self.data_manager.get_company_name(company_id)

                # Show fetching message
                await query.edit_message_text(f"Fetching latest data for {company_name}...")

                # Always fetch fresh data for the specific company
                company_updates = self.mintos_client.get_recovery_updates(company_id)
                if company_updates:
                    company_updates = {"lender_id": company_id, **company_updates}
                    # Save to cache for other commands to use
                    cached_updates = self.data_manager.load_previous_updates()
                    updated = False
                    for i, update in enumerate(cached_updates):
                        if update.get('lender_id') == company_id:
                            cached_updates[i] = company_updates
                            updated = True
                            break
                    if not updated:
                        cached_updates.append(company_updates)
                    self.data_manager.save_updates(cached_updates)

                if not company_updates:
                    await query.edit_message_text(f"No updates found for {company_name}")
                    return

                if update_type == "latest":
                    # Get the most recent update
                    latest_update = {"lender_id": company_id, "company_name": company_name}
                    if "items" in company_updates and company_updates["items"]:
                        latest_year = company_updates["items"][0]
                        if "items" in latest_year and latest_year["items"]:
                            latest_item = latest_year["items"][0]
                            latest_update.update(latest_item)
                    message = self.format_update_message(latest_update)
                    await query.edit_message_text(message, parse_mode='HTML')

                else:  # all updates
                    messages = []
                    for year_data in sorted(company_updates.get("items", []), key=lambda x: x.get('year', 0), reverse=True):
                        # Sort updates within each year by date, newest first
                        year_items = sorted(year_data.get("items", []), 
                                             key=lambda x: datetime.datetime.strptime(x.get('date', '1900-01-01'), '%Y-%m-%d'),
                                             reverse=True)
                        for update_item in year_items:
                            update_with_company = {
                                "lender_id": company_id,
                                "company_name": company_name,
                                **update_item
                            }
                            messages.append(self.format_update_message(update_with_company))

                    # Calculate total pages and current page bounds
                    updates_per_page = 5
                    total_updates = len(messages)
                    total_pages = (total_updates + updates_per_page - 1) // updates_per_page

                    # Validate page number
                    if page >= total_pages:
                        page = total_pages - 1
                    if page < 0:
                        page = 0

                    start_idx = page * updates_per_page
                    end_idx = min(start_idx + updates_per_page, total_updates)

                    # Send header with page info
                    header_message = (
                        f"📊 Updates for {company_name}\n"
                        f"Page {page + 1} of {total_pages}\n"
                        f"Showing updates {start_idx + 1}-{end_idx} of {total_updates}"
                    )
                    await self.send_message(query.message.chat_id, header_message)

                    # Get current page updates
                    current_page_updates = messages[start_idx:end_idx]

                    # Send updates for current page
                    for message in current_page_updates:
                        await self.send_message(query.message.chat_id, message)

                    # Create navigation buttons
                    nav_buttons = []
                    if page > 0:  # Show Previous button if not on first page
                        nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"all_{company_id}_{page-1}"))
                    if page < total_pages - 1:  # Show Next button if not on last page
                        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"all_{company_id}_{page+1}"))

                    # If there are navigation buttons, send them
                    if nav_buttons:
                        reply_markup = InlineKeyboardMarkup([nav_buttons])
                        await self.send_message(
                            query.message.chat_id,
                            "Navigate through updates:",
                            reply_markup=reply_markup
                        )

        except Exception as e:
            logger.error(f"Error in handle_callback: {e}", exc_info=True)
            await query.edit_message_text("⚠️ Error processing your request. Please try again.")

    async def send_message(self, chat_id, text, reply_markup=None):
        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            logger.debug(f"Message sent successfully to {chat_id}")
        except TelegramError as e:
            logger.error(f"Error sending message to {chat_id}: {e}", exc_info=True)
            logger.error(f"Full error details - Type: {type(e)}, Message: {str(e)}")
            raise

    def format_update_message(self, update):
        """Format update message with rich information from Mintos API"""
        logger.debug(f"Formatting update message for: {update.get('company_name')}")
        company_name = update.get('company_name', 'Unknown Company')
        message = f"🏢 <b>{company_name}</b>\n"

        # Add date and year if available
        if 'date' in update:
            message += f"📅 Date: {update['date']}\n"
            if 'year' in update:
                message += f"Year: {update['year']}\n"

        # Add status information
        if 'status' in update:
            status = update['status'].replace('_', ' ').title()
            message += f"📊 Status: {status}\n"
            if update.get('substatus'):
                substatus = update['substatus'].replace('_', ' ').title()
                message += f"Sub-status: {substatus}\n"

        # Add recovery information with proper formatting
        if any(key in update for key in ['recoveredAmount', 'remainingAmount', 'expectedRecoveryTo', 'expectedRecoveryFrom']):
            message += "\n💰 Recovery Information:\n"

            # Handle recovered and remaining amounts as Euro values
            if update.get('recoveredAmount'):
                amount = round(float(update['recoveredAmount']))
                message += f"• Recovered: €{amount:,}\n"
            if update.get('remainingAmount'):
                amount = round(float(update['remainingAmount']))
                message += f"• Remaining: €{amount:,}\n"

            # Handle expected recovery - always as percentage
            if update.get('expectedRecoveryFrom') and update.get('expectedRecoveryTo'):
                from_percentage = round(float(update['expectedRecoveryFrom']))
                to_percentage = round(float(update['expectedRecoveryTo']))
                message += f"• Expected Recovery: {from_percentage}% - {to_percentage}%\n"
            elif update.get('expectedRecoveryTo'):
                percentage = round(float(update['expectedRecoveryTo']))
                message += f"• Expected Recovery: Up to {percentage}%\n"

        # Add recovery timeline
        if any(key in update for key in ['expectedRecoveryYearFrom', 'expectedRecoveryYearTo']):
            timeline = ""
            if update.get('expectedRecoveryYearFrom') and update.get('expectedRecoveryYearTo'):
                timeline = f"{update['expectedRecoveryYearFrom']} - {update['expectedRecoveryYearTo']}"
            elif update.get('expectedRecoveryYearTo'):
                timeline = str(update['expectedRecoveryYearTo'])

            if timeline:
                message += f"📆 Expected Recovery Timeline: {timeline}\n"

        # Add description with proper HTML entity handling
        if 'description' in update:
            description = update['description']
            description = (description
                .replace('\u003C', '<')
                .replace('\u003E', '>')
                .replace('&#39;', "'")
                .replace('&rsquo;', "'")
                .replace('&euro;', '€')
                .replace('<p>', '')
                .replace('</p>', '\n')
                .strip())
            message += f"\n📝 Details:\n{description}\n"

        # Add Mintos link
        if 'lender_id' in update:
            message += f"\n🔗 <a href='https://www.mintos.com/en/loan-companies/{update['lender_id']}'>View on Mintos</a>"

        return message.strip()

    async def check_updates(self):
        try:
            logger.info("Starting update check...")
            # Get previous updates
            previous_updates = self.data_manager.load_previous_updates()

            # Fetch new updates
            lender_ids = [int(id) for id in self.data_manager.company_names.keys()]
            new_updates = self.mintos_client.fetch_all_updates(lender_ids)

            # Compare and get new updates
            added_updates = self.data_manager.compare_updates(new_updates, previous_updates)

            # Send notifications to all users
            if added_updates:
                users = self.user_manager.get_all_users()
                logger.info(f"Sending {len(added_updates)} updates to {len(users)} users")
                for update in added_updates:
                    message = self.format_update_message(update)
                    for user_id in users:
                        try:
                            await self.send_message(user_id, message)
                        except Exception as e:
                            logger.error(f"Failed to send update to user {user_id}: {e}")

            # Save new updates
            self.data_manager.save_updates(new_updates)
            logger.info(f"Update check completed. Found {len(added_updates)} new updates.")

        except Exception as e:
            logger.error(f"Error during update check: {e}", exc_info=True)
            # Notify all users about the error
            for user_id in self.user_manager.get_all_users():
                try:
                    await self.send_message(user_id, "⚠️ Error occurred while checking for updates")
                except Exception as nested_e:
                    logger.error(f"Failed to send error notification to user {user_id}: {nested_e}")

    async def start_polling(self):
        """Start the bot in polling mode with proper error handling"""
        try:
            logger.info("Starting bot polling")
            # Make sure we're initialized
            if not self._initialized:
                await self.initialize()

            # Double-check no webhook exists
            await self.application.bot.delete_webhook(drop_pending_updates=True)
            # Clear any pending updates
            await self.application.bot.get_updates(offset=-1)

            # Initialize and start application
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()

            logger.info("Bot polling started successfully")
        except Exception as e:
            logger.error(f"Error starting polling: {e}", exc_info=True)
            await self.cleanup()  # Cleanup on error
            raise

    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /today command - show today's updates from cache"""
        try:
            chat_id = update.effective_chat.id

            # Load updates from cache
            updates = self.data_manager.load_previous_updates()
            cache_age = self.data_manager.get_cache_age()
            logger.debug(f"Using cached data (age: {cache_age:.0f} seconds)")

            today = time.strftime("%Y-%m-%d")

            today_updates = []
            for company_update in updates:
                if "items" in company_update:
                    lender_id = company_update.get('lender_id')
                    company_name = self.data_manager.get_company_name(lender_id)

                    for year_data in company_update["items"]:
                        for item in year_data.get("items", []):
                            if item.get('date') == today:
                                update_with_company = {
                                    "lender_id": lender_id,
                                    "company_name": company_name,
                                    **year_data,
                                    **item
                                }
                                today_updates.append(update_with_company)

            if not today_updates:
                cache_message = ""
                if math.isinf(cache_age):
                    cache_message = "Cache age unknown"
                else:
                    minutes_old = max(0, int(cache_age / 60))
                    cache_message = f"Cache last updated {minutes_old} minutes ago"

                await self.send_message(chat_id, f"No updates found for today ({cache_message}).")
                return

            await self.send_message(chat_id, f"📅 Found {len(today_updates)} updates for today (from cache):")
            for update in today_updates:
                message = self.format_update_message(update)
                await self.send_message(chat_id, message)

        except Exception as e:
            logger.error(f"Error in today_command: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error getting today's updates. Please try again.")

    async def should_check_updates(self):
        """Determine if updates should be checked based on current time"""
        now = datetime.datetime.now()

        # Check if it's a working day (Monday = 0, Sunday = 6)
        if now.weekday() >= 5:  # Saturday or Sunday
            logger.debug(f"Skipping update check - weekend day ({now.strftime('%A')})")
            return False

        # Check if current hour is 4 PM, 5 PM or 6 PM
        should_check = now.hour in [16, 17, 18]
        if not should_check:
            logger.debug(f"Skipping update check - outside scheduled hours (current hour: {now.hour})")
        else:
            logger.info(f"Update check scheduled for current hour ({now.hour}:00)")
        return should_check

    async def refresh_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /refresh command - force an immediate update check"""
        try:
            chat_id = update.effective_chat.id
            cache_age = self.data_manager.get_cache_age()

            # Check if cache is less than 15 minutes old
            if cache_age < 900:  # 15 minutes = 900 seconds
                minutes_left = int((900 - cache_age) / 60)
                await self.send_message(chat_id, f"⏳ Please wait {minutes_left} minutes before refreshing again.")
                return

            # Inform user that refresh is starting
            await self.send_message(chat_id, "🔄 Starting manual refresh...")

            # Run the update check
            await self.check_updates()

            # Inform about completion
            await self.send_message(chat_id, "✅ Manual refresh completed!")

        except Exception as e:
            logger.error(f"Error in refresh_command: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error during manual refresh. Please try again.")


if __name__ == "__main__":
    bot = MintosBot()
    asyncio.run(bot.run())