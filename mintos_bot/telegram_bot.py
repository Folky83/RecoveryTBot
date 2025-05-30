from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import time
import html
import hashlib
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
    DOCUMENT_SCRAPE_INTERVAL_HOURS,
    DOCUMENT_TYPES
)
from .data_manager import DataManager
from .mintos_client import MintosClient
from .document_scraper import DocumentScraper
from .user_manager import UserManager
from .rss_reader import RSSReader

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
    _rss_task: Optional[asyncio.Task] = None

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
            self.rss_reader = RSSReader()
            self._polling_task: Optional[asyncio.Task] = None
            self._update_task: Optional[asyncio.Task] = None
            self._campaign_task: Optional[asyncio.Task] = None
            self._rss_task: Optional[asyncio.Task] = None
            self._is_startup_check = True  # Flag to indicate first check after startup
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
        for task_name, task in [("polling", self._polling_task), ("update", self._update_task), ("campaign", self._campaign_task), ("rss", self._rss_task)]:
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
                if hasattr(self.application, 'updater') and self.application.updater and self.application.updater.running:
                    await self.application.updater.stop()
                    await asyncio.sleep(1)

                if hasattr(self.application, 'bot') and self.application.bot:
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
            CommandHandler("campaigns", self.campaigns_command),
            CommandHandler("documents", self.documents_command),
            CommandHandler("notifications", self.notifications_command),
            CommandHandler("rss", self.rss_command),
            CommandHandler("trigger_today", self.trigger_today_command),
            CommandHandler("users", self.users_command), #Added
            CommandHandler("admin", self.admin_command), #Added admin command
            CommandHandler("refresh", self.refresh_command), # Admin only - moved to admin section
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
            
            # Check for company updates
            await self.check_updates()
            logger.info("Update check completed")
            
            # Check for document updates
            await self.check_documents()
            logger.info("Document check completed")
            

            
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
                if self.application and self.application.updater:
                    self._polling_task = asyncio.create_task(
                        self.application.updater.start_polling(
                            drop_pending_updates=True,
                            allowed_updates=["message", "callback_query"]
                        )
                    )

                # Start scheduled updates
                self._update_task = asyncio.create_task(self.scheduled_updates())
                
                # Start campaign updates (every 5 minutes)
                self._campaign_task = asyncio.create_task(self.scheduled_campaign_updates())
                
                # Start RSS updates
                self._rss_task = asyncio.create_task(self.scheduled_rss_updates())

                # Wait for all tasks
                await asyncio.gather(self._polling_task, self._update_task, self._campaign_task, self._rss_task)
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
        admin_commands = ""
        if show_admin:
            admin_commands = (
                "• /admin - Admin control panel\n"
            )
        
        return (
            "🚀 Welcome to Mintos Update Bot!\n\n"
            "📅 Update Schedule:\n"
            "• Automatic updates on weekdays at 3 PM, 4 PM, and 5 PM (UTC)\n"
            "• Document scraping happens daily\n\n"
            "📊 Data Commands:\n"
            "• /company - Check updates for a specific company\n"
            "• /today [YYYY-MM-DD] - View updates for today or a specific date\n"
            "• /campaigns - View current Mintos campaigns\n"
            "• /documents - View recent company documents\n\n"
            "🔔 Notification Settings:\n"
            "• /notifications - Manage notification preferences\n"
            "• /rss - RSS news feed subscriptions\n\n"
            "ℹ️ Other:\n"
            "• /start - Show this welcome message\n"
            f"{admin_commands}\n"
            "Customize your notifications to receive updates about lending companies, documents, campaigns, and news feeds."
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
            if not query:
                return
            
            await query.answer()

            if not query.data:
                return
                
            if query.data.startswith("company_"):
                company_id = int(query.data.split("_")[1])
                company_name = self.data_manager.get_company_name(company_id)

                buttons = [
                    [InlineKeyboardButton("Latest Update", callback_data=f"latest_{company_id}")],
                    [InlineKeyboardButton("All Updates", callback_data=f"all_{company_id}_0")]
                ]
                reply_markup = InlineKeyboardMarkup(buttons)
                if query.message:
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
                
            elif query.data == "use_current_cache":
                chat_id = update.effective_chat.id
                await query.edit_message_text("Using current cached data...", disable_web_page_preview=True)
                
                try:
                    # Create a fresh update but use existing context
                    new_update = Update(update.update_id, message=update.effective_message)
                    await self.today_command(new_update, context)
                except Exception as e:
                    logger.error(f"Error displaying cached updates: {e}")
                    await query.edit_message_text("⚠️ Error displaying updates. Please try again.", disable_web_page_preview=True)
                return
                
            elif query.data == "refresh_documents":
                chat_id = update.effective_chat.id
                # Improved refresh message with HTML formatting for consistency
                await query.edit_message_text(
                    "🔄 <b>Refreshing documents...</b>\n\n"
                    "Checking for new presentations, financials, and loan agreements "
                    "across all companies. This may take a moment.",
                    disable_web_page_preview=True,
                    parse_mode='HTML'
                )

                try:
                    # Force document check
                    new_documents = await self.check_documents()
                    
                    # Show count of new documents found
                    if new_documents:
                        await self.send_message(
                            chat_id,
                            f"✅ <b>Refresh completed</b>\n\n"
                            f"Found {len(new_documents)} new document(s).",
                            disable_web_page_preview=True
                        )
                    
                    # Run documents command again to display updated list
                    await self.documents_command(update, context)
                except Exception as e:
                    logger.error(f"Error during document refresh from callback: {e}", exc_info=True)
                    await query.edit_message_text(
                        "⚠️ <b>Error refreshing documents</b>\n\n"
                        "An error occurred while checking for new documents. "
                        "Please try again later or contact the administrator.",
                        disable_web_page_preview=True,
                        parse_mode='HTML'
                    )
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
                
            elif query.data.startswith("admin_trigger_today"):
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                
                # Check if there's a date parameter
                parts = query.data.split("_")
                target_date = None
                if len(parts) >= 4:
                    # Format should be admin_trigger_today_YYYY-MM-DD
                    target_date = parts[3]
                
                # First show date selection options if no date was specified
                if query.data == "admin_trigger_today":
                    keyboard = [
                        [InlineKeyboardButton("Today's Updates", callback_data="admin_trigger_today_select")],
                        [InlineKeyboardButton("Specify Custom Date", callback_data="admin_trigger_today_date")]
                    ]
                    # Add back button
                    keyboard.append([InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")])
                    
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(
                        "📅 <b>Send Updates</b>\n\n"
                        "Select an option:",
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                    return
                
                # Handle custom date input request
                elif query.data == "admin_trigger_today_date":
                    await query.edit_message_text(
                        "📅 <b>Enter Custom Date</b>\n\n"
                        "Please enter the date in YYYY-MM-DD format.\n"
                        "Example: 2025-04-19\n\n"
                        "Reply directly to this message with the date.",
                        parse_mode='HTML'
                    )
                    # The date input will be handled by a message handler
                    return
                
                # Continue with user selection using either today's date or the specified date
                elif query.data == "admin_trigger_today_select" or target_date:
                    # Get all registered users
                    users = self.user_manager.get_all_users()
                    
                    if not users:
                        # No users found
                        keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        date_text = "Today's" if not target_date else f"{target_date}"
                        await query.edit_message_text(
                            f"🔄 <b>Send {date_text} Updates</b>\n\n"
                            "No registered users found.",
                            reply_markup=reply_markup,
                            parse_mode='HTML'
                        )
                        return
                    
                    # Create buttons for each user
                    keyboard = []
                    for i, user_id in enumerate(users, 1):
                        username = self.user_manager.get_user_info(user_id) or "Unknown"
                        display_name = f"@{username}" if username != "Unknown" else f"User {user_id}"
                        button_text = f"{i}. {display_name}"
                        
                        # Add date parameter to callback data if specified
                        if target_date:
                            callback_data = f"trigger_today_{user_id}_{target_date}"
                        else:
                            callback_data = f"trigger_today_{user_id}"
                            
                        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
                    
                    # Add predefined channel option
                    if target_date:
                        mintos_callback = f"trigger_today_-1002373856504_{target_date}"
                    else:
                        mintos_callback = "trigger_today_-1002373856504"
                    keyboard.append([InlineKeyboardButton("📺 Mintos Unofficial News Channel", callback_data=mintos_callback)])
                    
                    # Add custom channel button
                    if target_date:
                        custom_callback = f"trigger_today_custom_{target_date}"
                    else:
                        custom_callback = "trigger_today_custom"
                    keyboard.append([InlineKeyboardButton("✏️ Enter custom channel ID", callback_data=custom_callback)])
                    
                    # Add back button
                    keyboard.append([InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")])
                    
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    date_text = "today's" if not target_date else f"updates for {target_date}"
                    await query.edit_message_text(
                        f"🔄 <b>Send {date_text.capitalize()}</b>\n\n"
                        f"Select a channel to send {date_text} to:",
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                    return
                
            elif query.data == "admin_refresh_updates":
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                
                # Edit message to show processing
                await query.edit_message_text("🔄 Refreshing updates, please wait...", disable_web_page_preview=True)
                
                try:
                    # Force update check regardless of hour
                    await self._safe_update_check()
                    
                    # Add back button
                    keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    # Get cache information
                    cache_age_minutes = int(self.data_manager.get_cache_age() / 60) if not math.isinf(self.data_manager.get_cache_age()) else float('inf')
                    
                    # Format cache age for display
                    if math.isinf(cache_age_minutes):
                        cache_age_text = "Unknown"
                    else:
                        hours = cache_age_minutes // 60
                        minutes = cache_age_minutes % 60
                        if hours > 0:
                            cache_age_text = f"{hours}h {minutes}m"
                        else:
                            cache_age_text = f"{minutes}m"
                    
                    # Get updates count
                    updates = self.data_manager.load_previous_updates()
                    update_count = len(updates) if updates else 0
                    
                    await query.edit_message_text(
                        f"✅ <b>Update check completed successfully!</b>\n\n"
                        f"📊 Total companies in cache: {update_count}\n"
                        f"⏱️ Cache freshness: {cache_age_text}\n\n"
                        f"<i>Updates are checked automatically on weekdays at 3-5 PM UTC.</i>",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error refreshing updates: {e}", exc_info=True)
                    # Add back button
                    keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        f"⚠️ <b>Error refreshing updates</b>\n\n"
                        f"{str(e)}\n\n"
                        f"<i>Please check the logs for more information.</i>",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True,
                        parse_mode='HTML'
                    )
                return
                
            elif query.data == "admin_refresh_documents":
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                
                # Edit message to show processing
                await query.edit_message_text("🔄 Refreshing documents, please wait...", disable_web_page_preview=True)
                
                # Perform document check
                try:
                    await self.check_documents()
                    # Add back button
                    keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    # Get documents count information
                    previous_documents = self.document_scraper.load_previous_documents()
                    doc_count = len(previous_documents)
                    
                    await query.edit_message_text(
                        f"✅ Document check completed successfully!\n\n"
                        f"📃 Total documents in cache: {doc_count}\n\n"
                        f"Documents are checked once daily by default.",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.error(f"Error refreshing documents: {e}", exc_info=True)
                    # Add back button
                    keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        f"⚠️ Error refreshing documents: {str(e)}\n\n"
                        f"Please check the logs for more information.",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
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
                
            elif query.data.startswith("trigger_today_"):
                # Extract data from callback
                callback_parts = query.data.split("_")
                
                # Check if it's the custom input callback
                if len(callback_parts) >= 3 and callback_parts[2] == "custom":
                    # Handle the custom channel ID entry request
                    # Check if there's a date parameter
                    target_date = None
                    if len(callback_parts) >= 4:
                        target_date = callback_parts[3]
                        date_text = f" for date {target_date}"
                    else:
                        date_text = ""
                        
                    await query.edit_message_text(
                        f"📝 Please enter the channel ID to send updates{date_text} to.\n\n"
                        "Format: -100xxxxxxxxxx\n"
                        "Example: -1001234567890\n\n"
                        "Reply directly to this message with the channel ID.",
                        disable_web_page_preview=True
                    )
                    # The actual sending will be handled in a message handler
                    return
                
                # Regular channel selection from the list
                target_channel = callback_parts[2]
                chat_id = update.effective_chat.id
                
                # Check for a date parameter in the callback data
                target_date = None
                if len(callback_parts) >= 4:
                    # The format is trigger_today_channelid_date
                    target_date = callback_parts[3]
                
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                
                # Create appropriate message based on whether we're checking today or a specific date
                date_text = ""
                if target_date:
                    date_text = f" for {target_date}"
                
                # Edit message to show processing
                await query.edit_message_text(f"🔄 Processing updates{date_text}, please wait...", disable_web_page_preview=True)
                
                # Send updates to the selected channel
                await self._send_today_updates_to_channel(chat_id, target_channel, target_date)
                return
                
            elif query.data == "admin_send_rss":
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                
                # Show RSS items selection
                await self._show_rss_items_selection(query)
                return
                
            elif query.data == "admin_exit":
                # Close the admin panel
                await query.edit_message_text("✅ Admin panel closed.", disable_web_page_preview=True)
                return
                
            elif query.data == "admin_back":
                # Check if user is admin
                if not await self.is_admin(update.effective_user.id):
                    await query.edit_message_text("⚠️ Access denied. Only admin can use this feature.", disable_web_page_preview=True)
                    return
                    
                # Return to admin panel
                keyboard = [
                    [InlineKeyboardButton("👥 View Users", callback_data="admin_users")],
                    [InlineKeyboardButton("🔄 Refresh Updates", callback_data="admin_refresh_updates")],
                    [InlineKeyboardButton("📄 Refresh Documents", callback_data="admin_refresh_documents")],
                    [InlineKeyboardButton("📤 Send Updates", callback_data="admin_trigger_today")],
                    [InlineKeyboardButton("📰 Send RSS Items", callback_data="admin_send_rss")],
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

            elif query.data.startswith("rss_toggle_"):
                # Legacy support - enable/disable all feeds
                chat_id = query.data.split("_")[2]
                current_preference = self.user_manager.get_rss_preference(chat_id)
                new_preference = not current_preference
                self.user_manager.set_rss_preference(chat_id, new_preference)
                
                status = "enabled" if new_preference else "disabled"
                await query.edit_message_text(
                    f"✅ <b>RSS Notifications {status.title()}</b>\n\n"
                    f"All RSS feed notifications are now <b>{status}</b>.",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                return
            
            elif query.data.startswith("notify_"):
                # Handle notification preference toggles
                parts = query.data.split("_", 2)  # notify_type_value
                notification_type = parts[1]
                new_value = parts[2] == "True"
                
                chat_id = query.message.chat_id
                self.user_manager.set_notification_preference(chat_id, notification_type, new_value)
                
                # Get updated preferences to refresh the interface
                preferences = self.user_manager.get_user_notification_preferences(chat_id)
                
                # Create status indicators
                campaigns_status = "✅" if preferences.get('campaigns', True) else "❌"
                recovery_status = "✅" if preferences.get('recovery_updates', True) else "❌"
                documents_status = "✅" if preferences.get('documents', True) else "❌"
                
                # Create updated keyboard
                keyboard = [
                    [InlineKeyboardButton(
                        f"{campaigns_status} Campaigns",
                        callback_data=f"notify_campaigns_{not preferences.get('campaigns', True)}"
                    )],
                    [InlineKeyboardButton(
                        f"{recovery_status} Recovery Updates", 
                        callback_data=f"notify_recovery_updates_{not preferences.get('recovery_updates', True)}"
                    )],
                    [InlineKeyboardButton(
                        f"{documents_status} Documents",
                        callback_data=f"notify_documents_{not preferences.get('documents', True)}"
                    )],
                    [InlineKeyboardButton("❌ Close", callback_data="cancel")]
                ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Map notification types to friendly names
                type_names = {
                    'campaigns': 'Campaigns',
                    'recovery_updates': 'Recovery Updates',
                    'documents': 'Documents'
                }
                
                type_name = type_names.get(notification_type, notification_type)
                status = "enabled" if new_value else "disabled"
                
                message = (
                    "🔔 <b>Notification Settings</b>\n\n"
                    "Manage which types of notifications you receive:\n\n"
                    f"{campaigns_status} <b>Campaigns:</b> New Mintos campaigns and bonuses\n"
                    f"{recovery_status} <b>Recovery Updates:</b> Company recovery status changes\n"
                    f"{documents_status} <b>Documents:</b> New company documents\n\n"
                    "Click the buttons below to toggle notifications on/off:"
                )
                
                await query.edit_message_text(
                    message,
                    reply_markup=reply_markup,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                return
                
            elif query.data.startswith("feed_toggle_"):
                # Handle individual feed toggle
                parts = query.data.split("_")
                feed_source = parts[2]  # nasdaq, mintos, or ffnews
                chat_id = parts[3]
                
                current_preference = self.user_manager.get_feed_preference(chat_id, feed_source)
                new_preference = not current_preference
                self.user_manager.set_feed_preference(chat_id, feed_source, new_preference)
                
                # Get feed display names
                feed_names = {
                    'nasdaq': 'NASDAQ Baltic',
                    'mintos': 'Mintos News',
                    'ffnews': 'FFNews'
                }
                
                feed_name = feed_names.get(feed_source, feed_source)
                status = "enabled" if new_preference else "disabled"
                
                # Show updated subscription menu
                user_prefs = self.user_manager.get_user_feed_preferences(chat_id)
                nasdaq_enabled = user_prefs.get('nasdaq', False)
                mintos_enabled = user_prefs.get('mintos', False)
                ffnews_enabled = user_prefs.get('ffnews', False)
                
                # Build updated keyboard
                keyboard = [
                    [InlineKeyboardButton(
                        f"{'✅' if nasdaq_enabled else '⭕'} NASDAQ Baltic (filtered)",
                        callback_data=f"feed_toggle_nasdaq_{chat_id}"
                    )],
                    [InlineKeyboardButton(
                        f"{'✅' if mintos_enabled else '⭕'} Mintos News (all articles)",
                        callback_data=f"feed_toggle_mintos_{chat_id}"
                    )],
                    [InlineKeyboardButton(
                        f"{'✅' if ffnews_enabled else '⭕'} FFNews (filtered)",
                        callback_data=f"feed_toggle_ffnews_{chat_id}"
                    )],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                enabled_count = sum([nasdaq_enabled, mintos_enabled, ffnews_enabled])
                
                await query.edit_message_text(
                    f"📰 <b>RSS Feed Subscriptions</b>\n\n"
                    f"✅ <b>{feed_name}</b> notifications {status}\n"
                    f"You have <b>{enabled_count}</b> feed(s) enabled\n\n"
                    f"<b>Available feeds:</b>\n"
                    f"• <b>NASDAQ Baltic</b> - Filtered news about Mintos, DelfinGroup, Grenardi, etc.\n"
                    f"• <b>Mintos News</b> - All articles from Mintos blog\n"
                    f"• <b>FFNews</b> - Financial news filtered by keywords\n\n"
                    f"Click on any feed to toggle notifications:",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                return
                
            elif query.data.startswith("rss_item_select_"):
                # Handle RSS item selection for sending
                await self._handle_rss_item_selection(query)
                return
                
            elif query.data.startswith("send_rss_to_"):
                # Handle sending selected RSS items to a user/channel
                await self._handle_send_rss_items(query)
                return
                
            elif query.data == "cancel":
                # Make the cancellation message more attractive and consistent
                await query.edit_message_text(
                    "✅ <b>Operation cancelled</b>\n\n"
                    "Menu has been closed successfully.",
                    disable_web_page_preview=True,
                    parse_mode='HTML'
                )
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
                    disable_web_page_preview=msg.get('disable_web_page_preview', True),
                    parse_mode=msg.get('parse_mode', 'HTML')
                )
                logger.info(f"Successfully resent message to {msg['chat_id']}")
            except Exception as e:
                logger.error(f"Failed to resend message: {e}")
                self._failed_messages.append(msg)

    async def send_message(self, chat_id: Union[int, str], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, disable_web_page_preview: bool = False, parse_mode: Optional[str] = None) -> None:
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
                    parse_mode=parse_mode or 'HTML',
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
                        'reply_markup': reply_markup,
                        'parse_mode': parse_mode,
                        'disable_web_page_preview': disable_web_page_preview
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

    async def notifications_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /notifications command - manage notification preferences"""
        try:
            if not update.message:
                return

            # Try to delete the command message
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")

            chat_id = update.effective_chat.id
            
            # Get current notification preferences
            preferences = self.user_manager.get_user_notification_preferences(chat_id)
            
            # Create status indicators
            campaigns_status = "✅" if preferences.get('campaigns', True) else "❌"
            recovery_status = "✅" if preferences.get('recovery_updates', True) else "❌"
            documents_status = "✅" if preferences.get('documents', True) else "❌"
            
            # Create keyboard with toggle buttons
            keyboard = [
                [InlineKeyboardButton(
                    f"{campaigns_status} Campaigns",
                    callback_data=f"notify_campaigns_{not preferences.get('campaigns', True)}"
                )],
                [InlineKeyboardButton(
                    f"{recovery_status} Recovery Updates", 
                    callback_data=f"notify_recovery_updates_{not preferences.get('recovery_updates', True)}"
                )],
                [InlineKeyboardButton(
                    f"{documents_status} Documents",
                    callback_data=f"notify_documents_{not preferences.get('documents', True)}"
                )],
                [InlineKeyboardButton("❌ Close", callback_data="cancel")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = (
                "🔔 <b>Notification Settings</b>\n\n"
                "Manage which types of notifications you receive:\n\n"
                f"{campaigns_status} <b>Campaigns:</b> New Mintos campaigns and bonuses\n"
                f"{recovery_status} <b>Recovery Updates:</b> Company recovery status changes\n"
                f"{documents_status} <b>Documents:</b> New company documents\n\n"
                "Click the buttons below to toggle notifications on/off:"
            )
            
            await self.send_message(
                chat_id,
                message,
                reply_markup,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Notifications command error: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error processing command", disable_web_page_preview=True)
        
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
                # Get all updates for today (both new and existing)
                today_updates = [update for update in added_updates if update.get('date') == today]
                logger.info(f"Found {len(today_updates)} updates for today ({today})")

                if today_updates:
                    # Filter for updates that haven't been sent yet
                    unsent_updates = [
                        update for update in today_updates 
                        if not self.data_manager.is_update_sent(update)
                    ]
                    logger.info(f"Found {len(unsent_updates)} unsent updates for today")

                    if unsent_updates:
                        # Send each individual update to all users
                        logger.info(f"Broadcasting {len(unsent_updates)} unsent updates to {len(users)} users")
                        for i, update in enumerate(unsent_updates):
                            message = self.format_update_message(update)
                            for user_id in users:
                                # Check if user has recovery updates notifications enabled
                                if self.user_manager.get_notification_preference(user_id, 'recovery_updates'):
                                    try:
                                        await self.send_message(user_id, message, disable_web_page_preview=True)
                                        logger.info(f"Successfully sent update {i+1}/{len(unsent_updates)} to user {user_id}")
                                    except Exception as e:
                                        logger.error(f"Failed to send update to user {user_id}: {e}")
                                else:
                                    logger.debug(f"Skipping recovery update for user {user_id} - notifications disabled")
                            
                            # Mark as sent after broadcasting to all users
                            self.data_manager.save_sent_update(update)
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

            # Campaign checking is now handled by the separate scheduled_campaign_updates task

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
                    admin_id = 114691530  # Hardcoded admin ID
                    
                    for i, campaign in enumerate(unsent_campaigns):
                        message = self.format_campaign_message(campaign)
                        
                        # Send immediately to admin
                        try:
                            await self.send_message(admin_id, message, disable_web_page_preview=True)
                            logger.info(f"Successfully sent campaign {i+1}/{len(unsent_campaigns)} to admin {admin_id}")
                        except Exception as e:
                            logger.error(f"Failed to send campaign to admin {admin_id}: {e}")
                        
                        # Add to pending notifications for other users (4-hour delay)
                        self.data_manager.add_pending_campaign(campaign, admin_notified=True)
                        logger.info(f"Added campaign {campaign.get('id')} to pending notifications for delayed sending")
                        
                        # Mark as sent to admin but not to other users yet
                        # We'll mark it as fully sent when we process pending campaigns
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

    async def check_documents(self) -> None:
        """Check for document updates from loan originators"""
        try:
            logger.info("Checking for new company documents...")
            
            # Check if it's time to scrape documents based on interval
            now = datetime.now()
            cache_age_hours = self.document_scraper.get_cache_age() / 3600
            
            # Only scrape documents if the cache is older than the configured interval
            # or if this is the first check after startup
            if cache_age_hours < DOCUMENT_SCRAPE_INTERVAL_HOURS and not self._is_startup_check:
                logger.info(f"Document cache is {cache_age_hours:.1f} hours old (< {DOCUMENT_SCRAPE_INTERVAL_HOURS}h), skipping document check")
                return
                
            logger.info("Starting document scraping...")
            
            # Use the improved document scraper to check for updates
            added_documents = await self.document_scraper.check_document_updates()
            
            if not added_documents:
                logger.info("No new documents found")
                
                # Reset the startup check flag after first run
                self._is_startup_check = False
                return
            
            logger.info(f"Found {len(added_documents)} new or updated documents")
            
            users = self.user_manager.get_all_users()
            logger.info(f"Processing {len(added_documents)} new documents for {len(users)} users")
            
            # Check if this is during app startup
            is_startup = getattr(self, '_is_startup_check', True)
            if is_startup:
                logger.info("Skipping notifications during startup")
                # Mark documents as sent without actually sending
                for document in added_documents:
                    self.document_scraper.save_sent_document(document)
                return
            
            # Send to all users
            user_count = 0
            # First, filter only documents that haven't been sent today
            unsent_documents = []
            for document in added_documents:
                if not self.document_scraper.is_document_sent(document):
                    unsent_documents.append(document)
                else:
                    logger.debug(f"Document {document.get('title')} for {document.get('company_name')} already sent today, skipping")
            
            logger.info(f"Found {len(unsent_documents)} unsent documents of {len(added_documents)} total")
            
            # Send each unsent document to all users
            for document in unsent_documents:
                message = self.format_document_message(document)
                sent_to_users = 0
                
                # Send to all users
                for chat_id in users:
                    # Check if user has document notifications enabled
                    if self.user_manager.get_notification_preference(chat_id, 'documents'):
                        try:
                            await self.send_message(chat_id, message, disable_web_page_preview=True)
                            sent_to_users += 1
                            logger.info(f"Sent document notification for {document.get('company_name')} to {chat_id}")
                        except Exception as e:
                            logger.error(f"Error sending document update to {chat_id}: {e}")
                            # Add to failed messages for retry
                            self._failed_messages.append({
                                'chat_id': chat_id,
                                'text': message,
                                'parse_mode': 'HTML',
                                'disable_web_page_preview': True
                            })
                    else:
                        logger.debug(f"Skipping document for user {chat_id} - notifications disabled")
                
                # Mark as sent after trying to send to all users
                self.document_scraper.save_sent_document(document)
                logger.info(f"Document for {document.get('company_name')} sent to {sent_to_users} users and marked as sent")
                
                # Update user count
                user_count += sent_to_users
                        
            if user_count > 0:
                logger.info(f"Sent document updates to {user_count} users")
                
            # Reset the startup check flag after first run
            self._is_startup_check = False
                
        except Exception as e:
            logger.error(f"Error during document check: {e}", exc_info=True)
            for user_id in self.user_manager.get_all_users():
                try:
                    await self.send_message(user_id, "⚠️ Error occurred while checking for documents", disable_web_page_preview=True)
                except Exception as nested_e:
                    logger.error(f"Failed to send document error notification to user {user_id}: {nested_e}")
    
    def format_document_message(self, document: Dict[str, Any]) -> str:
        """Format document message with rich information and consistent styling"""
        company_name = document.get('company_name', 'Unknown Company')
        document_title = document.get('title', 'Untitled Document')
        document_type = document.get('type', 'Document')
        document_date = document.get('date', 'Unknown date')
        document_url = document.get('url', '#')
        
        # Ensure the URL is properly formatted
        if document_url and not document_url.startswith(('http://', 'https://')):
            document_url = f"https://{document_url}"
        
        # Get company page URL from document or create it from company name
        company_page_url = document.get('company_page_url')
        if not company_page_url:
            company_page_url = f"https://www.mintos.com/en/lending-companies/{company_name.replace(' ', '')}/"
        
        # Match the emoji to the document types shown in the image
        emoji_map = {
            'presentation': '📊',
            'financials': '💰',
            'loan_agreement': '🤝',
            'company_page': '🏢',
            'document': '📃'
        }
        
        emoji = emoji_map.get(document_type.lower(), '📃')
        
        # Format title case for document type display
        display_type = document_type.replace('_', ' ').title()
        
        # Create a visually appealing, consistently styled message
        message = (
            f"{emoji} <b>{display_type}</b> from <b>{company_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📄 <b>Title:</b> {document_title}\n"
            f"📅 <b>Date:</b> {document_date}\n\n"
            f"🔗 <b>Links:</b>\n"
            f"└ <a href=\"{document_url}\">View Document</a>\n"
            f"└ <a href=\"{company_page_url}\">Company Page</a>"
        )
        
        return message
            
    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /today command to show updates for today or a specified date (format: YYYY-MM-DD)"""
        chat_id = None
        try:
            if not update.message or not update.effective_chat:
                logger.error("Invalid update object: message or effective_chat is None")
                return

            chat_id = update.effective_chat.id
            
            # Check if a date was specified in the command arguments
            target_date = time.strftime("%Y-%m-%d")  # Default to today
            
            # Extract the date parameter from context.args if provided
            args = context.args if context and hasattr(context, 'args') else None
            if args and args[0]:
                try:
                    # Validate date format (YYYY-MM-DD)
                    specified_date = args[0].strip()
                    # Simple validation of the date format
                    if len(specified_date) == 10 and specified_date[4] == '-' and specified_date[7] == '-':
                        # Further validate it's a proper date
                        datetime.strptime(specified_date, "%Y-%m-%d")
                        target_date = specified_date
                        logger.info(f"Using specified date: {target_date}")
                    else:
                        await self.send_message(chat_id, "⚠️ Invalid date format. Please use YYYY-MM-DD format.", disable_web_page_preview=True)
                        return
                except ValueError as e:
                    logger.error(f"Invalid date format: {e}")
                    await self.send_message(chat_id, "⚠️ Invalid date. Please use YYYY-MM-DD format (e.g., 2025-04-19).", disable_web_page_preview=True)
                    return
            
            logger.info(f"Processing /today command for chat_id: {chat_id}, date: {target_date}")

            # Always try to delete the command message
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")

            # Check cache age and refresh if needed
            cache_age = self.data_manager.get_cache_age()
            cache_age_minutes = int(cache_age / 60) if not math.isinf(cache_age) else float('inf')
            cache_age_hours = cache_age_minutes / 60

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
            # If cache is older than 3 hours but less than 6 hours, offer refresh option
            elif cache_age_hours > 3:
                logger.info(f"Cache is moderately old ({cache_age_hours:.1f} hours), offering refresh option")
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh Cache", callback_data="refresh_cache")],
                    [InlineKeyboardButton("Continue with current data", callback_data="use_current_cache")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await self.send_message(
                    chat_id, 
                    f"📊 Cache is {cache_age_hours:.1f} hours old. Would you like to refresh before viewing updates?", 
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                return  # Exit and wait for callback

            updates = self.data_manager.load_previous_updates()
            if not updates:
                logger.warning("No updates found in cache")
                await self.send_message(chat_id, "No cached updates found. Try using the admin refresh option.", disable_web_page_preview=True)
                return

            # Get the (possibly new) cache age
            cache_age = self.data_manager.get_cache_age()
            logger.debug(f"Using cached data (age: {cache_age:.0f} seconds)")

            logger.debug(f"Searching for updates on date: {target_date}")
            date_updates = []

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
                        if item.get('date') == target_date:
                            update_with_company = {
                                "lender_id": lender_id,
                                "company_name": company_name,
                                **year_data,
                                **item
                            }
                            date_updates.append(update_with_company)
                            logger.debug(f"Found update for {company_name} on {target_date}")

            # Check if we have any updates
            have_updates = len(date_updates) > 0

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

                # Format message differently depending on whether we're looking at today or a specific date
                is_today = target_date == time.strftime("%Y-%m-%d")
                date_desc = "today" if is_today else f"date {target_date}"
                
                logger.info(f"No updates found for {date_desc}. {cache_message}")

                # Create a message with a refresh button if cache is old
                if minutes_old > 120:  # If cache is older than 2 hours
                    keyboard = [[InlineKeyboardButton("🔄 Refresh Now", callback_data="refresh_cache")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await self.send_message(
                        chat_id, 
                        f"No updates found for {date_desc} ({cache_message}).\nWould you like to check for new updates?",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                else:
                    await self.send_message(chat_id, f"No updates found for {date_desc} ({cache_message.lower()}).", disable_web_page_preview=True)
                return

            # If we have updates, send them
            # Send header message with total count
            date_desc = "today" if target_date == time.strftime("%Y-%m-%d") else target_date
            header_message = f"📅 Found {len(date_updates)} updates for {date_desc}:\n"
            await self.send_message(chat_id, header_message, disable_web_page_preview=True)

            # Send each update individually
            for i, update_item in enumerate(date_updates, 1):
                try:
                    message = self.format_update_message(update_item)
                    await self.send_message(chat_id, message, disable_web_page_preview=True)
                    logger.debug(f"Successfully sent update {i}/{len(date_updates)} to {chat_id}")
                    # The send_message method already has adaptive delays built in
                except RetryAfter as e:
                    # If we hit rate limiting, wait the required time plus a buffer
                    wait_time = e.retry_after + 0.5
                    logger.warning(f"Rate limited by Telegram. Waiting {wait_time} seconds")
                    await asyncio.sleep(wait_time)
                    
                    # Retry sending after waiting
                    try:
                        await self.send_message(chat_id, message, disable_web_page_preview=True)
                        logger.debug(f"Successfully sent update {i}/{len(date_updates)} after rate limit wait")
                    except Exception as retry_err:
                        logger.error(f"Failed to send update {i} after rate limit wait: {retry_err}", exc_info=True)
                        continue
                except Exception as e:
                    logger.error(f"Error sending update {i}/{len(date_updates)}: {e}", exc_info=True)
                    continue

        except Exception as e:
            error_msg = f"Error in today_command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if chat_id:
                await self.send_message(chat_id, "⚠️ Error getting updates. Please try again.", disable_web_page_preview=True)
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
        """Force an immediate update check with cooldown period (admin only)"""
        if not update.effective_chat or not update.effective_user:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        # Check if user is admin
        if not await self.is_admin(user_id):
            logger.warning(f"Non-admin user {user_id} attempted to use /refresh command")
            await self.send_message(
                chat_id,
                "⚠️ This command is only available to administrators.", 
                disable_web_page_preview=True
            )
            # Try to delete the command message
            try:
                if update.message:
                    await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")
            return
            
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

    async def documents_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /documents command to show recent company documents"""
        if not update.effective_chat or not update.message:
            return
        
        chat_id = update.effective_chat.id
        
        try:
            # Try to delete the command message, continue if not possible
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete command message: {e}")
                
            # Get documents
            previous_documents = self.document_scraper.load_previous_documents()
            
            if not previous_documents:
                await self.send_message(
                    chat_id, 
                    "No documents found in cache. Use the refresh button to check for documents.", 
                    disable_web_page_preview=True
                )
            else:
                # Sort documents by date (newest first)
                sorted_documents = sorted(
                    previous_documents, 
                    key=lambda x: datetime.strptime(x.get('date', '1900-01-01'), '%Y-%m-%d') if x.get('date') else datetime.min,
                    reverse=True
                )
                
                # Get the 5 most recent documents
                recent_documents = sorted_documents[:5]
                
                await self.send_message(
                    chat_id,
                    f"📄 <b>Recent Company Documents</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Showing the {len(recent_documents)} most recent documents from Mintos loan originators:",
                    disable_web_page_preview=True,
                    parse_mode='HTML'
                )
                
                # Send each document
                for document in recent_documents:
                    message = self.format_document_message(document)
                    await self.send_message(chat_id, message, disable_web_page_preview=True, parse_mode='HTML')
            
            # Add refresh button with cancel button
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh Documents", callback_data="refresh_documents")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            cache_age_hours = self.document_scraper.get_cache_age() / 3600
            
            # Make the message wider with dashes to match other messages
            await self.send_message(
                chat_id, 
                f"📄 <b>Document Information</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Document cache is {cache_age_hours:.1f} hours old.\n\n"
                f"<i>Use the buttons below to check for new documents or close this menu.</i>",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Error in documents_command: {e}", exc_info=True)
            error_msg = f"Error retrieving documents: {str(e)}"
            if len(error_msg) > 100:
                error_msg = error_msg[:97] + "..."
            await self.send_message(chat_id, f"⚠️ {error_msg}", disable_web_page_preview=True)
    
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

            # Always fetch fresh campaigns when command is triggered
            await self.send_message(chat_id, "🔄 Fetching latest campaigns...", disable_web_page_preview=True)

            # Load previous campaigns for comparison
            previous_campaigns = self.data_manager.load_previous_campaigns()
            logger.info(f"Loaded {len(previous_campaigns)} previous campaigns for comparison")

            try:
                # Fetch new campaigns directly from Mintos
                new_campaigns = self.mintos_client.get_campaigns()
                if not new_campaigns:
                    await self.send_message(chat_id, "⚠️ No campaigns available right now.", disable_web_page_preview=True)
                    return

                # Save for future use
                self.data_manager.save_campaigns(new_campaigns)
                logger.info(f"Fetched and saved {len(new_campaigns)} campaigns")
                
                # Find new or updated campaigns
                added_campaigns = self.data_manager.compare_campaigns(new_campaigns, previous_campaigns)
                
                # Notify all users about new campaigns, not just the requester
                if added_campaigns:
                    logger.info(f"Found {len(added_campaigns)} new or updated campaigns to broadcast to all users")
                    
                    # Filter out Special Promotion (type 4) campaigns and unsent campaigns
                    unsent_campaigns = [
                        campaign for campaign in added_campaigns 
                        if not self.data_manager.is_campaign_sent(campaign) and campaign.get('type') != 4
                    ]
                    
                    if unsent_campaigns:
                        users = self.user_manager.get_all_users()
                        logger.info(f"Broadcasting {len(unsent_campaigns)} new campaigns to {len(users)} users")
                        
                        # Send notification to the requesting user first
                        await self.send_message(
                            chat_id, 
                            f"🔔 <b>Found {len(unsent_campaigns)} new campaign(s)!</b>\n"
                            f"Broadcasting to all {len(users)} subscribers...",
                            disable_web_page_preview=True
                        )
                        
                        # Send to all users
                        for i, campaign in enumerate(unsent_campaigns, 1):
                            message = self.format_campaign_message(campaign)
                            for user_id in users:
                                try:
                                    await self.send_message(user_id, message, disable_web_page_preview=True)
                                    # Mark as sent to prevent duplicate notifications
                                    self.data_manager.save_sent_campaign(campaign)
                                    logger.info(f"Successfully sent campaign {i}/{len(unsent_campaigns)} to user {user_id}")
                                except Exception as e:
                                    logger.error(f"Failed to send campaign to user {user_id}: {e}")
                                    
                            # Add a delay between campaigns
                            await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error fetching campaigns: {e}")
                # If fetching fails, try to use cached data as fallback
                new_campaigns = self.data_manager.load_previous_campaigns()
                if not new_campaigns:
                    await self.send_message(chat_id, "⚠️ Error fetching campaigns and no cache available. Please try again later.", disable_web_page_preview=True)
                    return
                logger.info(f"Using cached campaigns data as fallback after fetch error")
                await self.send_message(chat_id, "⚠️ Could not fetch new campaigns, using cached data instead.", disable_web_page_preview=True)

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
        """Trigger an update check for today's updates or for a specified date"""
        if not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        try:
            # Check if a date was specified
            date_text = "today's"
            if context and hasattr(context, 'args') and context.args:
                date_text = f"updates for {context.args[0]}"
            
            await self.send_message(chat_id, f"🔄 Checking {date_text}...", disable_web_page_preview=True)
            await self.today_command(update, context)
        except Exception as e:
            logger.error(f"Error in trigger_today command: {e}")
            await self.send_message(chat_id, "⚠️ Error checking updates", disable_web_page_preview=True)

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
        """Handle /trigger_today command with user selection and optional date parameter"""
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

            # Check for arguments
            args = context.args if context and hasattr(context, 'args') else None
            
            # Default to today's date
            target_date = time.strftime("%Y-%m-%d")
            has_date_param = False
            
            # Process arguments
            if args:
                # If last argument looks like a date, extract it
                if len(args) >= 2 and len(args[-1]) == 10 and args[-1][4] == '-' and args[-1][7] == '-':
                    try:
                        # Validate it's a proper date
                        datetime.strptime(args[-1], "%Y-%m-%d")
                        target_date = args[-1]
                        has_date_param = True
                        logger.info(f"Using specified date: {target_date}")
                        # Remove date from args for further processing
                        remaining_args = args[:-1]
                    except ValueError:
                        # Not a valid date, treat all args as target specification
                        remaining_args = args
                else:
                    # No date parameter
                    remaining_args = args
                    
                # Check if we have a target channel in the arguments
                if remaining_args:
                    target_channel = remaining_args[0]
                    
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
                    await self._send_today_updates_to_channel(chat_id, target_channel, target_date)
                    return
            
            # No target channel specified, display user selection interface
            # Get all registered users
            users = self.user_manager.get_all_users()
            
            # Create buttons for registered users
            keyboard = []
            for i, user_id in enumerate(users, 1):
                username = self.user_manager.get_user_info(user_id) or "Unknown"
                button_text = f"{i}. {username} ({user_id})"
                # Include the date in the callback data if specified
                callback_data = f"trigger_today_{user_id}_{target_date}" if has_date_param else f"trigger_today_{user_id}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            # Add button for manual ID entry
            callback_data = "trigger_today_custom" if not has_date_param else f"trigger_today_custom_{target_date}"
            keyboard.append([InlineKeyboardButton("✏️ Enter custom channel ID", callback_data=callback_data)])
            
            # Create appropriate title based on whether we're showing today or a specific date
            title = "today's" if not has_date_param else f"updates for {target_date}"
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            usage_example = "You can also use:\n" \
                           f"<code>/trigger_today [number] {target_date if has_date_param else 'YYYY-MM-DD'}</code>\n" \
                           f"<code>/trigger_today [channel_id] {target_date if has_date_param else 'YYYY-MM-DD'}</code>"
            
            await self.send_message(
                chat_id,
                f"📲 <b>Select a channel to send {title} to:</b>\n\n{usage_example}",
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
            
    async def _send_today_updates_to_channel(self, admin_chat_id: Union[int, str], target_channel: str, target_date: Optional[str] = None) -> None:
        """
        Send updates for a specific date to the specified channel
        
        Args:
            admin_chat_id: ID of the admin who triggered the command
            target_channel: Channel to send updates to
            target_date: Date in YYYY-MM-DD format (defaults to today)
        """
        try:
            # Use the provided target_date or default to today
            date_to_check = target_date if target_date else time.strftime("%Y-%m-%d")
            
            # Create appropriate message based on whether we're checking today or a specific date
            is_today = date_to_check == time.strftime("%Y-%m-%d")
            date_desc = "today" if is_today else f"date {date_to_check}"
            
            # Inform user that command is being processed
            await self.send_message(admin_chat_id, f"🔄 Processing updates for {date_desc}...", disable_web_page_preview=True)
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

            # Retrieve updates for the target date
            logger.info(f"Getting updates for {date_desc}")
            updates = self.data_manager.load_previous_updates()
            date_updates = []

            # Process updates
            for company_update in updates:
                if "items" in company_update:
                    lender_id = company_update.get('lender_id')
                    company_name = self.data_manager.get_company_name(lender_id)

                    for year_data in company_update["items"]:
                        for item in year_data.get("items", []):
                            if item.get('date') == date_to_check:
                                update_with_company = {
                                    "lender_id": lender_id,
                                    "company_name": company_name,
                                    **year_data,
                                    **item
                                }
                                date_updates.append(update_with_company)

            logger.info(f"Found {len(date_updates)} updates for {date_desc}")

            # Handle no updates case - only notify the command sender, not the channel
            if not date_updates:
                await self.send_message(admin_chat_id, f"✅ No updates found for {date_desc}", disable_web_page_preview=True)
                return

            # Send updates to the channel
            successful_sends = 0

            # Only send header if there are updates to show
            if date_updates:
                header_text = f"📊 Updates for {date_desc}:"
                if not is_today:
                    header_text = f"📊 Updates for {date_to_check}:"
                    
                await self.send_message(
                    chat_id=resolved_channel,
                    text=header_text,
                    disable_web_page_preview=True
                )

                # Send updates using proper delay mechanism
                for update_item in date_updates:
                    try:
                        message = self.format_update_message(update_item)
                        await self.send_message(
                            chat_id=resolved_channel,
                            text=message,
                            disable_web_page_preview=True
                        )
                        successful_sends += 1
                    except Exception as e:
                        logger.error(f"Error sending update: {e}")
                        # Continue with next message even if one fails

            # Get channel name for the status message
            channel_name = target_channel
            try:
                channel_info = await self.application.bot.get_chat(resolved_channel)
                if channel_info.title:
                    channel_name = channel_info.title
            except:
                pass  # If we can't get the name, use the ID

            # Send status only to the user who triggered the command
            status = f"✅ Successfully sent {successful_sends} of {len(date_updates)} updates for {date_desc} to {channel_name}"
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
            "/today [YYYY-MM-DD] - View updates for today or a specific date\n"
            "/campaigns - View current Mintos campaigns\n"
            "/trigger_today [@channel] [YYYY-MM-DD] - Send updates to a channel\n"
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

    async def check_rss_updates(self) -> None:
        """Check for new RSS items and send notifications to users based on their feed preferences"""
        try:
            # Get new RSS items from all feeds
            new_items = await self.rss_reader.check_and_get_new_items()
            if not new_items:
                logger.info("No new RSS items found")
                return

            logger.info(f"Found {len(new_items)} new RSS items")

            # Group items by feed source and send to appropriate users
            items_by_feed = {}
            for item in new_items:
                feed_source = item.feed_source
                if feed_source not in items_by_feed:
                    items_by_feed[feed_source] = []
                items_by_feed[feed_source].append(item)

            # Send notifications for each feed
            for feed_source, items in items_by_feed.items():
                # Get users subscribed to this specific feed
                feed_users = self.user_manager.get_users_with_feed_enabled(feed_source)
                
                if not feed_users:
                    logger.info(f"No users subscribed to {feed_source} feed")
                    continue
                
                logger.info(f"Sending {len(items)} {feed_source} items to {len(feed_users)} users")
                
                # Send each item to subscribed users
                for item in items:
                    message = self.rss_reader.format_rss_message(item)
                    
                    for chat_id in feed_users:
                        try:
                            await self.send_message(
                                chat_id,
                                message,
                                parse_mode='HTML',
                                disable_web_page_preview=True
                            )
                            await asyncio.sleep(0.1)  # Rate limiting
                        except Exception as e:
                            logger.error(f"Error sending {feed_source} RSS notification to {chat_id}: {e}")
                            if "bot was blocked" in str(e).lower():
                                self.user_manager.remove_user(chat_id)

                    # Mark item as sent after sending to all subscribed users
                    self.rss_reader.mark_item_as_sent(item)

        except Exception as e:
            logger.error(f"Error checking RSS updates: {e}", exc_info=True)

    async def should_check_rss(self) -> bool:
        """Check if RSS updates should be checked based on current time"""
        now = datetime.now()
        
        # Only check on weekdays (Monday=0, Sunday=6)
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        # Only check between 6 AM and 10 PM
        if not (6 <= now.hour <= 22):
            return False
        
        return True

    async def scheduled_rss_updates(self) -> None:
        """Handle RSS checks every 15 minutes during specified hours"""
        while True:
            try:
                if await self.should_check_rss():
                    logger.info("Running scheduled RSS check")
                    await self.check_rss_updates()
                    logger.info("RSS check completed")
                else:
                    logger.debug(f"Skipping RSS check - outside scheduled hours (weekday: {datetime.now().weekday()}, hour: {datetime.now().hour})")
                
                # Wait 15 minutes before next check
                await asyncio.sleep(15 * 60)
                
            except Exception as e:
                logger.error(f"RSS check failed: {e}", exc_info=True)
                # Wait 5 minutes on error before retrying
                await asyncio.sleep(5 * 60)

    async def scheduled_campaign_updates(self) -> None:
        """Handle campaign checks every 10 minutes on weekdays between 6 AM and 8 PM with 4-hour delay for non-admin users"""
        while True:
            try:
                await asyncio.sleep(10 * 60)  # Check every 10 minutes
                
                # Check if we should run the campaign check (weekdays only, 6 AM to 8 PM)
                now = datetime.now()
                weekday = now.weekday()  # 0=Monday, 6=Sunday
                hour = now.hour
                
                if weekday < 5 and 6 <= hour < 20:  # Monday-Friday, 6 AM to 8 PM
                    logger.info("Running scheduled campaign check")
                    await self.check_campaigns()
                    
                    # Also check for ready pending campaigns
                    await self.process_pending_campaigns()
                else:
                    logger.debug(f"Skipping campaign check - outside scheduled hours (weekday: {weekday}, hour: {hour})")
                
            except asyncio.CancelledError:
                logger.info("Scheduled campaign updates cancelled")
                break
            except Exception as e:
                logger.error(f"Campaign check failed: {e}", exc_info=True)
                # Wait 2 minutes on error before retrying
                await asyncio.sleep(2 * 60)

    async def process_pending_campaigns(self) -> None:
        """Process campaigns that are ready to be sent after the delay"""
        try:
            ready_campaigns = self.data_manager.get_ready_pending_campaigns(delay_hours=4)
            
            if not ready_campaigns:
                return
                
            logger.info(f"Processing {len(ready_campaigns)} ready pending campaigns")
            
            # Get all non-admin users
            all_users = self.user_manager.get_all_users()
            admin_id = 114691530  # Hardcoded admin ID
            non_admin_users = [user_id for user_id in all_users if user_id != admin_id]
            
            for pending_item in ready_campaigns:
                campaign = pending_item['campaign']
                campaign_id = campaign.get('id')
                
                if not campaign_id:
                    continue
                    
                # Send to non-admin users
                message = self.format_campaign_message(campaign)
                
                for user_id in non_admin_users:
                    # Check if user has campaign notifications enabled
                    if self.user_manager.get_notification_preference(user_id, 'campaigns'):
                        try:
                            await self.send_message(user_id, message, disable_web_page_preview=True)
                            logger.info(f"Sent delayed campaign {campaign_id} to user {user_id}")
                        except Exception as e:
                            logger.error(f"Failed to send delayed campaign to user {user_id}: {e}")
                    else:
                        logger.debug(f"Skipping campaign for user {user_id} - notifications disabled")
                
                # Remove from pending list and mark as sent
                self.data_manager.remove_pending_campaign(campaign_id)
                self.data_manager.save_sent_campaign(campaign)
                
        except Exception as e:
            logger.error(f"Error processing pending campaigns: {e}", exc_info=True)

    async def rss_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show RSS feed subscription options"""
        if not update.effective_user or not update.effective_chat or not update.message:
            return
            
        chat_id = str(update.effective_chat.id)
        user_prefs = self.user_manager.get_user_feed_preferences(chat_id)
        
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete command message: {e}")
        
        # Get current feed statuses
        nasdaq_enabled = user_prefs.get('nasdaq', False)
        mintos_enabled = user_prefs.get('mintos', False)
        ffnews_enabled = user_prefs.get('ffnews', False)
        
        # Build keyboard with individual feed toggles
        keyboard = [
            [InlineKeyboardButton(
                f"{'✅' if nasdaq_enabled else '⭕'} NASDAQ Baltic (filtered)",
                callback_data=f"feed_toggle_nasdaq_{chat_id}"
            )],
            [InlineKeyboardButton(
                f"{'✅' if mintos_enabled else '⭕'} Mintos News (all articles)",
                callback_data=f"feed_toggle_mintos_{chat_id}"
            )],
            [InlineKeyboardButton(
                f"{'✅' if ffnews_enabled else '⭕'} FFNews (filtered)",
                callback_data=f"feed_toggle_ffnews_{chat_id}"
            )],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Count enabled feeds
        enabled_count = sum([nasdaq_enabled, mintos_enabled, ffnews_enabled])
        
        await self.send_message(
            chat_id,
            f"📰 <b>RSS Feed Subscriptions</b>\n\n"
            f"You have <b>{enabled_count}</b> feed(s) enabled\n\n"
            f"<b>Available feeds:</b>\n"
            f"• <b>NASDAQ Baltic</b> - Filtered news about Mintos, DelfinGroup, Grenardi, etc.\n"
            f"• <b>Mintos News</b> - All articles from Mintos blog\n"
            f"• <b>FFNews</b> - Financial news filtered by keywords\n\n"
            f"Click on any feed to toggle notifications:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


        
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
            [InlineKeyboardButton("🔄 Refresh Updates", callback_data="admin_refresh_updates")],
            [InlineKeyboardButton("📄 Refresh Documents", callback_data="admin_refresh_documents")],
            [InlineKeyboardButton("📤 Send Updates", callback_data="admin_trigger_today")],
            [InlineKeyboardButton("📰 Send RSS Items", callback_data="admin_send_rss")],
            [InlineKeyboardButton("❌ Exit", callback_data="admin_exit")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(
            chat_id,
            "🔐 <b>Admin Control Panel</b>\n\n"
            "Please select an admin function:\n\n"
            "<i>You can also use /refresh command directly to force an immediate update check.</i>",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            parse_mode='HTML'
        )

    async def _show_rss_items_selection(self, query) -> None:
        """Show available RSS items for selection"""
        try:
            # Fetch current RSS items
            rss_items = await self.rss_reader.fetch_rss_feed()
            
            if not rss_items:
                await query.edit_message_text(
                    "📰 <b>No RSS Items Available</b>\n\n"
                    "No RSS items found in the current feed.",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                return
            
            # Show first few items with selection buttons
            items_per_page = 5
            total_items = len(rss_items)
            
            message_text = f"📰 <b>Select RSS Items to Send</b>\n\n"
            message_text += f"Found {total_items} RSS items. Select items to send:\n\n"
            
            keyboard = []
            
            # Show first 5 items
            for i, item in enumerate(rss_items[:items_per_page]):
                # Truncate title for button display
                truncated_title = item.title[:40] + "..." if len(item.title) > 40 else item.title
                button_text = f"📄 {truncated_title}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"rss_item_select_{i}")])
            
            # Add navigation and control buttons
            nav_buttons = []
            if total_items > items_per_page:
                nav_buttons.append(InlineKeyboardButton("Show More", callback_data="rss_show_more_0"))
            
            keyboard.append([InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error showing RSS items selection: {e}")
            await query.edit_message_text(
                "⚠️ Error loading RSS items. Please try again.",
                disable_web_page_preview=True
            )

    async def _handle_rss_item_selection(self, query) -> None:
        """Handle RSS item selection and show send options"""
        try:
            item_index = int(query.data.split("_")[-1])
            
            # Fetch RSS items again to get the selected item
            rss_items = await self.rss_reader.fetch_rss_feed()
            
            if item_index >= len(rss_items):
                await query.edit_message_text(
                    "⚠️ Invalid item selection. Please try again.",
                    disable_web_page_preview=True
                )
                return
            
            selected_item = rss_items[item_index]
            
            # Show the selected item and ask where to send it
            message_text = f"📰 <b>Selected RSS Item</b>\n\n"
            message_text += f"<b>Title:</b> {html.escape(selected_item.title)}\n"
            message_text += f"<b>Issuer:</b> {html.escape(selected_item.issuer)}\n"
            message_text += f"<b>Date:</b> {selected_item.pub_date}\n\n"
            message_text += "Where would you like to send this item?\n"
            
            # Get list of users for sending options
            users = self.user_manager.get_all_users()
            
            keyboard = []
            
            # Add option to send to all users
            keyboard.append([InlineKeyboardButton("📢 Send to All Users", callback_data=f"send_rss_to_all_{item_index}")])
            
            # Add individual user options (show first few)
            user_count = 0
            for user_id in users:
                if user_count >= 3:  # Limit to first 3 users to avoid too many buttons
                    break
                username = self.user_manager.get_user_info(user_id)
                display_name = f"@{username}" if username else f"User {user_id}"
                keyboard.append([InlineKeyboardButton(f"👤 {display_name}", callback_data=f"send_rss_to_user_{user_id}_{item_index}")])
                user_count += 1
            
            # Add predefined channel option
            keyboard.append([InlineKeyboardButton("📺 Mintos Unofficial News Channel", callback_data=f"send_rss_to_channel_-1002373856504_{item_index}")])
            
            # Add option for custom channel
            keyboard.append([InlineKeyboardButton("📺 Send to Custom Channel", callback_data=f"send_rss_to_custom_{item_index}")])
            
            # Add back button
            keyboard.append([InlineKeyboardButton("« Back to RSS Items", callback_data="admin_send_rss")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error handling RSS item selection: {e}")
            await query.edit_message_text(
                "⚠️ Error processing selection. Please try again.",
                disable_web_page_preview=True
            )

    async def _handle_send_rss_items(self, query) -> None:
        """Handle sending RSS items to selected destination"""
        try:
            callback_parts = query.data.split("_")
            send_type = callback_parts[3]  # all, user, or custom
            
            if send_type == "all":
                item_index = int(callback_parts[4])
                await self._send_rss_to_all_users(query, item_index)
            elif send_type == "user":
                user_id = callback_parts[4]
                item_index = int(callback_parts[5])
                await self._send_rss_to_user(query, user_id, item_index)
            elif send_type == "channel":
                channel_id = callback_parts[4]
                item_index = int(callback_parts[5])
                await self._send_rss_to_predefined_channel(query, channel_id, item_index)
            elif send_type == "custom":
                item_index = int(callback_parts[4])
                await self._send_rss_to_custom_channel(query, item_index)
            
        except Exception as e:
            logger.error(f"Error handling send RSS items: {e}")
            await query.edit_message_text(
                "⚠️ Error sending RSS items. Please try again.",
                disable_web_page_preview=True
            )

    async def _send_rss_to_all_users(self, query, item_index: int) -> None:
        """Send RSS item to all users"""
        try:
            # Fetch RSS items
            rss_items = await self.rss_reader.fetch_rss_feed()
            
            if item_index >= len(rss_items):
                await query.edit_message_text(
                    "⚠️ Invalid item selection.",
                    disable_web_page_preview=True
                )
                return
            
            selected_item = rss_items[item_index]
            
            await query.edit_message_text(
                "🔄 Sending RSS item to all users...",
                disable_web_page_preview=True
            )
            
            # Get all users
            users = self.user_manager.get_all_users()
            message = self.rss_reader.format_rss_message(selected_item)
            
            successful_sends = 0
            for user_id in users:
                try:
                    await self.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                    successful_sends += 1
                    await asyncio.sleep(0.1)  # Rate limiting
                except Exception as e:
                    logger.error(f"Error sending RSS to user {user_id}: {e}")
                    if "bot was blocked" in str(e).lower():
                        self.user_manager.remove_user(user_id)
            
            # Add back button
            keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ <b>RSS Item Sent Successfully</b>\n\n"
                f"Sent to {successful_sends} users.\n\n"
                f"<b>Item:</b> {html.escape(selected_item.title)}",
                reply_markup=reply_markup,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error sending RSS to all users: {e}")
            await query.edit_message_text(
                "⚠️ Error sending RSS item to users.",
                disable_web_page_preview=True
            )

    async def _send_rss_to_user(self, query, user_id: str, item_index: int) -> None:
        """Send RSS item to specific user"""
        try:
            # Fetch RSS items
            rss_items = await self.rss_reader.fetch_rss_feed()
            
            if item_index >= len(rss_items):
                await query.edit_message_text(
                    "⚠️ Invalid item selection.",
                    disable_web_page_preview=True
                )
                return
            
            selected_item = rss_items[item_index]
            
            await query.edit_message_text(
                f"🔄 Sending RSS item to user {user_id}...",
                disable_web_page_preview=True
            )
            
            message = self.rss_reader.format_rss_message(selected_item)
            
            try:
                await self.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                
                # Add back button
                keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ <b>RSS Item Sent Successfully</b>\n\n"
                    f"Sent to user {user_id}.\n\n"
                    f"<b>Item:</b> {html.escape(selected_item.title)}",
                    reply_markup=reply_markup,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                
            except Exception as e:
                logger.error(f"Error sending RSS to user {user_id}: {e}")
                await query.edit_message_text(
                    f"⚠️ Error sending RSS item to user {user_id}: {str(e)}",
                    disable_web_page_preview=True
                )
                
        except Exception as e:
            logger.error(f"Error in send RSS to user: {e}")
            await query.edit_message_text(
                "⚠️ Error sending RSS item.",
                disable_web_page_preview=True
            )

    async def _send_rss_to_predefined_channel(self, query, channel_id: str, item_index: int) -> None:
        """Send RSS item to predefined channel"""
        try:
            # Fetch RSS items
            rss_items = await self.rss_reader.fetch_rss_feed()
            
            if item_index >= len(rss_items):
                await query.edit_message_text(
                    "⚠️ Invalid item selection.",
                    disable_web_page_preview=True
                )
                return
            
            selected_item = rss_items[item_index]
            
            await query.edit_message_text(
                f"🔄 Sending RSS item to Mintos Unofficial News Channel...",
                disable_web_page_preview=True
            )
            
            message = self.rss_reader.format_rss_message(selected_item)
            
            try:
                await self.send_message(
                    chat_id=channel_id,
                    text=message,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                
                # Add back button
                keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ <b>RSS Item Sent Successfully</b>\n\n"
                    f"Sent to Mintos Unofficial News Channel.\n\n"
                    f"<b>Item:</b> {html.escape(selected_item.title)}",
                    reply_markup=reply_markup,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                
            except Exception as e:
                logger.error(f"Error sending RSS to channel {channel_id}: {e}")
                await query.edit_message_text(
                    f"⚠️ Error sending RSS item to channel: {str(e)}",
                    disable_web_page_preview=True
                )
                
        except Exception as e:
            logger.error(f"Error in send RSS to predefined channel: {e}")
            await query.edit_message_text(
                "⚠️ Error sending RSS item.",
                disable_web_page_preview=True
            )

    async def _send_rss_to_custom_channel(self, query, item_index: int) -> None:
        """Send RSS item to custom channel"""
        try:
            # Fetch RSS items
            rss_items = await self.rss_reader.fetch_rss_feed()
            
            if item_index >= len(rss_items):
                await query.edit_message_text(
                    "⚠️ Invalid item selection.",
                    disable_web_page_preview=True
                )
                return
            
            selected_item = rss_items[item_index]
            
            await query.edit_message_text(
                f"📝 <b>Send RSS Item to Custom Channel</b>\n\n"
                f"<b>Selected Item:</b> {html.escape(selected_item.title)}\n\n"
                f"Please enter the channel ID to send this RSS item to.\n\n"
                f"Format: -100xxxxxxxxxx\n"
                f"Example: -1001234567890\n\n"
                f"Reply directly to this message with the channel ID.",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
            # Store the item index for later use when user responds
            # We'll need to implement a message handler for this
            
        except Exception as e:
            logger.error(f"Error in send RSS to custom channel: {e}")
            await query.edit_message_text(
                "⚠️ Error processing request.",
                disable_web_page_preview=True
            )

if __name__ == "__main__":
    bot = MintosBot()
    asyncio.run(bot.run())