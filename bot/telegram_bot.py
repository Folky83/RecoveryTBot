import asyncio
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
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
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()
        self.data_manager = DataManager()
        self.mintos_client = MintosClient()
        self.user_manager = UserManager()

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start_command))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command - register new users"""
        chat_id = update.effective_chat.id
        self.user_manager.add_user(str(chat_id))
        await self.send_message(
            chat_id,
            "🚀 Welcome to Mintos Update Bot!\nYou'll receive updates about lending companies automatically."
        )

    async def send_message(self, chat_id, text):
        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML'
            )
            logger.info(f"Message sent successfully to {chat_id}")
        except TelegramError as e:
            logger.error(f"Error sending message to {chat_id}: {e}")

    def format_update_message(self, update):
        company_name = update.get('company_name', 'Unknown Company')
        message = f"🔔 <b>New Update for {company_name}</b>\n\n"

        if 'lastUpdate' in update:
            message += f"Last Update: {update['lastUpdate']}\n"
        if 'status' in update:
            message += f"Status: {update['status']}\n"
        if 'description' in update:
            message += f"\nDescription:\n{update['description']}\n"

        return message

    async def check_updates(self):
        try:
            # Get previous updates
            previous_updates = self.data_manager.load_previous_updates()

            # Fetch new updates - update range to match actual lender IDs
            lender_ids = [int(id) for id in self.data_manager.company_names.keys()]
            new_updates = self.mintos_client.fetch_all_updates(lender_ids)

            # Compare and get new updates
            added_updates = self.data_manager.compare_updates(new_updates, previous_updates)

            # Send notifications to all users
            if added_updates:
                users = self.user_manager.get_all_users()
                for update in added_updates:
                    message = self.format_update_message(update)
                    for user_id in users:
                        await self.send_message(user_id, message)

            # Save new updates
            self.data_manager.save_updates(new_updates)

            logger.info(f"Update check completed. Found {len(added_updates)} new updates.")

        except Exception as e:
            logger.error(f"Error during update check: {e}")
            # Notify all users about the error
            for user_id in self.user_manager.get_all_users():
                await self.send_message(user_id, "⚠️ Error occurred while checking for updates")

    async def run_periodic_updates(self):
        while True:
            await self.check_updates()
            await asyncio.sleep(UPDATE_INTERVAL)

    async def run(self):
        logger.info("Starting Mintos Update Bot")
        async with self.application:
            await self.application.initialize()
            await self.application.start()
            await self.run_periodic_updates()
            await self.application.run_polling()

if __name__ == "__main__":
    bot = MintosBot()
    asyncio.run(bot.run())