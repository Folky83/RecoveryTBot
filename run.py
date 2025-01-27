import asyncio
from bot.telegram_bot import MintosBot
import subprocess
import sys
import signal
import psutil
import logging
import os
import time

async def kill_port_process(port):
    """Kill any process using the specified port"""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for conn in proc.connections('inet'):  # Specify connection kind
                if hasattr(conn, 'laddr') and conn.laddr.port == port:
                    logging.info(f"Killing process {proc.pid} using port {port}")
                    proc.kill()
                    await asyncio.sleep(0.5)  # Give process time to die
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

async def kill_existing_processes():
    """Kill any existing Python and Streamlit processes"""
    logging.info("Starting cleanup of existing processes")

    # First kill any process using port 5001
    await kill_port_process(5001)

    # Then kill any existing streamlit and python processes
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline and ('streamlit' in ' '.join(cmdline) or 'run.py' in ' '.join(cmdline)):
                logging.info(f"Killing process: {proc.pid}")
                try:
                    proc.kill()
                except psutil.NoSuchProcess:
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # Give processes time to fully terminate
    await asyncio.sleep(5)  # Increased sleep time for thorough cleanup

async def cleanup():
    """Force cleanup any existing bot instances and processes"""
    try:
        logging.info("Starting cleanup process...")
        await kill_existing_processes()
        logging.info("Process cleanup completed")

        # Clean up any existing bot instances
        try:
            bot = MintosBot()
            if hasattr(bot, 'application') and bot.application and bot.application.bot:
                logging.info("Cleaning up existing bot instance...")
                await bot.application.bot.delete_webhook(drop_pending_updates=True)
                try:
                    await asyncio.wait_for(
                        bot.application.bot.get_updates(offset=-1),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logging.warning("Timeout while cleaning up updates, continuing anyway")
                except Exception as e:
                    logging.warning(f"Non-critical error during update cleanup: {e}")
        except Exception as e:
            logging.warning(f"Bot cleanup warning (non-critical): {e}")

        await asyncio.sleep(3)  # Give more time for cleanup
        logging.info("Cleanup completed successfully")
    except Exception as e:
        logging.error(f"Cleanup error: {e}")
        # Continue despite cleanup errors - new instance might still work

async def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)

    # Perform cleanup first
    await cleanup()

    streamlit_process = None
    try:
        # Initialize and run the bot
        bot = MintosBot()
        bot_task = asyncio.create_task(bot.run())

        # Give the bot time to initialize before starting Streamlit
        await asyncio.sleep(5)  # Increased sleep time for proper initialization

        # Start Streamlit in a separate process
        logging.info("Starting Streamlit process...")
        streamlit_process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run",
            "main.py", "--server.address", "0.0.0.0",
            "--server.port", "5001"
        ])
        logging.info("Streamlit process started")

        # Wait for bot task to complete
        await bot_task

    except Exception as e:
        logging.error(f"Application error: {e}")
    finally:
        # Cleanup on exit
        if streamlit_process:
            logging.info("Terminating Streamlit process...")
            streamlit_process.terminate()
            try:
                streamlit_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logging.warning("Streamlit process didn't terminate gracefully, forcing kill")
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