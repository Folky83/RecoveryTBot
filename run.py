
import asyncio
from bot.telegram_bot import MintosBot
import subprocess
import sys

async def main():
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
    finally:
        streamlit_process.terminate()

if __name__ == "__main__":
    asyncio.run(main())
