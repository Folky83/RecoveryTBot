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
import fcntl
import errno

LOCK_FILE = 'bot.lock'

def acquire_lock():
    """Try to acquire a lock file to ensure single instance"""
    try:
        # First check if lock file exists but is stale
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, 'r') as f:
                    old_pid = int(f.read().strip())
                if not psutil.pid_exists(old_pid):
                    os.unlink(LOCK_FILE)
                    logging.info(f"Removed stale lock file from PID {old_pid}")
            except (ValueError, IOError):
                os.unlink(LOCK_FILE)
                logging.info("Removed invalid lock file")

        # Create new lock file
        lock_file = open(LOCK_FILE, 'w')
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        return lock_file
    except IOError as e:
        if e.errno == errno.EAGAIN:
            logging.error("Another instance is already running")
            sys.exit(1)
        raise

async def kill_port_process(port):
    """Kill any process using the specified port"""
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.connections():
                    if conn.laddr.port == port:
                        logging.info(f"Killing process {proc.pid} using port {port}")
                        proc.kill()
                        await asyncio.sleep(2)  # Increased wait time
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # Additional wait to ensure port is released
        await asyncio.sleep(3)
    except Exception as e:
        logging.error(f"Error in kill_port_process: {e}")

async def kill_existing_processes():
    """Kill any existing Python and Streamlit processes"""
    try:
        # First kill any process using port 5000
        await kill_port_process(5000)

        # Then kill any existing streamlit or run.py processes
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid != current_pid:  # Don't kill ourselves
                    cmdline = proc.cmdline()
                    if cmdline and ('streamlit' in ' '.join(cmdline) or 'run.py' in ' '.join(cmdline)):
                        logging.info(f"Killing process {proc.pid}: {' '.join(cmdline)}")
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        await asyncio.sleep(5)  # Extended wait time for cleanup
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

async def cleanup(lock_file=None):
    """Force cleanup any existing bot instances and processes"""
    try:
        logging.info("Starting cleanup process...")
        await kill_existing_processes()
        await asyncio.sleep(3)  # Extended wait time

        # Clean up any existing bot instances
        async with managed_bot() as bot:
            if bot.application and bot.application.bot:
                await bot.application.bot.delete_webhook(drop_pending_updates=True)
                await bot.application.bot.get_updates(offset=-1)
                await asyncio.sleep(2)

        # Release lock file if provided
        if lock_file:
            try:
                os.unlink(LOCK_FILE)
                lock_file.close()
            except:
                pass

        logging.info("Cleanup completed successfully")
    except Exception as e:
        logging.error(f"Cleanup error: {e}")

async def wait_for_streamlit(process, timeout=60):  # Increased timeout
    """Wait for Streamlit to start and verify it's running"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if process.poll() is not None:
            raise RuntimeError("Streamlit process terminated unexpectedly")

        # Check if port 5000 is in use
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    for conn in proc.connections():
                        if conn.laddr.port == 5000 and conn.status == 'LISTEN':
                            logging.info("Streamlit is running on port 5000")
                            await asyncio.sleep(2)  # Give Streamlit extra time to fully initialize
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logging.error(f"Error checking Streamlit status: {e}")

        await asyncio.sleep(1)

    raise TimeoutError("Streamlit failed to start within timeout period")

async def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Try to acquire lock file
    lock_file = None
    try:
        lock_file = acquire_lock()
        logging.info(f"Lock file acquired for PID {os.getpid()}")

        # Always perform cleanup first
        await cleanup()
        await asyncio.sleep(5)  # Extended wait time for cleanup

        streamlit_process = None
        try:
            # Start Streamlit first
            logging.info("Starting Streamlit process...")
            streamlit_process = subprocess.Popen([
                sys.executable, "-m", "streamlit", "run",
                "main.py", "--server.address", "0.0.0.0",
                "--server.port", "5000"
            ])

            # Wait for Streamlit to start
            await wait_for_streamlit(streamlit_process)
            logging.info("Streamlit started successfully")
            await asyncio.sleep(2)  # Give extra time after Streamlit is confirmed running

            # Now start the bot
            async with managed_bot() as bot:
                # Initialize and run the bot
                await bot.cleanup()  # Ensure clean state before starting
                await asyncio.sleep(2)  # Wait after cleanup
                bot_task = asyncio.create_task(bot.run())

                # Wait for bot task to complete
                await bot_task

        except Exception as e:
            logging.error(f"Application error: {e}")
            raise
        finally:
            # Cleanup on exit
            if streamlit_process:
                logging.info("Terminating Streamlit process...")
                streamlit_process.terminate()
                try:
                    streamlit_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logging.warning("Streamlit process did not terminate gracefully, forcing kill")
                    streamlit_process.kill()

    finally:
        # Release lock file
        await cleanup(lock_file)

def signal_handler(sig, frame):
    logging.info("Received shutdown signal, cleaning up...")
    # Force cleanup of any remaining processes
    asyncio.get_event_loop().run_until_complete(kill_existing_processes())
    # Remove lock file on shutdown
    try:
        os.unlink(LOCK_FILE)
    except:
        pass
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start the application
    asyncio.run(main())