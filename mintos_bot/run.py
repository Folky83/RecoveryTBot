#!/usr/bin/env python3
"""
Main entry point for the Mintos Telegram Bot
Simple startup script that handles configuration and launches the bot.
"""
import asyncio
import sys
import os
import logging
from .config_loader import load_telegram_token, create_sample_config

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """Main entry point for the Mintos bot"""
    print("Starting Mintos Telegram Bot...")
    
    # Load the token
    token = load_telegram_token()
    
    if not token:
        print("\nNo Telegram bot token found!")
        print("Would you like to create a sample config file? (y/n): ", end="")
        
        try:
            response = input().lower().strip()
            if response in ['y', 'yes']:
                if create_sample_config():
                    print("\nPlease edit config.txt and add your bot token, then run the bot again.")
                    return 1
                else:
                    print("\nCould not create config file. Please set TELEGRAM_BOT_TOKEN environment variable.")
                    return 1
            else:
                print("\nPlease set your bot token using one of these methods:")
                print("1. Set environment variable: set TELEGRAM_BOT_TOKEN=your_token_here")
                print("2. Create config.txt file with: TELEGRAM_BOT_TOKEN=your_token_here")
                return 1
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            return 1
    
    # Set the token as environment variable for the rest of the application
    os.environ['TELEGRAM_BOT_TOKEN'] = token
    
    # Import and run the bot (after setting the token)
    try:
        # Import the main run script
        import run
        asyncio.run(run.main())
    except ImportError:
        # Fallback to direct bot import
        from .telegram_bot import MintosBot
        
        async def run_bot():
            bot = MintosBot()
            await bot.start()
        
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
        return 0
    except Exception as e:
        print(f"Error starting bot: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())