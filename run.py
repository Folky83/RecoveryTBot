
import asyncio
from bot.telegram_bot import MintosBot
import subprocess
import sys
import signal
import psutil
import logging

async def kill_existing_processes():
    """Kill any existing Python processes using port 5000"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and 'streamlit' in ' '.join(cmdline):
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    await asyncio.sleep(2)  # Give processes time to close

async def cleanup():
    """Force cleanup any existing bot instances"""
    try:
        await kill_existing_processes()
        bot = MintosBot()
        await bot.application.bot.delete_webhook(drop_pending_updates=True)
        await bot.application.bot.get_updates(offset=-1)
        await asyncio.sleep(3)  # Give more time for cleanup
    except Exception as e:
        print(f"Cleanup error: {e}")

async def main():
    # Perform cleanup first
    await cleanup()
    
    try:
        # Initialize and run the bot
        bot = MintosBot()
        bot_task = asyncio.create_task(bot.run())
        
        # Start Streamlit in a separate process
        streamlit_process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run",
            "main.py", "--server.address", "0.0.0.0",
            "--server.port", "5000"
        ])
        
        await bot_task
    except Exception as e:
        logging.error(f"Bot error: {e}")
    finally:
        if 'streamlit_process' in locals():
            streamlit_process.terminate()

def signal_handler(sig, frame):
    print("Shutting down gracefully...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(main())
