import asyncio
from bot.telegram_bot import MintosBot
import subprocess
import sys
import signal
import psutil
import logging
import os
import time
import contextlib

async def kill_port_process(port):
    """Kill any process using the specified port"""
    for proc in psutil.process_iter(['pid', 'name', 'connections']):
        try:
            for conn in proc.info.get('connections', []):
                if hasattr(conn, 'laddr') and hasattr(conn.laddr, 'port') and conn.laddr.port == port:
                    proc.kill()
                    await asyncio.sleep(0.5)  # Give process time to die
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

async def kill_existing_processes():
    """Kill any existing Python and Streamlit processes"""
    try:
        # First kill any process using port 5000
        await kill_port_process(5000)

        # Then kill any existing streamlit processes
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and ('streamlit' in ' '.join(cmdline) or 'run.py' in ' '.join(cmdline)):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        await asyncio.sleep(3)  # Give processes time to close
        logging.info("Existing processes killed successfully")
    except Exception as e:
        logging.error(f"Error killing existing processes: {e}")

@contextlib.asynccontextmanager
async def managed_bot():
    """Context manager for bot lifecycle management"""
    bot = None
    try:
        bot = MintosBot()
        yield bot
    finally:
        if bot:
            await bot.cleanup()

async def cleanup():
    """Force cleanup any existing bot instances and processes"""
    try:
        logging.info("Starting cleanup process...")
        await kill_existing_processes()
        await asyncio.sleep(2)  # Give time for cleanup

        # Clean up any existing bot instances
        async with managed_bot() as bot:
            if bot.application and bot.application.bot:
                await bot.application.bot.delete_webhook(drop_pending_updates=True)
                await bot.application.bot.get_updates(offset=-1)
                await asyncio.sleep(2)

        logging.info("Cleanup completed successfully")
    except Exception as e:
        logging.error(f"Cleanup error: {e}")

async def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Always perform cleanup first
    await cleanup()
    await asyncio.sleep(2)  # Give extra time for cleanup to complete

    streamlit_process = None
    try:
        async with managed_bot() as bot:
            # Initialize and run the bot
            bot_task = asyncio.create_task(bot.run())

            # Give the bot time to initialize before starting Streamlit
            await asyncio.sleep(2)

            # Start Streamlit in a separate process
            streamlit_process = subprocess.Popen([
                sys.executable, "-m", "streamlit", "run",
                "main.py", "--server.address", "0.0.0.0",
                "--server.port", "5000"
            ])

            # Wait for bot task to complete
            await bot_task

    except Exception as e:
        logging.error(f"Application error: {e}")
    finally:
        # Cleanup on exit
        if streamlit_process:
            streamlit_process.terminate()
            try:
                streamlit_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                streamlit_process.kill()

def signal_handler(sig, frame):
    logging.info("Received shutdown signal, cleaning up...")
    # Force cleanup of any remaining processes
    asyncio.get_event_loop().run_until_complete(kill_existing_processes())
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start the application
    asyncio.run(main())
