import asyncio
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError
import time
from .logger import setup_logger
from .config import TELEGRAM_TOKEN, UPDATE_INTERVAL
from .data_manager import DataManager
from .mintos_client import MintosClient
from .user_manager import UserManager

logger = setup_logger(__name__)

class MintosBot:
    def __init__(self):
        logger.info("Initializing Mintos Bot...")
        if not TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

        self.application = Application.builder().token(TELEGRAM_TOKEN).build()
        self.data_manager = DataManager()
        self.mintos_client = MintosClient()
        self.user_manager = UserManager()

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("company", self.company_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        logger.info("Bot initialized and handlers registered")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command - register new users"""
        try:
            chat_id = update.effective_chat.id
            user = update.effective_user
            logger.info(f"Received /start command from user {user.username} (chat_id: {chat_id})")

            self.user_manager.add_user(str(chat_id))
            welcome_message = (
                "🚀 Welcome to Mintos Update Bot!\n\n"
                "You'll receive updates about lending companies automatically.\n"
                "Use /company to check specific company updates.\n"
                "Stay tuned for important updates!"
            )
            await self.send_message(chat_id, welcome_message)
            logger.info(f"User {user.username} successfully registered")

        except Exception as e:
            logger.error(f"Error in start_command: {e}", exc_info=True)
            await self.send_message(chat_id, "⚠️ Error processing your command. Please try again.")
            raise

    async def company_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /company command - display company selection menu"""
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
                    [InlineKeyboardButton("All Updates", callback_data=f"all_{company_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(buttons)
                await query.edit_message_text(
                    f"Select update type for {company_name}:",
                    reply_markup=reply_markup
                )

            elif query.data.startswith(("latest_", "all_")):
                update_type, company_id = query.data.split("_")
                company_id = int(company_id)
                company_name = self.data_manager.get_company_name(company_id)

                updates = self.data_manager.load_previous_updates()
                company_updates = next((item for item in updates if item["lender_id"] == company_id), None)

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
                    for year_data in company_updates.get("items", []):
                        for update_item in year_data.get("items", []):
                            update_with_company = {
                                "lender_id": company_id,
                                "company_name": company_name,
                                **update_item
                            }
                            messages.append(self.format_update_message(update_with_company))

                    # Send updates in chunks to avoid message length limits
                    for message in messages[:5]:  # Limit to 5 most recent updates
                        await self.send_message(query.message.chat_id, message)

                    if len(messages) > 5:
                        await self.send_message(
                            query.message.chat_id,
                            f"Showing 5 most recent updates out of {len(messages)} total updates."
                        )

        except Exception as e:
            logger.error(f"Error in handle_callback: {e}", exc_info=True)
            await query.edit_message_text("⚠️ Error processing your request. Please try again.")

    async def send_message(self, chat_id, text):
        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML'
            )
            logger.debug(f"Message sent successfully to {chat_id}")
        except TelegramError as e:
            logger.error(f"Error sending message to {chat_id}: {e}", exc_info=True)
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

        # Add recovery information with rounded Euro amounts
        if any(key in update for key in ['recoveredAmount', 'remainingAmount', 'expectedRecoveryTo', 'expectedRecoveryFrom']):
            message += "\n💰 Recovery Information:\n"
            if update.get('recoveredAmount'):
                amount = round(float(update['recoveredAmount']))
                message += f"• Recovered: €{amount:,}\n"
            if update.get('remainingAmount'):
                amount = round(float(update['remainingAmount']))
                message += f"• Remaining: €{amount:,}\n"
            if update.get('expectedRecoveryFrom') and update.get('expectedRecoveryTo'):
                from_amount = round(float(update['expectedRecoveryFrom']))
                to_amount = round(float(update['expectedRecoveryTo']))
                message += f"• Expected Recovery: €{from_amount:,} - €{to_amount:,}\n"
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

        # Add description
        if 'description' in update:
            # Clean up HTML tags and entities
            description = update['description']
            description = description.replace('\u003C', '<').replace('\u003E', '>')  # Handle escaped HTML
            description = description.replace('&#39;', "'")  # Handle apostrophes
            description = description.replace('&euro;', '€')  # Handle euro symbol
            description = description.replace('<p>', '').replace('</p>', '\n').strip()
            message += f"\n📝 Details:\n{description}\n"

        # Add Mintos link with company ID if available
        if 'lender_id' in update:
            message += f"\n🔗 <a href='https://www.mintos.com/en/loan-companies/{update['lender_id']}'>View on Mintos</a>"

        logger.debug("Formatted message created")
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
        """Start the bot in polling mode"""
        logger.info("Starting bot polling")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Bot polling started successfully")

    async def run(self):
        """Run the bot with both polling and periodic updates"""
        logger.info("Starting Mintos Update Bot")
        try:
            # Start polling in the background
            polling_task = asyncio.create_task(self.start_polling())

            # Start periodic updates
            while True:
                await self.check_updates()
                await asyncio.sleep(UPDATE_INTERVAL)

        except Exception as e:
            logger.error(f"Error in main run loop: {e}", exc_info=True)
            raise

if __name__ == "__main__":
    bot = MintosBot()
    asyncio.run(bot.run())