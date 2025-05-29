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

# Import configuration
from mintos_bot.constants import (
    LOCK_FILE, STREAMLIT_PORT, STARTUP_TIMEOUT, CLEANUP_WAIT,
    PROCESS_KILL_WAIT, BOT_STARTUP_TIMEOUT, TELEGRAM_BOT_TOKEN_VAR
)

@dataclass
class ProcessManager:
    lock_file: Optional[Any] = None
    streamlit_process: Optional[subprocess.Popen] = None

    def __post_init__(self):
        self.logger = logging.getLogger(__name__)

    async def acquire_lock(self) -> bool:
        """Acquire lock file to ensure single instance"""
        try:
            if os.path.exists(LOCK_FILE):
                try:
                    with open(LOCK_FILE, 'r') as f:
                        old_pid = int(f.read().strip())
                    if not psutil.pid_exists(old_pid):
                        os.unlink(LOCK_FILE)
                        self.logger.info(f"Removed stale lock from PID {old_pid}")
                except (ValueError, IOError):
                    os.unlink(LOCK_FILE)
                    self.logger.info("Removed invalid lock file")

            self.lock_file = open(LOCK_FILE, 'w')
            fcntl.lockf(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file.write(str(os.getpid()))
            self.lock_file.flush()
            return True
        except IOError as e:
            if e.errno == errno.EAGAIN:
                self.logger.error("Another instance is already running")
                sys.exit(1)
            raise

    async def kill_port_process(self, port: int) -> None:
        """Kill any process using the specified port"""
        try:
            # Get all connections first
            for conn in psutil.net_connections(kind='inet'):
                try:
                    if (hasattr(conn, 'laddr') and conn.laddr and 
                        isinstance(conn.laddr, tuple) and len(conn.laddr) >= 2 and 
                        isinstance(conn.laddr[1], int) and conn.laddr[1] == port):
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
                        if (hasattr(conn, 'laddr') and conn.laddr and 
                            isinstance(conn.laddr, tuple) and len(conn.laddr) >= 2 and 
                            isinstance(conn.laddr[1], int) and conn.laddr[1] == STREAMLIT_PORT and 
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
                    if os.path.exists(LOCK_FILE):
                        os.unlink(LOCK_FILE)
                except FileNotFoundError:
                    self.logger.warning(f"Lock file {LOCK_FILE} not found during cleanup")
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
    from mintos_bot.telegram_bot import MintosBot
    bot = None
    logger = logging.getLogger(__name__)
    try:
        logger.info("Starting bot initialization...")
        if not os.getenv(TELEGRAM_BOT_TOKEN_VAR):
            logger.error(f"{TELEGRAM_BOT_TOKEN_VAR} environment variable is not set")
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
    
    # Simple cleanup without creating new event loops
    try:
        # Kill processes using the port
        for conn in psutil.net_connections(kind='inet'):
            try:
                if (hasattr(conn, 'laddr') and conn.laddr and 
                    isinstance(conn.laddr, tuple) and len(conn.laddr) >= 2 and 
                    isinstance(conn.laddr[1], int) and conn.laddr[1] == STREAMLIT_PORT):
                    pid = conn.pid
                    if pid and psutil.pid_exists(pid):
                        logging.info(f"Killing process {pid} using port {STREAMLIT_PORT}")
                        try:
                            proc = psutil.Process(pid)
                            proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
            except (AttributeError, TypeError):
                continue
        
        # Clean up lock file
        try:
            os.unlink(LOCK_FILE)
        except FileNotFoundError:
            pass
        except Exception as e:
            logging.error(f"Error removing lock file: {e}")
            
    except Exception as e:
        logging.error(f"Error during signal handler cleanup: {e}")
        
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(main())