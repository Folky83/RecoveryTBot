from __future__ import annotations
import asyncio
from datetime import datetime
import time
from typing import Optional, List, Dict, Any, Union, cast
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError, Conflict
import math

from .logger import setup_logger
from .config import TELEGRAM_TOKEN
from .data_manager import DataManager
from .mintos_client import MintosClient
from .user_manager import UserManager

logger = setup_logger(__name__)

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
                await self.cleanup()
                await asyncio.sleep(2)

                self.application = Application.builder().token(TELEGRAM_TOKEN).build()
                await self.application.bot.delete_webhook(drop_pending_updates=True)
                await self.application.bot.get_updates(offset=-1)

                self._register_handlers()
                self._initialized = True
                logger.info("Bot initialized with handlers")
                return True
            except Exception as e:
                logger.error(f"Initialization error: {e}", exc_info=True)
                return False

    def _register_handlers(self) -> None:
        """Register command and callback handlers"""
        if not self.application:
            raise RuntimeError("Application not initialized")

        handlers = [
            CommandHandler("start", self.start_command),
            CommandHandler("company", self.company_command),
            CommandHandler("today", self.today_command),
            CommandHandler("refresh", self.refresh_command),
            CallbackQueryHandler(self.handle_callback)
        ]
        for handler in handlers:
            self.application.add_handler(handler)
        self.application.add_error_handler(self._error_handler)

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
                await self.cleanup()
                await asyncio.sleep(2)

                if not await self.initialize():
                    raise RuntimeError("Bot initialization failed")

                await self.application.initialize()
                await self.application.start()

                self._polling_task = asyncio.create_task(
                    self.application.updater.start_polling(
                        drop_pending_updates=True,
                        allowed_updates=["message", "callback_query"]
                    )
                )
                self._update_task = asyncio.create_task(self.scheduled_updates())

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
            # Delete the command message
            await update.message.delete()
            
            user = update.effective_user
            logger.info(f"Start command from {user.username} (chat_id: {chat_id})")

            self.user_manager.add_user(str(chat_id))
            welcome_message = self._create_welcome_message()
            await self.send_message(chat_id, welcome_message)
            logger.info(f"User {user.username} registered")

        except Exception as e:
            logger.error(f"Start command error: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error processing command")

    def _create_welcome_message(self) -> str:
        """Create formatted welcome message"""
        return (
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

    async def company_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /company command - display company selection menu with live data"""
        try:
            if not update.message:
                return
                
            # Delete the command message
            await update.message.delete()
            
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

    async def send_message(self, chat_id: Union[int, str], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
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

    def format_update_message(self, update: Dict[str, Any]) -> str:
        """Format update message with rich information from Mintos API"""
        logger.debug(f"Formatting update message for: {update.get('company_name')}")
        company_name = update.get('company_name', 'Unknown Company')
        message = f"🏢 <b>{company_name}</b>\n"

        if 'date' in update:
            message += f"📅 Date: {update['date']}\n"
            if 'year' in update:
                message += f"Year: {update['year']}\n"

        if 'status' in update:
            status = update['status'].replace('_', ' ').title()
            message += f"📊 Status: {status}\n"
            if update.get('substatus'):
                substatus = update['substatus'].replace('_', ' ').title()
                message += f"Sub-status: {substatus}\n"

        if any(key in update for key in ['recoveredAmount', 'remainingAmount', 'expectedRecoveryTo', 'expectedRecoveryFrom']):
            message += "\n💰 Recovery Information:\n"

            if update.get('recoveredAmount'):
                amount = round(float(update['recoveredAmount']))
                message += f"• Recovered: €{amount:,}\n"
            if update.get('remainingAmount'):
                amount = round(float(update['remainingAmount']))
                message += f"• Remaining: €{amount:,}\n"

            if update.get('expectedRecoveryFrom') and update.get('expectedRecoveryTo'):
                from_percentage = round(float(update['expectedRecoveryFrom']))
                to_percentage = round(float(update['expectedRecoveryTo']))
                message += f"• Expected Recovery: {from_percentage}% - {to_percentage}%\n"
            elif update.get('expectedRecoveryTo'):
                percentage = round(float(update['expectedRecoveryTo']))
                message += f"• Expected Recovery: Up to {percentage}%\n"

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

        if 'lender_id' in update:
            message += f"\n🔗 <a href='https://www.mintos.com/en/loan-companies/{update['lender_id']}'>View on Mintos</a>"

        return message.strip()

    async def check_updates(self) -> None:
        try:
            logger.info("Starting update check...")
            previous_updates = self.data_manager.load_previous_updates()
            lender_ids = [int(id) for id in self.data_manager.company_names.keys()]
            new_updates = self.mintos_client.fetch_all_updates(lender_ids)
            added_updates = self.data_manager.compare_updates(new_updates, previous_updates)

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
        try:
            if not update.message:
                return
                
            # Delete the command message
            await update.message.delete()
            
            chat_id = update.effective_chat.id
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

    async def should_check_updates(self) -> bool:
        """Determine if updates should be checked based on current time"""
        now = datetime.now()

        if now.weekday() >= 5:
            logger.debug(f"Skipping update check - weekend day ({now.strftime('%A')})")
            return False

        should_check = now.hour in [16, 17, 18]
        if not should_check:
            logger.debug(f"Skipping update check - outside scheduled hours (current hour: {now.hour})")
        else:
            logger.info(f"Update check scheduled for current hour ({now.hour}:00)")
        return should_check

    async def refresh_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            if not update.message:
                return
                
            # Delete the command message
            await update.message.delete()
            
            chat_id = update.effective_chat.id
            cache_age = self.data_manager.get_cache_age()

            if cache_age < 900:
                minutes_left = int((900 - cache_age) / 60)
                await self.send_message(chat_id, f"⏳ Please wait {minutes_left} minutes before refreshing again.")
                return

            await self.send_message(chat_id, "🔄 Starting manual refresh...")
            await self.check_updates()
            await self.send_message(chat_id, "✅ Manual refresh completed!")

        except Exception as e:
            logger.error(f"Error in refresh_command: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error during manual refresh. Please try again.")


if __name__ == "__main__":
    bot = MintosBot()
    asyncio.run(bot.run())