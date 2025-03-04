from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import time
import json
import os
from typing import Optional, List, Dict, Any, Union, cast, TypedDict
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError, Conflict, Forbidden, BadRequest, RetryAfter
import math

from .logger import setup_logger
from .config import (
    TELEGRAM_TOKEN, 
    UPDATES_FILE, 
    CAMPAIGNS_FILE, 
    DOCUMENT_CHECK_INTERVAL_HOURS
)
from .data_manager import DataManager
from .mintos_client import MintosClient
from .user_manager import UserManager
from .document_scraper import DocumentScraper

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

            self.token = TELEGRAM_TOKEN  # Store token as instance variable
            self.application: Optional[Application] = None
            self.data_manager = DataManager()
            self.mintos_client = MintosClient()
            self.user_manager = UserManager()
            self.document_scraper = DocumentScraper()
            self._async_document_scraper = None  # Will be initialized in initialize()
            self._is_startup_check = True  # Flag to track initial startup
            self._last_document_check = 0  # Timestamp of last document check
            self._initialized = True
            logger.info("Bot instance created")

    async def cleanup(self) -> None:
        """Cleanup bot resources and tasks"""
        try:
            logger.info("Starting cleanup process...")
            await self._cancel_tasks()
            
            # Clean up async document scraper if initialized
            if self._async_document_scraper:
                try:
                    await self._async_document_scraper.stop_document_checking()
                    logger.info("Async document scraper stopped")
                except Exception as e:
                    logger.error(f"Error stopping async document scraper: {e}")
            
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
                    
                # Initialize async document scraper
                try:
                    from .async_document_scraper import AsyncDocumentScraper
                    self._async_document_scraper = AsyncDocumentScraper()
                    logger.info("Async document scraper initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize async document scraper: {e}")
                    # Continue without async document scraper, we'll fall back to regular scraper

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
            CommandHandler("campaigns", self.campaigns_command),
            CommandHandler("trigger_today", self.trigger_today_command),
            CommandHandler("users", self.users_command), #Added
            CommandHandler("admin", self.admin_command), #Added admin command
            CommandHandler("documents", self.documents_command), # Show recent documents
            CommandHandler("company_documents", self.company_documents_command), # Show documents by company
            CommandHandler("check_documents", self.check_documents_command), # Manually check for new documents
            CommandHandler("help", self.help_command), # Help command
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
        """Handle scheduled update checks with improved resilience"""
        consecutive_errors = 0
        max_consecutive_errors = 3
        normal_sleep = 5 * 60  # Regular 5-minute check interval
        error_sleep = 3 * 60   # Shorter 3-minute retry after errors
        long_sleep = 55 * 60   # 55-minute wait after successful update

        while True:
            try:
                # Check the current time and stale cache situation
                should_check = await self.should_check_updates()

                if should_check:
                    logger.info("Running scheduled update")
                    try:
                        await self._safe_update_check()
                        # Reset error counter after successful update
                        consecutive_errors = 0
                        logger.info("Scheduled update completed successfully")

                        # Try to resend any failed messages
                        await self.retry_failed_messages()

                        # Use longer sleep interval after successful update
                        await asyncio.sleep(long_sleep)
                        continue  # Skip the normal sleep at the end
                    except Exception as e:
                        consecutive_errors += 1
                        logger.error(f"Update check failed ({consecutive_errors}/{max_consecutive_errors}): {e}", exc_info=True)

                        # Implement exponential backoff for repeated errors
                        if consecutive_errors >= max_consecutive_errors:
                            logger.critical(f"Too many consecutive errors ({consecutive_errors}). Backing off for longer period.")
                            await asyncio.sleep(error_sleep * consecutive_errors)
                        else:
                            await asyncio.sleep(error_sleep)
                        continue  # Skip the normal sleep at the end
                else:
                    # Check for stale cache during business hours
                    try:
                        cache_age_hours = self.data_manager.get_cache_age() / 3600
                        now = datetime.now()
                        # If more than 30 hours old on a weekday during business hours, force an update
                        if (cache_age_hours > 30 and now.weekday() < 5 and 
                            9 <= now.hour <= 18):  # Business hours (9 AM to 6 PM)
                            logger.warning(f"Cache file is {cache_age_hours:.1f} hours old - forcing emergency update")
                            await self._safe_update_check()
                            consecutive_errors = 0
                            await asyncio.sleep(long_sleep)
                            continue
                    except Exception as e:
                        logger.error(f"Error checking cache age: {e}")

                # Normal sleep interval between checks
                await asyncio.sleep(normal_sleep)

            except asyncio.CancelledError:
                logger.info("Scheduled updates cancelled")
                break
            except Exception as e:
                logger.error(f"Scheduled update loop error: {e}", exc_info=True)
                # Use shorter sleep time when we encounter errors
                await asyncio.sleep(error_sleep)

    async def _safe_update_check(self) -> None:
        """Safely perform update check with error handling"""
        try:
            await asyncio.sleep(1)  # Prevent conflicts
            await self.check_updates()
            
            # Check for new company documents if it's time
            await self.check_company_documents()
            
            logger.info("Update check completed")
        except Exception as e:
            logger.error(f"Update check error: {e}", exc_info=True)
            
    async def check_company_documents(self) -> None:
        """Check for new documents on company pages"""
        try:
            current_time = time.time()
            # Convert hours to seconds for comparison
            check_interval_seconds = DOCUMENT_CHECK_INTERVAL_HOURS * 3600
            
            # Only check once per day or after interval has passed
            if (current_time - self._last_document_check) >= check_interval_seconds:
                logger.info("Checking for new company documents")
                
                # Load company mapping from data manager
                company_mapping = self.data_manager.load_company_mapping()
                
                if not company_mapping:
                    logger.warning("No company mapping available for document scraping")
                    return
                
                # Check for new documents - use async scraper if available
                new_documents = []
                if self._async_document_scraper:
                    logger.info("Using async document scraper")
                    try:
                        # Use the non-blocking async document scraper
                        new_documents = await self._async_document_scraper.check_all_companies()
                    except Exception as e:
                        logger.error(f"Async document scraping failed: {e}", exc_info=True)
                        # Fall back to sync scraper
                        logger.info("Falling back to sync document scraper")
                        new_documents = self.document_scraper.check_all_companies(company_mapping)
                else:
                    # Use the regular blocking document scraper
                    logger.info("Using sync document scraper")
                    new_documents = self.document_scraper.check_all_companies(company_mapping)
                
                if new_documents:
                    logger.info(f"Found {len(new_documents)} new documents")
                    
                    # Send notifications for each new document
                    for document in new_documents:
                        if not self.data_manager.is_document_sent(document):
                            # Format and send the message
                            message = self.format_document_message(document)
                            await self.send_document_notification(message)
                            
                            # Mark this document as sent
                            self.data_manager.save_sent_document(document)
                else:
                    logger.info("No new documents found")
                
                # Update last check timestamp
                self._last_document_check = current_time
                logger.info("Document check completed")
            else:
                logger.debug("Skipping document check - checked recently")
                
        except Exception as e:
            logger.error(f"Error checking company documents: {e}", exc_info=True)

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
                chat_title = update.effective_chat.title
                logger.info(f"Start command from channel/group {chat_title} (chat_id: {chat_id})")
                welcome_message = "🚀 Bot added to channel/group. Updates will be sent here."
                # Save chat title as the "username" for channels/groups
                self.user_manager.add_user(str(chat_id), chat_title)
            else:
                username = user.username if user else None
                full_name = f"{user.first_name} {user.last_name if user.last_name else ''}".strip() if user else None
                user_identifier = username or full_name or "Unknown"
                logger.info(f"Start command from user {user_identifier} (chat_id: {chat_id})")
                
                # Check if user is admin to show admin command
                is_admin = await self.is_admin(user.id if user else 0)
                welcome_message = self._create_welcome_message(show_admin=is_admin)
                
                # Save username for individual users
                self.user_manager.add_user(str(chat_id), username)
            await self.send_message(chat_id, welcome_message, disable_web_page_preview=True)
            logger.info(f"Chat {chat_id} registered")

        except Exception as e:
            logger.error(f"Start command error: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error processing command", disable_web_page_preview=True)

    def _create_welcome_message(self, show_admin: bool = False) -> str:
        """Create formatted welcome message"""
        admin_command = "• /admin - Admin control panel\n" if show_admin else ""
        
        return (
            "🚀 Welcome to Mintos Update Bot!\n\n"
            "📅 Update Schedule:\n"
            "• Automatic updates on weekdays at 3 PM, 4 PM, and 5 PM (UTC)\n"
            "• Daily checks for new company documents\n\n"
            "Available Commands:\n"
            "• /company - Check updates for a specific company\n"
            "• /today - View all updates from today\n"
            "• /campaigns - View current Mintos campaigns\n"
            "• /documents - View recent company documents\n"
            "• /company_documents - Filter documents by company\n"
            "• /check_documents - Manually check for new documents\n"
            "• /refresh - Force an immediate update check\n"
            "• /start - Show this welcome message\n"
            "• /help - Show all available commands\n"
            f"{admin_command}\n"
            "You'll receive notifications about recovery updates, new company documents, and campaigns automatically. Stay tuned!"
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
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error in company_command: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error displaying company list. Please try again.", disable_web_page_preview=True)

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
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )

            elif query.data == "refresh_cache":
                chat_id = update.effective_chat.id
                await query.edit_message_text("🔄 Refreshing updates...", disable_web_page_preview=True)

                try:
                    # Force update check regardless of hour
                    await self._safe_update_check()
                    # Run today command again
                    await self.today_command(update, context)
                except Exception as e:
                    logger.error(f"Error during refresh from callback: {e}")
                    await query.edit_message_text("⚠️ Error refreshing updates. Please try again.", disable_web_page_preview=True)
                return
                
            elif query.data == "admin_users":
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                    
                users = self.user_manager.get_all_users()
                if users:
                    user_list = []
                    for chat_id in users:
                        username = self.user_manager.get_user_info(chat_id)
                        if username:
                            user_list.append(f"{chat_id} - {username}")
                        else:
                            user_list.append(f"{chat_id}")
                    
                    user_text = "👥 <b>Registered users:</b>\n\n" + "\n".join(user_list)
                else:
                    user_text = "No users are currently registered."
                
                # Add back button
                keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(user_text, reply_markup=reply_markup, parse_mode='HTML')
                return
                
            elif query.data == "admin_trigger_today":
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                
                # Get all registered users
                users = self.user_manager.get_all_users()
                
                if not users:
                    # No users found
                    keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        "🔄 <b>Send Today's Updates</b>\n\n"
                        "No registered users found.",
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                    return
                
                # Create buttons for each user
                keyboard = []
                for i, user_id in enumerate(users, 1):
                    username = self.user_manager.get_user_info(user_id) or "Unknown"
                    button_text = f"{i}. {username} ({user_id})"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"trigger_today_{user_id}")])
                
                # Add back button
                keyboard.append([InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "🔄 <b>Send Today's Updates</b>\n\n"
                    "Select a channel to send today's updates to:",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                return
                
            elif query.data == "trigger_today_custom":
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                
                # Show instructions for custom channel ID entry
                await query.edit_message_text(
                    "Please enter a custom channel ID using the command:\n\n"
                    "<code>/trigger_today [channel_id]</code>\n\n"
                    "For example:\n"
                    "<code>/trigger_today 114691530</code> - for a user\n"
                    "<code>/trigger_today -1001234567890</code> - for a channel",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                return
                
            elif query.data.startswith("doc_company_"):
                # Extract company ID from callback data
                company_id = query.data.split("_")[2]
                
                # Show documents for this company only
                await self._show_company_documents(update, company_id)
                return
                
            elif query.data.startswith("trigger_today_"):
                # Extract channel ID from callback data
                target_channel = query.data.split("_")[2]
                chat_id = update.effective_chat.id
                
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                
                # Edit message to show processing
                await query.edit_message_text("🔄 Processing, please wait...", disable_web_page_preview=True)
                
                # Send updates to the selected channel
                await self._send_today_updates_to_channel(chat_id, target_channel)
                return
                
            elif query.data == "admin_exit":
                # Close the admin panel
                await query.edit_message_text("✅ Admin panel closed.", disable_web_page_preview=True)
                return
                
            elif query.data == "admin_check_documents":
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                
                # Show checking message
                await query.edit_message_text("🔄 Checking for new company documents...", disable_web_page_preview=True)
                
                try:
                    # Force document check
                    self._last_document_check = 0  # Reset last check time to force a check
                    await self.check_company_documents()
                    
                    # Return to admin panel with success message
                    keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        "✅ Document check completed!\n\n"
                        "Any new documents found will be sent to all registered users.",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.error(f"Error during document check: {e}", exc_info=True)
                    
                    # Return to admin panel with error message
                    keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        f"⚠️ Error checking documents: {str(e)}\n\n"
                        "Please try again later.",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                return
                
            elif query.data == "admin_back":
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                    
                # Return to admin panel
                keyboard = [
                    [InlineKeyboardButton("👥 View Users", callback_data="admin_users")],
                    [InlineKeyboardButton("🔄 Send Today's Updates to Channel", callback_data="admin_trigger_today")],
                    [InlineKeyboardButton("📄 Check Company Documents", callback_data="admin_check_documents")],
                    [InlineKeyboardButton("❌ Exit", callback_data="admin_exit")]
                ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "🔐 <b>Admin Control Panel</b>\n\nPlease select an admin function:",
                    reply_markup=reply_markup,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                return

            elif query.data == "check_documents":
                # Show checking message
                await query.edit_message_text("🔄 Checking for new company documents... Please wait.", disable_web_page_preview=True)
                
                try:
                    # Force document check
                    self._last_document_check = 0  # Reset last check time to force a check
                    
                    # Load company mapping from data manager
                    company_mapping = self.data_manager.load_company_mapping()
                    
                    if not company_mapping:
                        await query.edit_message_text("⚠️ No company mapping available for document scraping.", disable_web_page_preview=True)
                        return
                        
                    # Check for new documents
                    new_documents = self.document_scraper.check_all_companies(company_mapping)
                    
                    if new_documents:
                        # Send information about new documents
                        message = f"✅ Found {len(new_documents)} new documents:\n\n"
                        
                        for i, document in enumerate(new_documents[:5], 1):  # Show first 5 documents
                            company = document.get('company_name', 'Unknown Company')
                            title = document.get('title', 'Untitled Document')
                            date = document.get('date', 'Unknown Date')
                            url = document.get('url', '#')
                            
                            message += f"{i}. <b>{company}</b>: <a href='{url}'>{title}</a> ({date})\n\n"
                            
                        if len(new_documents) > 5:
                            message += f"... and {len(new_documents) - 5} more documents. Use /documents to see all recent documents.\n\n"
                            
                        message += "New document notifications will be sent to all users shortly."
                        
                        # Add a button to view all documents
                        keyboard = [[InlineKeyboardButton("📄 View All Documents", callback_data="view_all_documents")]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.edit_message_text(
                            message,
                            reply_markup=reply_markup,
                            parse_mode='HTML',
                            disable_web_page_preview=False  # Enable preview for document links
                        )
                        
                        # Also trigger sending the notification to all users
                        for document in new_documents:
                            if not self.data_manager.is_document_sent(document):
                                # Format and send the message
                                notification = self.format_document_message(document)
                                await self.send_document_notification(notification)
                                
                                # Mark this document as sent
                                self.data_manager.save_sent_document(document)
                    else:
                        # Add a button to view all documents
                        keyboard = [[InlineKeyboardButton("📄 View All Documents", callback_data="view_all_documents")]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.edit_message_text(
                            "✅ Document check completed. No new documents found.",
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                        
                except Exception as e:
                    logger.error(f"Error during document check: {e}", exc_info=True)
                    await query.edit_message_text(
                        f"⚠️ Error checking documents: {str(e)}",
                        disable_web_page_preview=True
                    )
                return

            elif query.data == "view_all_documents":
                # Simulate /documents command
                await self.documents_command(update, context)
                return
            
            elif query.data == "company_documents_back":
                # Return to company documents selection
                await self.company_documents_command(update, context)
                return
            
            elif query.data == "cancel":
                await query.edit_message_text("Operation cancelled.", disable_web_page_preview=True)
                return

            elif query.data.startswith(("latest_", "all_")):
                parts = query.data.split("_")
                update_type = parts[0]
                company_id = int(parts[1])
                page = int(parts[2]) if len(parts) > 2 else 0
                company_name = self.data_manager.get_company_name(company_id)

                await query.edit_message_text(f"Fetching latest data for {company_name}...", disable_web_page_preview=True)

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
                    await query.edit_message_text(f"No updates found for {company_name}", disable_web_page_preview=True)
                    return

                if update_type == "latest":
                    latest_update = {"lender_id": company_id, "company_name": company_name}
                    if "items" in company_updates and company_updates["items"]:
                        latest_year = company_updates["items"][0]
                        if "items" in latest_year and latest_year["items"]:
                            latest_item = latest_year["items"][0]
                            latest_update.update(latest_item)
                    message = self.format_update_message(latest_update)
                    await query.edit_message_text(message, parse_mode='HTML', disable_web_page_preview=True)

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
                    await self.send_message(query.message.chat_id, header_message, disable_web_page_preview=True)

                    current_page_updates = messages[start_idx:end_idx]
                    for message in current_page_updates:
                        await self.send_message(query.message.chat_id, message, disable_web_page_preview=True)

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
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )

        except Exception as e:
            logger.error(f"Error in handle_callback: {e}", exc_info=True)
            await query.edit_message_text("⚠️ Error processing your request. Please try again.", disable_web_page_preview=True)

    _failed_messages: List[Dict[str, Any]] = []
    
    def format_document_message(self, document: Dict[str, Any]) -> str:
        """Format a notification message for a new document
        
        Args:
            document: Document information dictionary
            
        Returns:
            Formatted message text
        """
        company_name = document.get('company_name', 'Unknown Company')
        # Handle both direct and nested document structures
        title = document.get('title', None)
        date = document.get('date', None) 
        url = document.get('url', None)
        document_type = document.get('document_type', None)
        country_info = document.get('country_info', None)
        
        # If values are not direct, try to get from nested 'document' object
        if title is None or date is None or url is None:
            doc = document.get('document', {})
            if not title:
                title = doc.get('title', 'Untitled Document')
            if not date:
                date = doc.get('date', 'Unknown date')
            if not url:
                url = doc.get('url', '#')
            if not document_type:
                document_type = doc.get('document_type', None)
            if not country_info:
                country_info = doc.get('country_info', None)
                
        # Determine document type based on metadata or extension
        if document_type:
            # Use the document type from metadata
            doc_type = document_type.capitalize()
        else:
            # Format the document type based on file extension
            doc_type = "PDF"
            if url and "." in url:
                file_ext = url.split(".")[-1].lower()
                if file_ext in ["xls", "xlsx", "csv"]:
                    doc_type = "Spreadsheet"
                elif file_ext in ["doc", "docx"]:
                    doc_type = "Word Document"
                elif file_ext in ["ppt", "pptx"]:
                    doc_type = "Presentation"
                elif file_ext in ["zip", "rar"]:
                    doc_type = "Archive"
                
        # Format date if possible
        formatted_date = date
        try:
            # Check if the date might be in some standard format
            if isinstance(date, str) and ("-" in date or "/" in date):
                # Try to parse the date into a more readable format
                date_formats = ["%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%d/%m/%Y", "%m/%d/%Y"]
                for fmt in date_formats:
                    try:
                        dt = datetime.strptime(date, fmt)
                        formatted_date = dt.strftime("%d %B %Y")
                        break
                    except ValueError:
                        continue
        except Exception:
            # If date formatting fails, keep original
            pass
            
        # Create an emoji indicator for the document type
        emoji = "📄"
        if doc_type == "Spreadsheet":
            emoji = "📊"
        elif doc_type == "Word Document":
            emoji = "📝"
        elif doc_type == "Presentation":
            emoji = "📑"
            
        # Create a more attractive message with emoji and formatting
        message = (
            f"{emoji} <b>New {doc_type} Document Published</b>\n\n"
            f"🏢 <b>Company:</b> {company_name}\n"
            f"📋 <b>Title:</b> {title}\n"
            f"📅 <b>Published:</b> {formatted_date}\n"
        )
        
        # Add country-specific information if available
        if country_info and isinstance(country_info, dict) and country_info.get('is_country_specific', False):
            countries = country_info.get('countries', [])
            regions = country_info.get('regions', [])
            
            if countries:
                countries_str = ", ".join(country.capitalize() for country in countries)
                message += f"🌍 <b>Countries:</b> {countries_str}\n"
                
            if regions:
                regions_str = ", ".join(region.capitalize() for region in regions)
                message += f"🗺️ <b>Regions:</b> {regions_str}\n"
        
        # Add download link
        message += f"\n<a href='{url}'>📥 Download Document</a>"
        
        return message
        
    async def send_document_notification(self, message: str) -> None:
        """Send document notification to all registered users
        
        Args:
            message: Formatted message text
        """
        user_ids = self.user_manager.get_all_users()
        success_count = 0
        
        for chat_id in user_ids:
            try:
                await self.send_message(
                    chat_id=chat_id,
                    text=message,
                    disable_web_page_preview=False,  # Allow document preview
                )
                success_count += 1
                # Add a small delay to avoid rate limiting
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Failed to send document notification to {chat_id}: {e}")
                
        logger.info(f"Sent document notification to {success_count}/{len(user_ids)} users")

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
                    msg.get('reply_markup'),
                    disable_web_page_preview=True
                )
                logger.info(f"Successfully resent message to {msg['chat_id']}")
            except Exception as e:
                logger.error(f"Failed to resend message: {e}")
                self._failed_messages.append(msg)

    async def send_message(self, chat_id: Union[int, str], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, disable_web_page_preview: bool = False) -> None:
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
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview
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
            # Link directly to campaigns page
            message += f"\n🔗 <a href='https://www.mintos.com/en/campaigns/'>View on Mintos</a>"

        return message.strip()

    def format_campaign_message(self, campaign: Dict[str, Any]) -> str:
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
                except (ValueError, TypeError):
                    # If conversion fails, use original text
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
            # Use regex to completely strip all HTML tags and safely handle entity references
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
            description = re.sub(r'\s{2,}', ' ', description)      # Replace multiple spaces with one
            message += f"\n📝 <b>Description:</b>\n{description}\n"

        # Terms & Conditions link
        if campaign.get('termsConditionsLink'):
            message += f"\n📄 <a href='{campaign.get('termsConditionsLink')}'>Terms & Conditions</a>"

        # Add link to Mintos campaigns page
        message += "\n\n🔗 <a href='https://www.mintos.com/en/campaigns/'>View on Mintos</a>"

        return message.strip()

    async def check_updates(self) -> None:
        try:
            now = datetime.now()
            logger.info(f"Starting update check at {now.strftime('%Y-%m-%d %H:%M:%S')}...")

            # Get cache file age before update
            try:
                if os.path.exists(UPDATES_FILE):
                    before_update_time = os.path.getmtime(UPDATES_FILE)
                    cache_age_hours = (time.time() - before_update_time) / 3600
                    logger.info(f"Cache file age before update: {cache_age_hours:.1f} hours (last modified: {datetime.fromtimestamp(before_update_time).strftime('%Y-%m-%d %H:%M:%S')})")
            except Exception as e:
                logger.error(f"Error checking cache file age before update: {e}")

            # Load previous updates
            previous_updates = self.data_manager.load_previous_updates()
            logger.info(f"Loaded {len(previous_updates)} previous updates")

            # Fetch new updates
            lender_ids = [int(id) for id in self.data_manager.company_names.keys()]
            logger.info(f"Fetching updates for {len(lender_ids)} lender IDs")
            new_updates = self.mintos_client.fetch_all_updates(lender_ids)
            logger.info(f"Fetched {len(new_updates)} new updates from API")

            # Ensure both lists are of the correct type
            previous_updates = cast(List[CompanyUpdate], previous_updates)
            new_updates = cast(List[CompanyUpdate], new_updates)

            # Compare updates
            added_updates = self.data_manager.compare_updates(new_updates, previous_updates)
            logger.info(f"Found {len(added_updates)} new updates after comparison")

            if added_updates:
                users = self.user_manager.get_all_users()
                logger.info(f"Found {len(added_updates)} new updates to process for {len(users)} users")

                today = time.strftime("%Y-%m-%d")
                new_today_updates = [update for update in added_updates if update.get('date') == today]
                logger.info(f"Found {len(new_today_updates)} updates for today ({today})")

                if new_today_updates:
                    unsent_updates = [
                        update for update in new_today_updates 
                        if not self.data_manager.is_update_sent(update)
                    ]
                    logger.info(f"Found {len(unsent_updates)} unsent updates for today")

                    if unsent_updates:
                        logger.info(f"Sending {len(unsent_updates)} unsent updates to {len(users)} users")
                        for i, update in enumerate(unsent_updates):
                            message = self.format_update_message(update)
                            for user_id in users:
                                try:
                                    await self.send_message(user_id, message, disable_web_page_preview=True)
                                    self.data_manager.save_sent_update(update)
                                    logger.info(f"Successfully sent update {i+1}/{len(unsent_updates)} to user {user_id}")
                                except Exception as e:
                                    logger.error(f"Failed to send update to user {user_id}: {e}")
                    else:
                        logger.info("No new unsent updates to send")
                else:
                    logger.info(f"No new updates found for today ({today})")

            # Save updates to file
            try:
                before_size = os.path.getsize(UPDATES_FILE) if os.path.exists(UPDATES_FILE) else 0
                self.data_manager.save_updates(new_updates)
                after_size = os.path.getsize(UPDATES_FILE) if os.path.exists(UPDATES_FILE) else 0

                # Check if the file was actually updated
                if after_size > 0:
                    modified_time = os.path.getmtime(UPDATES_FILE)
                    logger.info(f"Cache file updated successfully. Size: {before_size} -> {after_size} bytes")
                    logger.info(f"New modification time: {datetime.fromtimestamp(modified_time).strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    logger.warning("Cache file may not have been updated properly (size is 0)")
            except Exception as e:
                logger.error(f"Error verifying cache file update: {e}")

            # Check for new campaigns
            await self.check_campaigns()

            logger.info(f"Update check completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. Found {len(added_updates)} new updates.")

        except Exception as e:
            logger.error(f"Error during update check: {e}", exc_info=True)
            for user_id in self.user_manager.get_all_users():
                try:
                    await self.send_message(user_id, "⚠️ Error occurred while checking for updates", disable_web_page_preview=True)
                except Exception as nested_e:
                    logger.error(f"Failed to send error notification to user {user_id}: {nested_e}")

    async def check_campaigns(self) -> None:
        """Check for new Mintos campaigns"""
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

                # Check if this is during app startup
                is_startup = getattr(self, '_is_startup_check', True)
                if is_startup:
                    # During startup, don't send campaigns that might have been sent in previous runs
                    logger.info("Startup detected - marking campaigns as sent without sending notifications")
                    for campaign in added_campaigns:
                        if not self.data_manager.is_campaign_sent(campaign):
                            self.data_manager.save_sent_campaign(campaign)
                    # Reset startup flag
                    self._is_startup_check = False
                    logger.info("Campaigns marked as sent during startup")
                    return

                # Filter out Special Promotion (type 4) campaigns and unsent campaigns
                unsent_campaigns = [
                    campaign for campaign in added_campaigns 
                    if not self.data_manager.is_campaign_sent(campaign) and campaign.get('type') != 4
                ]
                logger.info(f"Found {len(unsent_campaigns)} unsent campaigns")

                if unsent_campaigns:
                    logger.info(f"Sending {len(unsent_campaigns)} unsent campaigns to {len(users)} users")
                    for i, campaign in enumerate(unsent_campaigns):
                        message = self.format_campaign_message(campaign)
                        for user_id in users:
                            try:
                                await self.send_message(user_id, message, disable_web_page_preview=True)
                                self.data_manager.save_sent_campaign(campaign)
                                logger.info(f"Successfully sent campaign {i+1}/{len(unsent_campaigns)} to user {user_id}")
                            except Exception as e:
                                logger.error(f"Failed to send campaign to user {user_id}: {e}")
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
                    logger.error(f"Failed to send campaign error notification to user {user_id}: {nested_e}")

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

            # Check cache age and refresh if needed
            cache_age = self.data_manager.get_cache_age()
            cache_age_minutes = int(cache_age / 60) if not math.isinf(cache_age) else float('inf')

            # If cache is older than 6 hours (360 minutes), do a fresh check
            if cache_age_minutes > 360:
                logger.info(f"Cache is old ({cache_age_minutes} minutes), doing a fresh update check")
                await self.send_message(chat_id, "🔄 Cache is old, refreshing updates...", disable_web_page_preview=True)
                try:
                    # Do a fresh update check regardless of current hour
                    await self._safe_update_check()
                    logger.info("Cache refreshed successfully")
                except Exception as e:
                    logger.error(f"Failed to refresh cache: {e}")

            updates = self.data_manager.load_previous_updates()
            if not updates:
                logger.warning("No updates found in cache")
                await self.send_message(chat_id, "No cached updates found. Try /refresh first.", disable_web_page_preview=True)
                return

            # Get the (possibly new) cache age
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

            # Check if we have any updates
            have_updates = len(today_updates) > 0

            if not have_updates:
                cache_message = ""
                if math.isinf(cache_age):
                    cache_message = "Cache age unknown"
                else:
                    minutes_old = max(0, int(cache_age / 60))
                    hours_old = minutes_old // 60
                    remaining_minutes = minutes_old % 60

                    if hours_old > 0:
                        cache_message = f"Cache last updated {hours_old}h {remaining_minutes}m ago"
                    else:
                        cache_message = f"Cache last updated {minutes_old} minutes ago"

                logger.info(f"No updates found for today. {cache_message}")

                # Create a message with a refresh button if cache is old
                if minutes_old > 120:  # If cache is older than 2 hours
                    keyboard = [[InlineKeyboardButton("🔄 Refresh Now", callback_data="refresh_cache")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await self.send_message(
                        chat_id, 
                        f"No updates found for today ({cache_message}).\nWould you like to check for new updates?",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                else:
                    await self.send_message(chat_id, f"No updates found for today ({cache_message.lower()}).", disable_web_page_preview=True)
                return

            # If we have updates, send them
            # Send header message with total count
            header_message = f"📅 Found {len(today_updates)} updates for today:\n"
            await self.send_message(chat_id, header_message, disable_web_page_preview=True)

            # Send each update individually
            for i, update_item in enumerate(today_updates, 1):
                try:
                    message = self.format_update_message(update_item)
                    await self.send_message(chat_id, message, disable_web_page_preview=True)
                    logger.debug(f"Successfully sent update {i}/{len(today_updates)} to {chat_id}")
                    await asyncio.sleep(1)  # Small delay between messages
                except Exception as e:
                    logger.error(f"Error sending update {i}/{len(today_updates)}: {e}", exc_info=True)
                    continue

        except Exception as e:
            error_msg = f"Error in today_command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if chat_id:
                await self.send_message(chat_id, "⚠️ Error getting today's updates. Please try again.", disable_web_page_preview=True)
            raise

    async def should_check_updates(self) -> bool:
        """Check if updates should be checked based on current time"""
        now = datetime.now()
        # Enhanced logging of server time
        logger.debug(f"Current server time: {now.strftime('%Y-%m-%d %H:%M:%S')} (weekday: {now.weekday()}, hour: {now.hour})")

        # Schedule updates for working days (Monday = 0, Sunday = 6)
        # at specific hours (15:00, 16:00, 1700 UTC)
        is_scheduled_time = (
            now.weekday() < 5 and  # Monday to Friday
            now.hour in [15, 16, 17]  # 3 PM, 4 PM, 5 PM UTC
        )

        # By default, check based on schedule
        should_check = is_scheduled_time

        # Add a recovery mechanism for missed updates
        try:
            # Check for stale cache on weekdays
            if os.path.exists(UPDATES_FILE):
                cache_age_hours = self.data_manager.get_cache_age() / 3600
                logger.debug(f"Cache file age: {cache_age_hours:.1f} hours")

                # If cache is more than 24 hours old on a weekday, log a warning and trigger an update
                if cache_age_hours > 24 and now.weekday() < 5:
                    logger.warning(f"Cache file is {cache_age_hours:.1f} hours old on a weekday - may indicate missed updates")

                    # Force an update during business hours even if outside scheduled update times
                    # This helps recover from missed updates
                    if 9 <= now.hour <= 18:  # Business hours (9 AM to 6 PM)
                        logger.info("Forcing update check due to stale cache during business hours")
                        should_check = True
        except Exception as e:
            logger.error(f"Error checking cache file status: {e}")

        if not should_check:
            logger.debug(f"Skipping updatecheck - outside scheduled hours (weekday: {now.weekday()}, hour: {now.hour})")
        else:
            logger.info(f"Update check scheduled for current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        return should_check

    # Dictionary to track last refresh command usage per user
    _refresh_cooldowns = {}
    _refresh_cooldown_minutes = 10

    async def refresh_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Force an immediate update check with cooldown period"""
        if not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        current_time = datetime.now()

        # Try to delete the command message, continue if not possible
        try:
            if update.message:
                await update.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete command message: {e}")

        # Check if user is in cooldown period
        if chat_id in self._refresh_cooldowns:
            last_refresh = self._refresh_cooldowns[chat_id]
            elapsed_minutes = (current_time - last_refresh).total_seconds() / 60

            if elapsed_minutes < self._refresh_cooldown_minutes:
                remaining = round(self._refresh_cooldown_minutes - elapsed_minutes)
                await self.send_message(
                    chat_id, 
                    f"⏳ Command on cooldown. Please wait {remaining} more minute(s) before using /refresh again.",
                    disable_web_page_preview=True
                )
                return

        try:
            # Update cooldown timestamp
            self._refresh_cooldowns[chat_id] = current_time

            await self.send_message(chat_id, "🔄 Checking for updates...", disable_web_page_preview=True)
            await self._safe_update_check()
            await self.send_message(chat_id, "✅ Update check completed", disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Error in refresh command: {e}")
            await self.send_message(chat_id, "⚠️ Error checking for updates", disable_web_page_preview=True)

    async def campaigns_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /campaigns command to show active Mintos campaigns"""
        if not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        try:
            # Try to delete the command message, continue if not possible
            try:
                if update.message:
                    await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")

            logger.info(f"Processing /campaigns command for chat_id: {chat_id}")

            # Check if campaigns cache exists and age
            cache_age = self.data_manager.get_campaigns_cache_age()
            cache_age_minutes = int(cache_age / 60) if not math.isinf(cache_age) else float('inf')

            # If cache is older than 6 hours (360 minutes) or doesn't exist, do a fresh check
            if cache_age_minutes > 360:
                logger.info(f"Campaigns cache is old ({cache_age_minutes} minutes), doing a fresh campaigns check")
                await self.send_message(chat_id, "🔄 Fetching latest campaigns...", disable_web_page_preview=True)

                try:
                    # Fetch new campaigns directly
                    new_campaigns = self.mintos_client.get_campaigns()
                    if not new_campaigns:
                        await self.send_message(chat_id, "⚠️ No campaigns available right now.", disable_web_page_preview=True)
                        return

                    # Save for future use
                    self.data_manager.save_campaigns(new_campaigns)
                    logger.info(f"Fetched and saved {len(new_campaigns)} campaigns")
                except Exception as e:
                    logger.error(f"Error fetching campaigns: {e}")
                    await self.send_message(chat_id, "⚠️ Error fetching campaigns. Please try again later.", disable_web_page_preview=True)
                    return
            else:
                # Load from cache
                new_campaigns = self.data_manager.load_previous_campaigns()
                logger.info(f"Using cached campaigns data ({cache_age_minutes} minutes old)")

            if not new_campaigns:
                await self.send_message(chat_id, "No campaigns found. Try again later.", disable_web_page_preview=True)
                return

            # Display header with count of campaigns
            active_campaigns = []
            for campaign in new_campaigns:
                # Filter out Special Promotion (type 4) campaigns and check if active
                if self._is_campaign_active(campaign) and campaign.get('type') != 4:
                    active_campaigns.append(campaign)

            if not active_campaigns:
                await self.send_message(chat_id, "No active campaigns found at this time.", disable_web_page_preview=True)
                return

            # Sort campaigns by order field (if available) or by validity date
            sorted_campaigns = sorted(
                active_campaigns, 
                key=lambda c: (c.get('order', 999), c.get('validTo', '9999-12-31'))
            )

            await self.send_message(
                chat_id, 
                f"📣 <b>Current Mintos Campaigns</b>\n\nFound {len(sorted_campaigns)} active campaigns:",
                disable_web_page_preview=True
            )

            # Send each campaign with a small delay between messages
            for i, campaign in enumerate(sorted_campaigns, 1):
                try:
                    message = self.format_campaign_message(campaign)
                    await self.send_message(chat_id, message, disable_web_page_preview=True)
                    logger.debug(f"Successfully sent campaign {i}/{len(sorted_campaigns)} to {chat_id}")
                    await asyncio.sleep(1)  # Small delay between messages
                except Exception as e:
                    logger.error(f"Error sending campaign {i}/{len(sorted_campaigns)}: {e}", exc_info=True)
                    continue

        except Exception as e:
            error_msg = f"Error in campaigns_command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if chat_id:
                await self.send_message(chat_id, "⚠️ Error getting campaigns. Please try again.", disable_web_page_preview=True)

    def _is_campaign_active(self, campaign: Dict[str, Any]) -> bool:
        """Check if a campaign is currently active based on its validity dates"""
        try:
            # Use UTC time for comparison
            now = datetime.now().replace(tzinfo=timezone.utc)

            valid_from = campaign.get('validFrom')
            valid_to = campaign.get('validTo')

            if not valid_from or not valid_to:
                return False

            # Parse dates (format example: "2025-01-31T22:00:00.000000Z")
            from_date = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
            to_date = datetime.fromisoformat(valid_to.replace('Z', '+00:00'))

            return from_date <= now <= to_date
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing campaign dates: {e}")
            # If we can't parse dates, consider the campaign active by default
            return True

    async def trigger_today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Trigger an update check for today's updates"""
        if not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        try:
            await self.send_message(chat_id, "🔄 Checking today's updates...", disable_web_page_preview=True)
            await self.today_command(update, context)
        except Exception as e:
            logger.error(f"Error in trigger_today command: {e}")
            await self.send_message(chat_id, "⚠️ Error checking today's updates", disable_web_page_preview=True)

    async def _resolve_channel_id(self, channel_identifier: str) -> str:
        """Validate channel/user ID format and verify permissions"""
        logger.info(f"Validating target ID: {channel_identifier}")

        # Check if it's a registered user ID first
        if channel_identifier in self.user_manager.get_all_users():
            logger.info(f"Valid registered user ID: {channel_identifier}")
            return channel_identifier
            
        # Check if it's a channel ID (should start with -100)
        if channel_identifier.startswith('-100') and channel_identifier[4:].isdigit():
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
        
        # If we get here, the ID format is invalid
        logger.error(f"Invalid ID format: {channel_identifier}")
        raise ValueError(
            "Invalid ID format. For channels, please use the full channel ID\n"
            "Example: -1001234567890\n"
            "Note: Channel IDs must start with '-100' followed by numbers\n\n"
            "For users, please use a valid registered user ID"
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
        """Handle /trigger_today command with user selection"""
        try:
            if not update.message or not update.effective_chat or not update.effective_user:
                return

            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            logger.info(f"Processing trigger_today command from user {user_id}")

            # Only allow admin to use this command
            if not await self.is_admin(user_id):
                await update.message.reply_text("Sorry, this command is only available to the admin.")
                try:
                    await update.message.delete()
                except Exception as e:
                    logger.warning(f"Could not delete command message: {e}")
                return

            # Try to delete the command message
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")

            # Check if number or user was specified in args
            args = context.args if context and hasattr(context, 'args') else None
            if args:
                # Attempt to use the provided argument (channel ID or number selection)
                target_channel = args[0]
                
                # Check if it's a number referencing a user in the list
                try:
                    index = int(target_channel)
                    users = list(self.user_manager.get_all_users())
                    
                    # If number is between 1 and number of users, use it as a user index
                    if 1 <= index <= len(users):
                        target_channel = users[index-1]
                        logger.info(f"Selected user by index {index}: {target_channel}")
                    else:
                        # If it's a number but not a valid index, use it directly as a channel ID
                        # This allows entering any channel ID manually
                        target_channel = str(target_channel)
                        logger.info(f"Using provided numeric channel ID: {target_channel}")
                except ValueError:
                    # Not a number, use as is (should be a channel ID)
                    logger.info(f"Using provided channel ID: {target_channel}")
                
                # Continue with sending updates to the target channel
                await self._send_today_updates_to_channel(chat_id, target_channel)
                return
                
            # No arguments provided, display user selection interface
            # Get all registered users
            users = self.user_manager.get_all_users()
            
            # Create buttons for registered users
            keyboard = []
            for i, user_id in enumerate(users, 1):
                username = self.user_manager.get_user_info(user_id) or "Unknown"
                button_text = f"{i}. {username} ({user_id})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"trigger_today_{user_id}")])
            
            # Add button for manual ID entry
            keyboard.append([InlineKeyboardButton("✏️ Enter custom channel ID", callback_data="trigger_today_custom")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self.send_message(
                chat_id,
                "📲 <b>Select a channel to send today's updates to:</b>\n\n"
                "You can also use <code>/trigger_today [number]</code> or <code>/trigger_today [channel_id]</code>",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )

        except Exception as e:
            logger.error(f"Error in trigger_today_command: {e}", exc_info=True)
            await self.send_message(
                chat_id,
                "⚠️ An error occurred while processing your command.",
                disable_web_page_preview=True
            )
            
    async def _send_today_updates_to_channel(self, admin_chat_id: Union[int, str], target_channel: str) -> None:
        """Send today's updates to the specified channel"""
        try:
            # Inform user that command is being processed
            await self.send_message(admin_chat_id, "🔄 Processing command...", disable_web_page_preview=True)
            logger.info(f"Target channel specified: {target_channel}")

            try:
                # Convert/validate channel identifier
                resolved_channel = await self._resolve_channel_id(target_channel)
                logger.info(f"Channel resolved: {resolved_channel}")
            except ValueError as e:
                await self.send_message(
                    admin_chat_id,
                    f"⚠️ {str(e)}\n"
                    "Please verify:\n"
                    "1. The channel exists\n"
                    "2. The bot is a member of the channel\n"
                    "3. You provided the correct channel name/ID",
                    disable_web_page_preview=True
                )
                return

            # Verify bot permissions without sending a message
            try:
                # Just check if the bot can get chat info instead of sending a message
                await self.application.bot.get_chat(resolved_channel)
            except Exception as e:
                error_msg = str(e).lower()
                logger.error(f"Permission error for channel {resolved_channel}: {error_msg}")

                if 'not enough rights' in error_msg:
                    await self.send_message(
                        admin_chat_id,
                        "⚠️ Bot needs admin rights. Please:\n"
                        "1. Add the bot as channel admin\n"
                        "2. Enable 'Post Messages' permission\n"
                        "3. Try again",
                        disable_web_page_preview=True
                    )
                else:
                    await self.send_message(
                        admin_chat_id,
                        f"⚠️ Error accessing channel: {str(e)}\n"
                        "Please verify the bot's permissions.",
                        disable_web_page_preview=True
                    )
                return

            # Retrieve today's updates
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

            # Handle no updates case - only notify the command sender, not the channel
            if not today_updates:
                await self.send_message(admin_chat_id, "✅ No updates found for today", disable_web_page_preview=True)
                return

            # Send updates to the channel
            successful_sends = 0

            # Only send header if there are updates to show
            if today_updates:
                await self.application.bot.send_message(
                    chat_id=resolved_channel,
                    text=f"📊 Updates for today ({today}):",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

                # Send updates
                for update_item in today_updates:
                    try:
                        message = self.format_update_message(update_item)
                        await self.application.bot.send_message(
                            chat_id=resolved_channel,
                            text=message,
                            parse_mode='HTML',
                            disable_web_page_preview=True
                        )
                        successful_sends += 1
                        await asyncio.sleep(0.5)  # Rate limiting
                    except Exception as e:
                        logger.error(f"Error sending update: {e}")

            # Get channel name for the status message
            channel_name = target_channel
            try:
                channel_info = await self.application.bot.get_chat(resolved_channel)
                if channel_info.title:
                    channel_name = channel_info.title
            except:
                pass  # If we can't get the name, use the ID

            # Send status only to the user who triggered the command
            status = f"✅ Successfully sent {successful_sends} of {len(today_updates)} updates to {channel_name}"
            logger.info(status)
            await self.send_message(admin_chat_id, status, disable_web_page_preview=True)

        except Exception as e:
            logger.error(f"Error sending updates to channel: {e}", exc_info=True)
            await self.send_message(
                admin_chat_id,
                "⚠️ An error occurred. Please verify:\n"
                "1. Channel name/ID is correct\n"
                "2. Bot has proper permissions\n"
                "3. Bot can send messages",
                disable_web_page_preview=True
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message with available commands."""
        help_text = (
            "Available commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/updates - Show lending company updates\n"
            "/refresh - Force refresh updates data\n"
            "/users - View registered users (admin only)\n"
            "/company - Check updates for a specific company\n"
            "/today - View all updates from today\n"
            "/campaigns - View current Mintos campaigns\n"
            "/documents - View recent company documents\n"
            "/company_documents - Filter documents by company\n"
            "/check_documents - Manually check for new documents\n"
            "/trigger_today @channel - Send today's updates to a specified channel\n"
        )
        await update.message.reply_text(help_text)
        # Delete the command message
        await update.message.delete()

    async def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return str(user_id) == "114691530"  # This is the admin ID from your logs
        
    async def users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show list of registered users (admin use only)."""
        if not update.effective_user:
            return
            
        user_id = update.effective_user.id

        # Only allow admin to use this command
        if not await self.is_admin(user_id):
            await update.message.reply_text("Sorry, this command is only available to the admin.")
            await update.message.delete()
            return

        users = self.user_manager.get_all_users()
        if users:
            user_list = []
            for chat_id in users:
                username = self.user_manager.get_user_info(chat_id)
                if username:
                    user_list.append(f"{chat_id} - {username}")
                else:
                    user_list.append(f"{chat_id}")
            
            user_text = "Registered users:\n" + "\n".join(user_list)
        else:
            user_text = "No users are currently registered."

        await update.message.reply_text(user_text)
        # Delete the command message
        await update.message.delete()
        
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin command panel with various admin functions"""
        if not update.effective_user or not update.effective_chat or not update.message:
            return
            
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Only allow admin to use this command
        if not await self.is_admin(user_id):
            await update.message.reply_text("Sorry, this command is only available to the admin.")
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")
            return
            
        try:
            # Try to delete the command message
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete command message: {e}")
        
        # Create admin panel with inline keyboard
        keyboard = [
            [InlineKeyboardButton("👥 View Users", callback_data="admin_users")],
            [InlineKeyboardButton("🔄 Send Today's Updates to Channel", callback_data="admin_trigger_today")],
            [InlineKeyboardButton("📄 Check Company Documents", callback_data="admin_check_documents")],
            [InlineKeyboardButton("❌ Exit", callback_data="admin_exit")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(
            chat_id,
            "🔐 <b>Admin Control Panel</b>\n\nPlease select an admin function:",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )

    async def documents_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /documents command - show recent company documents"""
        if not update.effective_chat or not update.message:
            return
            
        chat_id = update.effective_chat.id
        try:
            # Try to delete the command message, continue if not possible
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")
            
            # Load document data - use direct path to improve reliability
            document_data = {}
            try:
                document_cache_path = "data/documents_cache.json"
                logger.info(f"Loading documents from {document_cache_path}")
                if os.path.exists(document_cache_path):
                    with open(document_cache_path, 'r', encoding='utf-8') as f:
                        document_data = json.load(f)
                        logger.info(f"Successfully loaded document data with {len(document_data)} companies")
                else:
                    logger.error(f"Document cache file not found at {document_cache_path}")
            except Exception as e:
                logger.error(f"Error loading document data: {e}", exc_info=True)
                document_data = {}
            
            if not document_data:
                await self.send_message(
                    chat_id,
                    "❓ No document data available. Use /check_documents to fetch the latest documents.",
                    disable_web_page_preview=True
                )
                return
                
            # Get most recent documents (last 10)
            recent_documents = []
            for company_id, documents in document_data.items():
                company_name = self.data_manager.get_company_name(company_id) or company_id
                for doc in documents:
                    # Create a copy of the document with company name
                    doc_with_company = dict(doc)
                    doc_with_company['company_name'] = company_name
                    recent_documents.append(doc_with_company)
            
            logger.info(f"Found {len(recent_documents)} total documents across all companies")
            
            # Sort by date (newest first) and take top 10
            recent_documents.sort(key=lambda x: x.get('date', ''), reverse=True)
            recent_documents = recent_documents[:10]
            
            if not recent_documents:
                await self.send_message(
                    chat_id,
                    "❓ No documents found in the database. Use /check_documents to fetch the latest documents.",
                    disable_web_page_preview=True
                )
                return
                
            # Create message with document list
            message = "📄 <b>Recent Company Documents</b>\n\n"
            for i, doc in enumerate(recent_documents, 1):
                company = doc.get('company_name', 'Unknown Company')
                title = doc.get('title', 'Untitled Document')
                date = doc.get('date', 'Unknown Date')
                url = doc.get('url', '#')
                doc_type = doc.get('document_type', 'document')
                
                message += f"{i}. <b>{company}</b>: <a href='{url}'>{title}</a> ({date}) [{doc_type}]\n\n"
                
            # Add check documents button
            keyboard = [[InlineKeyboardButton("🔄 Check for New Documents", callback_data="check_documents")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.send_message(
                chat_id,
                message,
                reply_markup=reply_markup,
                disable_web_page_preview=False  # Enable preview for document links
            )
            
        except Exception as e:
            logger.error(f"Error in documents_command: {e}", exc_info=True)
            await self.send_message(
                chat_id,
                "⚠️ Error retrieving documents. Please try again.",
                disable_web_page_preview=True
            )
    
    async def check_documents_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /check_documents command - manually trigger document check"""
        if not update.effective_chat or not update.message:
            return
            
        chat_id = update.effective_chat.id
        try:
            # Try to delete the command message, continue if not possible
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")
                
            # Show checking message
            checking_message = await self.send_message(
                chat_id,
                "🔄 Checking for new company documents... Please wait.",
                disable_web_page_preview=True
            )
            
            # Force document check
            self._last_document_check = 0  # Reset last check time to force a check
            
            # Load company mapping from data manager
            company_mapping = self.data_manager.load_company_mapping()
            
            if not company_mapping:
                await self.send_message(
                    chat_id,
                    "⚠️ No company mapping available for document scraping.",
                    disable_web_page_preview=True
                )
                return
                
            # Check for new documents
            new_documents = self.document_scraper.check_all_companies(company_mapping)
            
            # Delete checking message
            if checking_message:
                await self.application.bot.delete_message(chat_id=chat_id, message_id=checking_message.message_id)
            
            if new_documents:
                # Send information about new documents
                message = f"✅ Found {len(new_documents)} new documents:\n\n"
                
                for i, document in enumerate(new_documents[:5], 1):  # Show first 5 documents
                    company = document.get('company_name', 'Unknown Company')
                    title = document.get('title', 'Untitled Document')
                    date = document.get('date', 'Unknown Date')
                    url = document.get('url', '#')
                    
                    message += f"{i}. <b>{company}</b>: <a href='{url}'>{title}</a> ({date})\n\n"
                    
                if len(new_documents) > 5:
                    message += f"... and {len(new_documents) - 5} more documents. Use /documents to see all recent documents.\n\n"
                    
                message += "New document notifications will be sent to all users shortly."
                
                await self.send_message(
                    chat_id,
                    message,
                    disable_web_page_preview=False  # Enable preview for document links
                )
                
                # Also trigger sending the notification to all users
                for document in new_documents:
                    if not self.data_manager.is_document_sent(document):
                        # Format and send the message
                        notification = self.format_document_message(document)
                        await self.send_document_notification(notification)
                        
                        # Mark this document as sent
                        self.data_manager.save_sent_document(document)
            else:
                await self.send_message(
                    chat_id,
                    "✅ Document check completed. No new documents found.",
                    disable_web_page_preview=True
                )
                
        except Exception as e:
            logger.error(f"Error in check_documents_command: {e}", exc_info=True)
            await self.send_message(
                chat_id,
                f"⚠️ Error checking documents: {str(e)}",
                disable_web_page_preview=True
            )

    async def company_documents_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /company_documents command - show documents filtered by company"""
        if not update.effective_chat or not update.message:
            return
            
        chat_id = update.effective_chat.id
        try:
            # Try to delete the command message, continue if not possible
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")
            
            # Load company mapping to get all companies
            company_mapping = self.data_manager.load_company_mapping()
            
            # Load document data to check if there are any documents
            document_data = []
            documents_by_company = {}
            
            # Initialize documents_by_company with all companies from mapping
            for company_id, company_name in company_mapping.items():
                documents_by_company[company_id] = []
            
            try:
                document_cache_path = "data/documents_cache.json"
                logger.info(f"Loading documents from {document_cache_path} for company selection")
                if os.path.exists(document_cache_path):
                    with open(document_cache_path, 'r', encoding='utf-8') as f:
                        document_data = json.load(f)
                        
                        # Check if document_data is a list (new format) or dict (old format)
                        if isinstance(document_data, list):
                            # Group documents by company name
                            for doc in document_data:
                                company_name = doc.get('company_name')
                                if not company_name:
                                    continue
                                
                                # Create a slug for the company name to use as ID
                                import re
                                company_id = re.sub(r'[^a-z0-9]', '-', company_name.lower())
                                company_id = re.sub(r'-+', '-', company_id).strip('-')
                                
                                if company_id not in documents_by_company:
                                    documents_by_company[company_id] = []
                                
                                documents_by_company[company_id].append(doc)
                            
                            # Count companies that actually have documents
                            companies_with_docs_count = sum(1 for docs in documents_by_company.values() if docs)
                            logger.info(f"Successfully loaded document data with {companies_with_docs_count} companies with documents (total: {len(documents_by_company)})")
                        else:
                            # Old format - direct dictionary
                            # Add existing documents to our initialized dictionary
                            for company_id, docs in document_data.items():
                                if docs:  # Only add if there are documents
                                    documents_by_company[company_id] = docs
                            
                            # Count companies with docs
                            companies_with_docs_count = sum(1 for docs in documents_by_company.values() if docs)
                            logger.info(f"Successfully loaded document data with {companies_with_docs_count} companies with documents (total: {len(documents_by_company)})")
                else:
                    logger.error(f"Document cache file not found at {document_cache_path}")
            except Exception as e:
                logger.error(f"Error loading document data for company selection: {e}", exc_info=True)
                documents_by_company = {}
            
            if not documents_by_company:
                await self.send_message(
                    chat_id,
                    "❓ No document data available. Use /check_documents to fetch the latest documents.",
                    disable_web_page_preview=True
                )
                return
            
            # Create company buttons for selection
            company_buttons = []
            
            # Get all companies, not just those with documents
            all_companies = []
            for company_id, docs in documents_by_company.items():
                company_name = self.data_manager.get_company_name(company_id) or company_id
                
                # If we don't have a name from data_manager but have docs, try to get from first document
                if company_name == company_id and docs and 'company_name' in docs[0]:
                    company_name = docs[0]['company_name']
                
                # Format company ID as fallback if needed
                if company_name == company_id:
                    company_name = company_id.replace('-', ' ').title()
                    
                # Show a document indicator for companies with documents
                has_docs = bool(docs)
                display_name = f"{company_name} 📄" if has_docs else company_name
                
                all_companies.append((company_id, display_name, has_docs))
            
            # Sort companies by name, with companies with documents first
            all_companies.sort(key=lambda x: (not x[2], x[1]))
            
            # Create buttons, 2 per row
            for i in range(0, len(all_companies), 2):
                row = []
                for company_id, display_name, _ in all_companies[i:i+2]:
                    row.append(InlineKeyboardButton(
                        display_name,
                        callback_data=f"doc_company_{company_id}"
                    ))
                company_buttons.append(row)
            
            # Add "All Companies" button at the top
            company_buttons.insert(0, [InlineKeyboardButton("📄 All Documents", callback_data="view_all_documents")])
            
            # Add cancel button
            company_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
            
            # Show company selection menu
            reply_markup = InlineKeyboardMarkup(company_buttons)
            await self.send_message(
                chat_id,
                "📄 <b>Select a company to view documents:</b>\n"
                "Companies with documents are marked with 📄",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error in company_documents_command: {e}", exc_info=True)
            await self.send_message(
                chat_id,
                "⚠️ Error retrieving company list. Please try again.",
                disable_web_page_preview=True
            )
    
    async def _show_company_documents(self, update: Update, company_id: str) -> None:
        """Show documents for a specific company
        
        Args:
            update: The update object from Telegram
            company_id: The company ID to show documents for
        """
        query = update.callback_query
        
        try:
            # Edit message to show loading
            await query.edit_message_text("🔄 Loading documents... Please wait.", disable_web_page_preview=True)
            
            # Load document data
            document_data = None
            documents_by_company = {}
            
            try:
                document_cache_path = "data/documents_cache.json"
                logger.info(f"Loading documents from {document_cache_path} for company {company_id}")
                if os.path.exists(document_cache_path):
                    with open(document_cache_path, 'r', encoding='utf-8') as f:
                        document_data = json.load(f)
                        
                        # Check if document_data is a list (new format) or dict (old format)
                        if isinstance(document_data, list):
                            # Group documents by company ID
                            for doc in document_data:
                                company_name = doc.get('company_name')
                                if not company_name:
                                    continue
                                
                                # Create a slug for the company name to use as ID
                                import re
                                doc_company_id = re.sub(r'[^a-z0-9]', '-', company_name.lower())
                                doc_company_id = re.sub(r'-+', '-', doc_company_id).strip('-')
                                
                                # Also check if this document belongs to the company we're looking for
                                # by comparing the slugified company name with the requested company_id
                                if doc_company_id == company_id:
                                    if company_id not in documents_by_company:
                                        documents_by_company[company_id] = []
                                    
                                    documents_by_company[company_id].append(doc)
                            
                            logger.info(f"Successfully processed document data: found {len(documents_by_company)} companies in list format")
                        else:
                            # Old format - direct dictionary
                            documents_by_company = document_data
                            logger.info(f"Successfully loaded document data with {len(documents_by_company)} companies in dict format")
                else:
                    logger.error(f"Document cache file not found at {document_cache_path}")
            except Exception as e:
                logger.error(f"Error loading document data for company {company_id}: {e}", exc_info=True)
                
                # Show error message
                await query.edit_message_text(
                    "⚠️ Error loading document data. Please try again.",
                    disable_web_page_preview=True
                )
                return
            
            # Get company name
            company_name = self.data_manager.get_company_name(company_id) or company_id
            
            # If we still only have the ID, try to format it nicely
            if company_name == company_id:
                company_name = company_id.replace('-', ' ').title()
            
            # Check if company has documents
            if company_id not in documents_by_company or not documents_by_company[company_id]:
                # No documents for this company
                keyboard = [[InlineKeyboardButton("« Back to Companies", callback_data="company_documents_back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"❓ No documents found for <b>{company_name}</b>. Use /check_documents to fetch the latest documents.",
                    reply_markup=reply_markup,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                return
            
            # Get documents for this company
            company_docs = documents_by_company[company_id]
            
            # Sort by date (newest first)
            company_docs.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            # Take top 10 documents
            company_docs = company_docs[:10]
            
            # Create message with document list
            message = f"📄 <b>Documents for {company_name}</b>\n\n"
            for i, doc in enumerate(company_docs, 1):
                title = doc.get('title', 'Untitled Document')
                date = doc.get('date', 'Unknown Date')
                url = doc.get('url', '#')
                doc_type = doc.get('document_type', '')
                
                # Add document type if available
                type_text = f" ({doc_type})" if doc_type else ""
                
                message += f"{i}. <a href='{url}'>{title}</a>{type_text} - {date}\n\n"
            
            # Add check documents button and back button
            keyboard = [
                [InlineKeyboardButton("🔄 Check for New Documents", callback_data="check_documents")],
                [InlineKeyboardButton("« Back to Companies", callback_data="company_documents_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='HTML',
                disable_web_page_preview=False  # Enable preview for document links
            )
        except Exception as e:
            logger.error(f"Error in _show_company_documents: {e}", exc_info=True)
            try:
                # Try to send a meaningful error message
                keyboard = [
                    [InlineKeyboardButton("« Back to Companies", callback_data="company_documents_back")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "⚠️ Error retrieving documents. Please try again.",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            except Exception as inner_e:
                logger.error(f"Error sending error message: {inner_e}", exc_info=True)

if __name__ == "__main__":
    bot = MintosBot()
    asyncio.run(bot.run())