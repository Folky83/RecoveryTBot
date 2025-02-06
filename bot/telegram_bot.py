from __future__ import annotations
import asyncio
from datetime import datetime
import time
from typing import Optional, List, Dict, Any, Union, cast, TypedDict
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError, Conflict, Forbidden, BadRequest, RetryAfter
import math

from .logger import setup_logger
from .config import TELEGRAM_TOKEN
from .data_manager import DataManager
from .mintos_client import MintosClient
from .user_manager import UserManager

logger = setup_logger(__name__)

class YearItem(TypedDict, total=False):
    year: int
    status: str
    substatus: str
    items: List[Dict[str, Any]]

class CompanyUpdate(TypedDict, total=False):
    lender_id: int
    items: List[YearItem]
    company_name: str
    date: str
    description: str

class MintosBot:
    """
    Telegram bot for monitoring Mintos lending platform updates.
    Implements singleton pattern and provides comprehensive update tracking.
    """
    _instance: Optional['MintosBot'] = None
    _lock = asyncio.Lock()
    _initialized = False
    _polling_task: Optional[asyncio.Task] = None
    _update_task: Optional[asyncio.Task] = None

    def __new__(cls) -> 'MintosBot':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def __aenter__(self) -> 'MintosBot':
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.cleanup()

    def __init__(self) -> None:
        if not self._initialized:
            logger.info("Initializing Mintos Bot...")
            if not TELEGRAM_TOKEN:
                raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

            self.application: Optional[Application] = None
            self.data_manager = DataManager()
            self.mintos_client = MintosClient()
            self.user_manager = UserManager()
            self._initialized = True
            logger.info("Bot instance created")

    async def cleanup(self) -> None:
        """Cleanup bot resources and tasks"""
        try:
            logger.info("Starting cleanup process...")
            await self._cancel_tasks()
            await self._cleanup_application()
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

    async def _cancel_tasks(self) -> None:
        """Cancel running background tasks"""
        for task_name, task in [("polling", self._polling_task), ("update", self._update_task)]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                setattr(self, f"_{task_name}_task", None)

    async def _cleanup_application(self) -> None:
        """Clean up the Telegram application instance"""
        if self.application:
            try:
                if hasattr(self.application, 'updater') and self.application.updater.running:
                    await self.application.updater.stop()
                    await asyncio.sleep(1)

                if hasattr(self.application, 'bot'):
                    await self.application.bot.delete_webhook(drop_pending_updates=True)
                    await self.application.bot.get_updates(offset=-1)

                await self.application.stop()
                await self.application.shutdown()
                self.application = None
                self._initialized = False
            except Exception as e:
                logger.error(f"Error during application cleanup: {e}")

    async def initialize(self) -> bool:
        """Initialize bot application with handlers"""
        async with self._lock:
            try:
                logger.info("Starting bot initialization...")
                await self.cleanup()
                await asyncio.sleep(2)  # Wait for cleanup to complete

                if not TELEGRAM_TOKEN:
                    logger.error("TELEGRAM_BOT_TOKEN not set")
                    return False

                logger.info("Creating application instance...")
                self.application = Application.builder().token(TELEGRAM_TOKEN).build()

                # Verify bot connection
                try:
                    bot_info = await self.application.bot.get_me()
                    logger.info(f"Connected as bot: {bot_info.username}")
                except Exception as e:
                    logger.error(f"Failed to connect to Telegram: {e}")
                    return False

                logger.info("Setting up webhook...")
                try:
                    await self.application.bot.delete_webhook(drop_pending_updates=True)
                    await self.application.bot.get_updates(offset=-1)
                except Exception as e:
                    logger.error(f"Webhook setup failed: {e}")
                    return False

                logger.info("Registering command handlers...")
                self._register_handlers()

                logger.debug("Registered handlers:")
                for handler in self.application.handlers[0]:
                    logger.debug(f"- {handler.__class__.__name__}")

                # Initialize the application
                try:
                    await self.application.initialize()
                    await self.application.start()
                    logger.info("Application started successfully")
                except Exception as e:
                    logger.error(f"Application startup failed: {e}")
                    return False

                self._initialized = True
                logger.info("Bot initialization completed successfully")
                return True
            except Exception as e:
                logger.error(f"Initialization error: {e}", exc_info=True)
                return False

    def _register_handlers(self) -> None:
        """Register command and callback handlers"""
        if not self.application:
            logger.error("Cannot register handlers: Application not initialized")
            raise RuntimeError("Application not initialized")

        handlers = [
            CommandHandler("start", self.start_command),
            CommandHandler("company", self.company_command),
            CommandHandler("today", self.today_command),
            CommandHandler("refresh", self.refresh_command),
            CommandHandler("trigger_today", self.trigger_today_command),
            CallbackQueryHandler(self.handle_callback)
        ]

        for handler in handlers:
            try:
                handler_name = handler.__class__.__name__
                logger.info(f"Registering handler: {handler_name}")
                self.application.add_handler(handler)
                logger.info(f"Successfully registered {handler_name}")
            except Exception as e:
                logger.error(f"Error registering handler {handler.__class__.__name__}: {e}")
                raise
        self.application.add_error_handler(self._error_handler)
        logger.info("All handlers registered successfully")

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle bot errors globally"""
        logger.error(f"Update error: {context.error}")
        if isinstance(context.error, TelegramError):
            if "Forbidden: bot was blocked by the user" in str(context.error):
                user = getattr(update, 'effective_user', None)
                if user and hasattr(user, 'id'):
                    logger.warning(f"Bot blocked by user {user.id}")
                    await self.user_manager.remove_user(user.id)
            elif isinstance(context.error, Conflict):
                logger.error("Multiple instance conflict detected")
                await self.cleanup()
                await asyncio.sleep(5)
                await self.initialize()

    async def scheduled_updates(self) -> None:
        """Handle scheduled update checks"""
        while True:
            try:
                if await self.should_check_updates():
                    logger.info("Running scheduled update")
                    await self._safe_update_check()
                    # Try to resend any failed messages
                    await self.retry_failed_messages()
                    await asyncio.sleep(55 * 60)  # Wait 55 minutes
                else:
                    await asyncio.sleep(5 * 60)  # Check every 5 minutes
            except asyncio.CancelledError:
                logger.info("Scheduled updates cancelled")
                break
            except Exception as e:
                logger.error(f"Scheduled update error: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _safe_update_check(self) -> None:
        """Safely perform update check with error handling"""
        try:
            await asyncio.sleep(1)  # Prevent conflicts
            await self.check_updates()
            logger.info("Update check completed")
        except Exception as e:
            logger.error(f"Update check error: {e}", exc_info=True)

    async def run(self) -> None:
        """Run the bot with polling and scheduled updates"""
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
                    logger.error("Bot initialization failed")
                    raise RuntimeError("Bot initialization failed")

                # Start polling in background
                self._polling_task = asyncio.create_task(
                    self.application.updater.start_polling(
                        drop_pending_updates=True,
                        allowed_updates=["message", "callback_query"]
                    )
                )

                # Start scheduled updates
                self._update_task = asyncio.create_task(self.scheduled_updates())

                # Wait for both tasks
                await asyncio.gather(self._polling_task, self._update_task)
                return

            except Exception as e:
                logger.error(f"Runtime error: {e}", exc_info=True)
                retry_count += 1
                if retry_count < max_retries:
                    logger.info(f"Retrying (attempt {retry_count + 1}/{max_retries})...")
                    await asyncio.sleep(5)
                else:
                    logger.error("Max retries reached")
                    raise
            finally:
                await self.cleanup()

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        if not update.effective_chat or not update.message:
            return

        chat_id = update.effective_chat.id
        try:
            # Try to delete the command message, continue if not possible
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")

            chat_type = update.effective_chat.type
            user = update.effective_user

            if chat_type in ['channel', 'supergroup', 'group']:
                logger.info(f"Start command from channel/group {update.effective_chat.title} (chat_id: {chat_id})")
                welcome_message = "🚀 Bot added to channel/group. Updates will be sent here."
            else:
                logger.info(f"Start command from user {user.username} (chat_id: {chat_id})")
                welcome_message = self._create_welcome_message()

            self.user_manager.add_user(str(chat_id))
            await self.send_message(chat_id, welcome_message)
            logger.info(f"Chat {chat_id} registered")

        except Exception as e:
            logger.error(f"Start command error: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error processing command")

    def _create_welcome_message(self) -> str:
        """Create formatted welcome message"""
        return (
            "🚀 Welcome to Mintos Update Bot!\n\n"
            "📅 Update Schedule:\n"
            "• Automatic updates on weekdays at 3 PM, 4 PM, and 5 PM (UTC)\n\n"
            "Available Commands:\n"
            "• /company - Check updates for a specific company\n"
            "• /today - View all updates from today\n"
            "• /refresh - Force an immediate update check\n"
            "• /start - Show this welcome message\n\n"
            "You'll receive updates about lending companies automatically. Stay tuned!"
        )

    async def company_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /company command - display company selection menu with live data"""
        try:
            if not update.message:
                return

            # Try to delete the command message, continue if not possible
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")

            chat_id = update.effective_chat.id
            company_buttons = []
            companies = sorted(self.data_manager.company_names.items(), key=lambda x: x[1])
            for i in range(0, len(companies), 2):
                row = []
                for company_id, company_name in companies[i:i+2]:
                    row.append(InlineKeyboardButton(
                        company_name,
                        callback_data=f"company_{company_id}"
                    ))
                company_buttons.append(row)

            company_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
            reply_markup = InlineKeyboardMarkup(company_buttons)
            await update.message.reply_text(
                "Select a company to view updates:",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error in company_command: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error displaying company list. Please try again.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboard buttons"""
        try:
            query = update.callback_query
            await query.answer()

            if query.data.startswith("company_"):
                company_id = int(query.data.split("_")[1])
                company_name = self.data_manager.get_company_name(company_id)

                buttons = [
                    [InlineKeyboardButton("Latest Update", callback_data=f"latest_{company_id}")],
                    [InlineKeyboardButton("All Updates", callback_data=f"all_{company_id}_0")]
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

                await query.edit_message_text(f"Fetching latest data for {company_name}...")

                company_updates = self.mintos_client.get_recovery_updates(company_id)
                if company_updates:
                    company_updates = {"lender_id": company_id, **company_updates}
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
                        year_items = sorted(year_data.get("items", []),
                                             key=lambda x: datetime.strptime(x.get('date', '1900-01-01'), '%Y-%m-%d'),
                                             reverse=True)
                        for update_item in year_items:
                            update_with_company = {
                                "lender_id": company_id,
                                "company_name": company_name,
                                **update_item
                            }
                            messages.append(self.format_update_message(update_with_company))

                    updates_per_page = 5
                    total_updates = len(messages)
                    total_pages = (total_updates + updates_per_page - 1) // updates_per_page

                    if page >= total_pages:
                        page = total_pages - 1
                    if page < 0:
                        page = 0

                    start_idx = page * updates_per_page
                    end_idx = min(start_idx + updates_per_page, total_updates)

                    header_message = (
                        f"📊 Updates for {company_name}\n"
                        f"Page {page + 1} of {total_pages}\n"
                        f"Showing updates {start_idx + 1}-{end_idx} of {total_updates}"
                    )
                    await self.send_message(query.message.chat_id, header_message)

                    current_page_updates = messages[start_idx:end_idx]
                    for message in current_page_updates:
                        await self.send_message(query.message.chat_id, message)

                    nav_buttons = []
                    if page > 0:
                        nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"all_{company_id}_{page-1}"))
                    if page < total_pages - 1:
                        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"all_{company_id}_{page+1}"))

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

    _failed_messages: List[Dict[str, Any]] = []

    async def retry_failed_messages(self) -> None:
        """Attempt to resend failed messages"""
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
                    msg.get('reply_markup')
                )
                logger.info(f"Successfully resent message to {msg['chat_id']}")
            except Exception as e:
                logger.error(f"Failed to resend message: {e}")
                self._failed_messages.append(msg)

    async def send_message(self, chat_id: Union[int, str], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
        max_retries = 3
        base_delay = 1.0

        # Calculate delay based on message length
        message_length = len(text)
        adaptive_delay = min(2.0 + (message_length / 1000), 5.0)  # Max 5 second delay for very long messages

        for attempt in range(max_retries):
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                logger.debug(f"Message sent successfully to {chat_id} (length: {message_length} chars)")

                # Apply adaptive delay based on message size and previous success
                delay = adaptive_delay * (0.8 if attempt == 0 else 1.2)
                logger.debug(f"Waiting {delay:.1f}s before next message")
                await asyncio.sleep(delay)
                return

            except RetryAfter as e:
                delay = e.retry_after + 1  # Add 1 second buffer
                logger.warning(f"Rate limit hit, waiting {delay} seconds before retry")
                await asyncio.sleep(delay)
                continue

            except Forbidden as e:
                logger.error(f"Bot was blocked by user {chat_id}: {e}")
                await self.user_manager.remove_user(str(chat_id))
                raise

            except BadRequest as e:
                if "chat not found" in str(e).lower():
                    logger.error(f"Chat {chat_id} not found, removing user")
                    await self.user_manager.remove_user(str(chat_id))
                raise

            except TelegramError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Error sending message to {chat_id}: {e}", exc_info=True)
                    # Store failed message for later retry
                    self._failed_messages.append({
                        'chat_id': chat_id,
                        'text': text,
                        'reply_markup': reply_markup
                    })
                    raise
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Telegram error, retrying in {delay} seconds: {e}")
                await asyncio.sleep(delay)

    def format_update_message(self, update: Dict[str, Any]) -> str:
        """Format update message with rich information from Mintos API"""
        logger.debug(f"Formatting update message for: {update.get('company_name')}")
        company_name = update.get('company_name', 'Unknown Company')
        message = f"🏢 <b>{company_name}</b>\n"

        if 'date' in update:
            message += f"📅 <b>{update['date']}</b>"
            if 'year' in update:
                message += f" | Year: <b>{update['year']}</b>"
            message += "\n"

        if 'status' in update:
            status = update['status'].replace('_', ' ').title()
            message += f"\n📊 <b>Status:</b> {status}"
            if update.get('substatus'):
                substatus = update['substatus'].replace('_', ' ').title()
                message += f"\n└ {substatus}"
            message += "\n"

        if any(key in update for key in ['recoveredAmount', 'remainingAmount', 'expectedRecoveryTo', 'expectedRecoveryFrom']):
            message += "\n💰 <b>Recovery Information:</b>\n"

            if update.get('recoveredAmount'):
                amount = round(float(update['recoveredAmount']))
                message += f"└ Recovered: <b>€{amount:,}</b>\n"
            if update.get('remainingAmount'):
                amount = round(float(update['remainingAmount']))
                message += f"└ Remaining: <b>€{amount:,}</b>\n"

            recovery_info = []
            if update.get('expectedRecoveryFrom') and update.get('expectedRecoveryTo'):
                from_percentage = round(float(update['expectedRecoveryFrom']))
                to_percentage = round(float(update['expectedRecoveryTo']))
                recovery_info.append(f"{from_percentage}% - {to_percentage}%")
            elif update.get('expectedRecoveryTo'):
                percentage = round(float(update['expectedRecoveryTo']))
                recovery_info.append(f"Up to {percentage}%")

            if recovery_info:
                message += f"└ Expected Recovery: <b>{recovery_info[0]}</b>\n"

        if any(key in update for key in ['expectedRecoveryYearFrom', 'expectedRecoveryYearTo']):
            timeline = ""
            if update.get('expectedRecoveryYearFrom') and update.get('expectedRecoveryYearTo'):
                timeline = f"{update['expectedRecoveryYearFrom']} - {update['expectedRecoveryYearTo']}"
            elif update.get('expectedRecoveryYearTo'):
                timeline = str(update['expectedRecoveryYearTo'])

            if timeline:
                message += f"📆 Expected Recovery Timeline: {timeline}\n"

        if 'description' in update:
            description = update['description']
            # Clean HTML tags and entities
            description = (description
                .replace('\u003C', '<')
                .replace('\u003E', '>')
                .replace('&#39;', "'")
                .replace('&rsquo;', "'")
                .replace('&euro;', '€')
                .replace('&nbsp;', ' ')
                .replace('<br>', '\n')
                .replace('<br/>', '\n')
                .replace('<br />', '\n')
                .replace('<p>', '')
                .replace('</p>', '\n')
                .strip())
            message += f"\n📝 Details:\n{description}\n"

        if 'lender_id' in update:
            message += f"\n🔗 <a href='https://www.mintos.com/en/loan-companies/{update['lender_id']}'>View on Mintos</a>"

        return message.strip()

    async def check_updates(self) -> None:
        try:
            logger.info("Starting update check...")
            previous_updates = self.data_manager.load_previous_updates()
            lender_ids = [int(id) for id in self.data_manager.company_names.keys()]
            new_updates = self.mintos_client.fetch_all_updates(lender_ids)

            # Ensure both lists are of the correct type
            previous_updates = cast(List[CompanyUpdate], previous_updates)
            new_updates = cast(List[CompanyUpdate], new_updates)

            added_updates = self.data_manager.compare_updates(new_updates, previous_updates)

            if added_updates:
                users = self.user_manager.get_all_users()
                logger.info(f"Sending {len(added_updates)} new updates to {len(users)} users")

                today = time.strftime("%Y-%m-%d")
                new_today_updates = [update for update in added_updates if update.get('date') == today]

                if new_today_updates:
                    for update in new_today_updates:
                        message = self.format_update_message(update)
                        for user_id in users:
                            try:
                                await self.send_message(user_id, message)
                            except Exception as e:
                                logger.error(f"Failed to send update to user {user_id}: {e}")

            self.data_manager.save_updates(new_updates)
            logger.info(f"Update check completed. Found {len(added_updates)} new updates.")

        except Exception as e:
            logger.error(f"Error during update check: {e}", exc_info=True)
            for user_id in self.user_manager.get_all_users():
                try:
                    await self.send_message(user_id, "⚠️ Error occurred while checking for updates")
                except Exception as nested_e:
                    logger.error(f"Failed to send error notification to user {user_id}: {nested_e}")

    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /today command to show today's updates"""
        chat_id = None
        try:
            if not update.message or not update.effective_chat:
                logger.error("Invalid update object: message or effective_chat is None")
                return

            chat_id = update.effective_chat.id
            logger.info(f"Processing /today command for chat_id: {chat_id}")

            # Always try to delete the command message
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")

            updates = self.data_manager.load_previous_updates()
            if not updates:
                logger.warning("No updates found in cache")
                await self.send_message(chat_id, "No cached updates found. Try /refresh first.")
                return

            cache_age = self.data_manager.get_cache_age()
            logger.debug(f"Using cached data (age: {cache_age:.0f} seconds)")

            today = time.strftime("%Y-%m-%d")
            logger.debug(f"Searching for updates on date: {today}")
            today_updates = []

            for company_update in updates:
                if not isinstance(company_update, dict):
                    logger.warning(f"Invalid update format: {type(company_update)}")
                    continue

                if "items" not in company_update:
                    logger.warning(f"No 'items' in company update: {company_update.keys()}")
                    continue

                lender_id = company_update.get('lender_id')
                if not lender_id:
                    logger.warning("Missing lender_id in company update")
                    continue

                company_name = self.data_manager.get_company_name(lender_id)
                logger.debug(f"Processing updates for company: {company_name} (ID: {lender_id})")

                for year_data in company_update["items"]:
                    if not isinstance(year_data, dict):
                        logger.warning(f"Invalid year_data format: {type(year_data)}")
                        continue

                    items = year_data.get("items", [])
                    if not isinstance(items, list):
                        logger.warning(f"Invalid items format: {type(items)}")
                        continue

                    for item in items:
                        if item.get('date') == today:
                            update_with_company = {
                                "lender_id": lender_id,
                                "company_name": company_name,
                                **year_data,
                                **item
                            }
                            today_updates.append(update_with_company)
                            logger.debug(f"Found update for {company_name} on {today}")

            if not today_updates:
                cache_message = ""
                if math.isinf(cache_age):
                    cache_message = "Cache age unknown"
                else:
                    minutes_old = max(0, int(cache_age / 60))
                    cache_message = f"Cache last updated {minutes_old} minutes ago"

                logger.info(f"No updates found for today. {cache_message}")
                await self.send_message(chat_id, f"No updates found for today ({cache_message}).")
                return

            # Send header message with total count
            header_message = f"📅 Found {len(today_updates)} updates for today:\n"
            await self.send_message(chat_id, header_message)

            # Send each update individually
            for i, update_item in enumerate(today_updates, 1):
                try:
                    message = self.format_update_message(update_item)
                    await self.send_message(chat_id, message)
                    logger.debug(f"Successfully sent update {i}/{len(today_updates)} to {chat_id}")
                    await asyncio.sleep(1)  # Small delay between messages
                except Exception as e:
                    logger.error(f"Error sending update {i}/{len(today_updates)}: {e}", exc_info=True)
                    continue

        except Exception as e:
            error_msg = f"Error in today_command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if chat_id:
                await self.send_message(chat_id, "⚠️ Error getting today's updates. Please try again.")
            raise

    async def should_check_updates(self) -> bool:
        """Determine if updates should be checked based on current time"""
        now = datetime.now()

        if now.weekday() >= 5:
            logger.debug(f"Skipping update check - weekend day ({now.strftime('%A')})")
            return False

        should_check = now.hour in [15, 16, 17]
        if not should_check:
            logger.debug(f"Skipping update check - outside scheduled hours (current hour: {now.hour})")
        else:
            logger.info(f"Update check scheduled for current hour ({now.hour}:00)")
        return should_check

    async def refresh_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = None
        try:
            if not update.message or not update.effective_chat:
                logger.error("Invalid update object: message or effective_chat is None")
                return

            chat_id = update.effective_chat.id
            logger.info(f"Processing /refresh command for chat_id: {chat_id}")

            # Try to delete the command message, continue if not possible
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")

            await self.send_message(chat_id, "🔄 Checking for updates...")
            await self.check_updates()
            await self.send_message(chat_id, "✅ Update check completed!")

        except Exception as e:
            error_msg = f"Error in refresh_command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if chat_id:
                await self.send_message(chat_id, "⚠️ Error refreshing updates. Please try again.")
            raise


    async def _resolve_channel_id(self, channel_identifier: str) -> str:
        """Validate channel ID format and verify bot permissions"""
        logger.info(f"Validating channel ID: {channel_identifier}")

        # Only accept channel IDs in the correct format
        if not channel_identifier.startswith('-100') or not channel_identifier[4:].isdigit():
            logger.error(f"Invalid channel ID format: {channel_identifier}")
            raise ValueError(
                "Invalid channel ID format. Please use the full channel ID\n"
                "Example: -1001234567890\n"
                "Note: Channel ID must start with '-100' followed by numbers"
            )

        try:
            # Verify bot permissions in the channel
            if await self._verify_bot_permissions(channel_identifier):
                logger.info(f"Channel ID validated and permissions verified: {channel_identifier}")
                return channel_identifier

            logger.error(f"Bot lacks required permissions in channel: {channel_identifier}")
            raise ValueError(
                "Bot lacks required permissions in the channel.\n"
                "Please ensure the bot:\n"
                "1. Is added to the channel\n"
                "2. Has admin rights in the channel"
            )

        except Exception as e:
            logger.error(f"Error validating channel ID {channel_identifier}: {e}")
            logger.error(f"Full error details - Type: {type(e)}, Message: {str(e)}")
            if isinstance(e, ValueError):
                raise
            raise ValueError(
                f"Could not validate channel {channel_identifier}. "
                "Please ensure the channel ID is correct and the bot has proper permissions."
            )

    async def _verify_bot_permissions(self, chat_id: str) -> bool:
        """Verify bot's permissions in the channel"""
        try:
            if not self.application or not self.application.bot:
                logger.error("Bot application not initialized during permission check")
                raise ValueError("Bot not initialized")

            logger.info(f"Starting permission verification for chat: {chat_id}")

            try:
                # First verify if chat exists and is accessible
                chat = await self.application.bot.get_chat(chat_id)
                logger.info(f"Chat verification successful - Type: {chat.type}, Title: {chat.title}")

                # Then check bot's member status
                bot_member = await self.application.bot.get_chat_member(
                    chat_id=chat_id,
                    user_id=self.application.bot.id
                )

                # Log detailed status information
                logger.info(f"Bot member status in chat {chat_id}: {bot_member.status}")

                if bot_member.status not in ['administrator', 'creator']:
                    logger.warning(
                        f"Bot lacks required permissions in chat {chat_id}. "
                        f"Current status: {bot_member.status}. "
                        "Required status: administrator or creator"
                    )
                    return False

                logger.info(
                    f"Permission verification successful for chat {chat_id}. "
                    f"Bot status: {bot_member.status}"
                )
                return True

            except BadRequest as e:
                logger.error(f"Bad request during permission check: {e}")
                return False
            except Forbidden as e:
                logger.error(f"Bot was denied access during permission check: {e}")
                return False
            except TelegramError as e:
                logger.error(f"Telegram API error during permission check: {e}")
                return False

        except Exception as e:
            logger.error(f"Unexpected error during permission verification: {e}")
            logger.error(f"Full error details - Type: {type(e)}, Message: {str(e)}")
            return False

    async def trigger_today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /trigger_today @channel command"""
        try:
            if not update.message or not update.effective_chat or not update.effective_user:
                return

            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            logger.info(f"Processing trigger_today command from user {user_id}")

            # Try to delete the command message
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")

            # Parse the channel argument
            args = context.args if context and hasattr(context, 'args') else None
            if not args:
                await self.send_message(chat_id, "Please specify a channel (e.g., /trigger_today @yourchannel)")
                return

            target_channel = args[0]
            logger.info(f"Target channel specified: {target_channel}")

            try:
                # Convert/validate channel identifier
                resolved_channel = await self._resolve_channel_id(target_channel)
                logger.info(f"Channel resolved: {resolved_channel}")
            except ValueError as e:
                await self.send_message(
                    chat_id,
                    f"⚠️ {str(e)}\n"
                    "Please verify:\n"
                    "1. The channel exists\n"
                    "2. The bot is a member of the channel\n"
                    "3. You provided the correct channel name/ID"
                )
                return

            # Verify bot permissions
            try:
                await self.application.bot.send_message(
                    chat_id=resolved_channel,
                    text="🔄 Checking bot permissions...",
                    parse_mode='HTML'
                )
            except Exception as e:
                error_msg = str(e).lower()
                logger.error(f"Permission error for channel {resolved_channel}: {error_msg}")

                if 'not enough rights' in error_msg:
                    await self.send_message(
                        chat_id,
                        "⚠️ Bot needs admin rights. Please:\n"
                        "1. Add the bot as channel admin\n"
                        "2. Enable 'Post Messages' permission\n"
                        "3. Try again"
                    )
                else:
                    await self.send_message(
                        chat_id,
                        f"⚠️ Error accessing channel: {str(e)}\n"
                        "Please verify the bot's permissions."
                    )
                return            # Retrieve today's updates
            logger.info("Getting today's updates")
            today = time.strftime("%Y-%m-%d")
            updates = self.data_manager.load_previous_updates()
            today_updates = []

            # Process updates
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

            logger.info(f"Found {len(today_updates)} updates for today")

            # Handle no updates case
            if not today_updates:
                await self.application.bot.send_message(
                    chat_id=resolved_channel,
                    text="📝 No updates found for today.",
                    parse_mode='HTML'
                )
                await self.send_message(chat_id, "✅ No updates found for today")
                return

            # Send header
            await self.application.bot.send_message(
                chat_id=resolved_channel,
                text=f"📊 Found {len(today_updates)} updates for today:",
                parse_mode='HTML'
            )

            # Send updates
            successful_sends = 0
            for update_item in today_updates:
                try:
                    message = self.format_update_message(update_item)
                    await self.application.bot.send_message(
                        chat_id=resolved_channel,
                        text=message,
                        parse_mode='HTML'
                    )
                    successful_sends += 1
                    await asyncio.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logger.error(f"Error sending update: {e}")

            # Send status
            status = f"✅ Successfully sent {successful_sends} of {len(today_updates)} updates to {target_channel}"
            logger.info(status)
            await self.send_message(chat_id, status)

        except Exception as e:
            logger.error(f"Error in trigger_today_command: {e}", exc_info=True)
            await self.send_message(
                chat_id,
                "⚠️ An error occurred. Please verify:\n"
                "1. Channel name/ID is correct\n"
                "2. Bot has proper permissions\n"
                "3. Bot can send messages"
            )

if __name__ == "__main__":
    bot = MintosBot()
    asyncio.run(bot.run())