import asyncio
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
from typing import Optional, Any
from dataclasses import dataclass
from psutil import Process

# Configuration
LOCK_FILE = 'bot.lock'
STREAMLIT_PORT = 5000
STARTUP_TIMEOUT = 60
CLEANUP_WAIT = 5
PROCESS_KILL_WAIT = 3
BOT_STARTUP_TIMEOUT = 30  # Add timeout for bot initialization

@dataclass
class ProcessManager:
    lock_file: Optional[Any] = None
    streamlit_process: Optional[subprocess.Popen] = None

    def __post_init__(self):
        self.logger = logging.getLogger(__name__)

    async def acquire_lock(self) -> bool:
        """Acquire lock file to ensure single instance with enhanced cleanup"""
        try:
            # Check for existing lock file
            if os.path.exists(LOCK_FILE):
                try:
                    # Try to read the PID from the lock file
                    with open(LOCK_FILE, 'r') as f:
                        content = f.read().strip()
                        if content:
                            try:
                                old_pid = int(content)
                                # Check if the process is still running
                                if psutil.pid_exists(old_pid):
                                    try:
                                        proc = psutil.Process(old_pid)
                                        # Check if it's a Python process that might be our bot
                                        cmdline = ' '.join(proc.cmdline())
                                        if 'python' in cmdline and ('run.py' in cmdline or 'bot' in cmdline):
                                            # This appears to be another bot instance
                                            self.logger.warning(f"Found running bot process with PID {old_pid}")
                                            
                                            # Check if the process is a zombie or unresponsive
                                            if proc.status() in ['zombie', 'dead']:
                                                self.logger.warning(f"Process {old_pid} is a zombie, terminating it")
                                                proc.kill()
                                                os.unlink(LOCK_FILE)
                                            else:
                                                # Check if Telegram API is in conflict
                                                has_conflict = await self._check_telegram_conflict(proc)
                                                
                                                if has_conflict:
                                                    self.logger.critical(f"Telegram conflict detected with PID {old_pid}, terminating it")
                                                    proc.kill()
                                                    await asyncio.sleep(3)  # Give time for cleanup
                                                    os.unlink(LOCK_FILE)
                                                else:
                                                    # Active, non-conflicting instance, so we should exit
                                                    self.logger.error(f"Active bot instance with PID {old_pid} is running properly")
                                                    return False
                                        else:
                                            # Not our bot process, remove the lock
                                            self.logger.info(f"Found unrelated process with PID {old_pid}, removing lock")
                                            os.unlink(LOCK_FILE)
                                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                                        self.logger.info(f"Could not access process {old_pid}: {e}")
                                        os.unlink(LOCK_FILE)
                                else:
                                    # Process doesn't exist, remove stale lock
                                    self.logger.info(f"Removed stale lock from non-existent PID {old_pid}")
                                    os.unlink(LOCK_FILE)
                            except ValueError:
                                # Invalid PID in lock file
                                self.logger.info(f"Invalid PID in lock file: {content}")
                                os.unlink(LOCK_FILE)
                        else:
                            # Empty lock file
                            self.logger.info("Empty lock file found, removing it")
                            os.unlink(LOCK_FILE)
                except (ValueError, IOError) as e:
                    # Invalid lock file format
                    self.logger.info(f"Invalid lock file format: {e}")
                    os.unlink(LOCK_FILE)

            # Create new lock file
            self.lock_file = open(LOCK_FILE, 'w')
            try:
                fcntl.lockf(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.lock_file.write(str(os.getpid()))
                self.lock_file.flush()
                self.logger.info(f"Lock acquired for PID {os.getpid()}")
                return True
            except IOError as e:
                if e.errno == errno.EAGAIN:
                    self.logger.error("Another process has an exclusive lock on the file")
                    self.lock_file.close()
                    return False
                raise
        except Exception as e:
            self.logger.error(f"Unexpected error in acquire_lock: {e}", exc_info=True)
            return False
            
    async def _check_telegram_conflict(self, proc: Process) -> bool:
        """Check if the given process is causing Telegram API conflicts"""
        try:
            # This would require a more sophisticated check in a real scenario
            # For now, we'll check if there are stderr logs with conflict messages in the process
            # or if the process has been running for too long with no successful activity
            
            # We'll assume a conflict if the process is more than 30 minutes old
            # This is a simplification - in a real scenario you might check networking activity
            # or parse logs more extensively
            process_age = time.time() - proc.create_time()
            if process_age > 30 * 60:  # 30 minutes
                self.logger.warning(f"Process {proc.pid} is more than 30 minutes old, potential zombie")
                return True
                
            # Additional checks could include:
            # - Monitoring process CPU/memory usage to detect hung processes
            # - Examining open network connections to the Telegram API
            # - Tracking the age of the cache files to detect inactive processes
            
            return False
        except Exception as e:
            self.logger.error(f"Error checking Telegram conflict: {e}", exc_info=True)
            return False

    async def kill_port_process(self, port: int) -> None:
        """Kill any process using the specified port"""
        try:
            # Get all connections first
            for conn in psutil.net_connections(kind='inet'):
                try:
                    if (hasattr(conn, 'laddr') and 
                        isinstance(conn.laddr, tuple) and len(conn.laddr) >= 2 and 
                        conn.laddr[1] == port):
                        pid = conn.pid
                        if pid and psutil.pid_exists(pid):
                            self.logger.info(f"Killing process {pid} using port {port}")
                            try:
                                proc = psutil.Process(pid)
                                proc.kill()
                                await asyncio.sleep(PROCESS_KILL_WAIT)
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                self.logger.warning(f"Could not kill process {pid}")
                except (AttributeError, TypeError) as e:
                    self.logger.debug(f"Skipping malformed connection: {e}")
        except Exception as e:
            self.logger.error(f"Error killing port process: {e}", exc_info=True)

    async def cleanup_processes(self) -> None:
        """Clean up all related processes"""
        try:
            self.logger.info("Starting process cleanup...")
            await self.kill_port_process(STREAMLIT_PORT)
            current_pid = os.getpid()

            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.pid != current_pid:
                        cmdline = proc.cmdline()
                        if cmdline and ('streamlit' in ' '.join(cmdline) or 'run.py' in ' '.join(cmdline)):
                            self.logger.info(f"Killing process {proc.pid}: {' '.join(cmdline)}")
                            proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            await asyncio.sleep(CLEANUP_WAIT)
            self.logger.info("Process cleanup completed")
        except Exception as e:
            self.logger.error(f"Error in process cleanup: {e}")

    async def wait_for_streamlit(self) -> None:
        """Wait for Streamlit to start and verify it's running"""
        if not self.streamlit_process:
            raise RuntimeError("Streamlit process not initialized")

        start_time = time.time()
        while time.time() - start_time < STARTUP_TIMEOUT:
            if self.streamlit_process.poll() is not None:
                raise RuntimeError("Streamlit process terminated unexpectedly")

            try:
                # Check all network connections
                for conn in psutil.net_connections(kind='inet'):
                    try:
                        # Check if this connection is our streamlit server
                        if (hasattr(conn, 'laddr') and 
                            isinstance(conn.laddr, tuple) and len(conn.laddr) >= 2 and 
                            conn.laddr[1] == STREAMLIT_PORT and 
                            hasattr(conn, 'status') and conn.status == 'LISTEN'):
                            self.logger.info(f"Streamlit running on port {STREAMLIT_PORT}")
                            await asyncio.sleep(2)  # Give it a moment to fully initialize
                            return
                    except (AttributeError, TypeError) as e:
                        self.logger.debug(f"Skipping malformed connection while checking Streamlit: {e}")
            except Exception as e:
                self.logger.error(f"Error checking Streamlit status: {e}", exc_info=True)

            await asyncio.sleep(1)

        raise TimeoutError("Streamlit failed to start within timeout")

    async def cleanup(self) -> None:
        """Cleanup all resources"""
        try:
            self.logger.info("Starting cleanup process...")
            await self.cleanup_processes()

            if self.lock_file:
                try:
                    self.lock_file.close()
                    os.unlink(LOCK_FILE)
                except Exception as e:
                    self.logger.error(f"Error cleaning up lock file: {e}")

            try:
                await asyncio.sleep(0.5)
                self.logger.info("Cleanup completed")
            except asyncio.CancelledError:
                self.logger.info("Cleanup interrupted but completed")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

@contextlib.asynccontextmanager
async def managed_bot():
    """Context manager for bot lifecycle"""
    from bot.telegram_bot import MintosBot
    bot = None
    logger = logging.getLogger(__name__)
    try:
        logger.info("Starting bot initialization...")
        if not os.getenv('TELEGRAM_BOT_TOKEN'):
            logger.error("TELEGRAM_BOT_TOKEN environment variable is not set")
            raise ValueError("Bot token is missing")

        bot = MintosBot()
        start_time = time.time()
        while not hasattr(bot, 'token') and time.time() - start_time < BOT_STARTUP_TIMEOUT:
            logger.warning("Waiting for bot token initialization...")
            await asyncio.sleep(1)

        if not hasattr(bot, 'token'):
            raise RuntimeError("Bot failed to initialize token within timeout")

        logger.info("Bot instance created successfully with valid token")
        yield bot
    except ImportError as e:
        logger.error(f"Failed to import required modules: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Failed to initialize bot: {str(e)}")
        raise
    finally:
        if bot:
            logger.info("Cleaning up bot resources...")
            await bot.cleanup()
            logger.info("Bot cleanup completed")

async def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    process_manager = ProcessManager()
    try:
        # Acquire lock and clean up existing processes
        await process_manager.acquire_lock()
        logger.info(f"Lock acquired for PID {os.getpid()}")
        await process_manager.cleanup()

        # Start Streamlit
        logger.info("Starting Streamlit process...")
        process_manager.streamlit_process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run",
            "main.py", "--server.address", "0.0.0.0",
            "--server.port", str(STREAMLIT_PORT)
        ])

        # Wait for Streamlit and start bot
        await process_manager.wait_for_streamlit()
        logger.info("Streamlit started successfully")

        async with managed_bot() as bot:
            logger.info("Initializing Telegram bot...")
            try:
                # Start the bot and wait for it indefinitely
                bot_task = asyncio.create_task(bot.run())
                logger.info("Bot task created, waiting for completion...")
                await bot_task
            except asyncio.CancelledError:
                logger.info("Bot task was cancelled")
                raise
            except Exception as e:
                logger.error(f"Bot error: {str(e)}")
                raise

    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        raise
    finally:
        if process_manager.streamlit_process:
            logger.info("Terminating Streamlit...")
            process_manager.streamlit_process.terminate()
            try:
                process_manager.streamlit_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Force killing Streamlit process")
                process_manager.streamlit_process.kill()
        await process_manager.cleanup()

def signal_handler(sig, frame):
    logging.info("Received shutdown signal")
    asyncio.get_event_loop().run_until_complete(ProcessManager().cleanup_processes())
    try:
        os.unlink(LOCK_FILE)
    except FileNotFoundError:
        pass  # Ignore if the file does not exist
    except Exception as e:
        logging.error(f"Error removing lock file: {e}")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(main())