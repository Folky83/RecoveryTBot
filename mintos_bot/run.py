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
        # Try to import the main run script from parent directory
        import sys
        import importlib.util
        
        # Look for run.py in the current working directory
        run_path = os.path.join(os.getcwd(), 'run.py')
        if os.path.exists(run_path):
            spec = importlib.util.spec_from_file_location("run", run_path)
            run_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(run_module)
            asyncio.run(run_module.main())
        else:
            # Fallback to direct bot import with Streamlit
            import subprocess
            import time
            
            # Start Streamlit in background
            print("Starting dashboard on http://localhost:5000...")
            
            # Find main.py in the current directory or package directory
            main_path = None
            if os.path.exists("main.py"):
                main_path = "main.py"
            else:
                # Try to find main.py in the package installation
                import mintos_bot
                package_dir = os.path.dirname(mintos_bot.__file__)
                parent_dir = os.path.dirname(package_dir)
                potential_main = os.path.join(parent_dir, "main.py")
                if os.path.exists(potential_main):
                    main_path = potential_main
            
            if main_path:
                streamlit_process = subprocess.Popen([
                    sys.executable, "-m", "streamlit", "run",
                    main_path, "--server.address", "0.0.0.0",
                    "--server.port", "5000"
                ])
            else:
                print("Warning: main.py not found, running bot without dashboard")
                streamlit_process = None
            
            # Wait a moment for Streamlit to start
            time.sleep(3)
            
            # Start the bot
            from .telegram_bot import MintosBot
            
            async def run_bot():
                bot = MintosBot()
                await bot.run()
            
            try:
                asyncio.run(run_bot())
            finally:
                if streamlit_process:
                    streamlit_process.terminate()
                
    except ImportError as e:
        print(f"Import error: {e}")
        # Simple bot-only mode
        from .telegram_bot import MintosBot
        
        async def run_bot():
            bot = MintosBot()
            await bot.run()
        
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