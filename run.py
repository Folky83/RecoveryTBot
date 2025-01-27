
import asyncio
from bot.telegram_bot import MintosBot
import subprocess
import sys
import signal

async def cleanup():
    """Force cleanup any existing bot instances"""
    try:
        # Delete webhook and clear pending updates
        bot = MintosBot()
        await bot.application.bot.delete_webhook(drop_pending_updates=True)
        await bot.application.bot.get_updates(offset=-1)
        await asyncio.sleep(2)  # Give time for cleanup
    except Exception as e:
        print(f"Cleanup error: {e}")

async def main():
    # Perform cleanup first
    await cleanup()
    
    # Initialize and run the bot
    bot = MintosBot()
    bot_task = asyncio.create_task(bot.run())
    
    # Start Streamlit in a separate process
    streamlit_process = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run",
        "main.py", "--server.address", "0.0.0.0",
        "--server.port", "5000"
    ])
    
    try:
        await bot_task
    except Exception as e:
        print(f"Bot error: {e}")
    finally:
        streamlit_process.terminate()

def signal_handler(sig, frame):
    print("Shutting down gracefully...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(main())
