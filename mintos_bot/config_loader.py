"""
Simple configuration loader that supports multiple ways to set the Telegram token
Makes it easy for Windows users to configure the bot.
"""
import os
import logging

def load_telegram_token():
    """
    Load Telegram bot token from multiple sources in order of preference:
    1. Environment variable TELEGRAM_BOT_TOKEN
    2. config.txt file in current directory
    3. config.txt file in user's home directory
    """
    logger = logging.getLogger(__name__)
    
    # Method 1: Environment variable
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if token:
        logger.info("Telegram token loaded from environment variable")
        return token
    
    # Method 2: config.txt in current directory
    config_files = ['config.txt', 'bot_config.txt', '.env']
    
    for config_file in config_files:
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('TELEGRAM_BOT_TOKEN='):
                            token = line.split('=', 1)[1].strip()
                            if token:
                                logger.info(f"Telegram token loaded from {config_file}")
                                return token
            except Exception as e:
                logger.warning(f"Could not read {config_file}: {e}")
    
    # Method 3: config.txt in home directory
    home_config = os.path.expanduser('~/mintos_bot_config.txt')
    if os.path.exists(home_config):
        try:
            with open(home_config, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('TELEGRAM_BOT_TOKEN='):
                        token = line.split('=', 1)[1].strip()
                        if token:
                            logger.info(f"Telegram token loaded from {home_config}")
                            return token
        except Exception as e:
            logger.warning(f"Could not read {home_config}: {e}")
    
    # No token found - provide helpful instructions
    logger.error("No Telegram bot token found!")
    logger.error("Please set your token using one of these methods:")
    logger.error("1. Set environment variable: set TELEGRAM_BOT_TOKEN=your_token_here")
    logger.error("2. Create config.txt file with: TELEGRAM_BOT_TOKEN=your_token_here")
    logger.error("3. Create ~/.mintos_bot_config.txt with: TELEGRAM_BOT_TOKEN=your_token_here")
    
    return None

def create_sample_config():
    """Create a sample config file for users"""
    sample_config = """# Mintos Telegram Bot Configuration
# Replace 'your_bot_token_here' with your actual Telegram bot token
TELEGRAM_BOT_TOKEN=your_bot_token_here

# To get a bot token:
# 1. Open Telegram and search for @BotFather
# 2. Send /newbot command
# 3. Follow the instructions to create your bot
# 4. Copy the token and replace 'your_bot_token_here' above
"""
    
    try:
        with open('config.txt', 'w', encoding='utf-8') as f:
            f.write(sample_config)
        print("Created sample config.txt file")
        print("Please edit config.txt and add your Telegram bot token")
        return True
    except Exception as e:
        print(f"Could not create config.txt: {e}")
        return False