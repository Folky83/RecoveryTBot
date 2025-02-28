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
        """Acquire lock file to ensure single instance"""
        try:
            # Always try to remove stale lock files in deployment
            if os.path.exists(LOCK_FILE):
                try:
                    with open(LOCK_FILE, 'r') as f:
                        old_pid = int(f.read().strip())
                    if not psutil.pid_exists(old_pid):
                        os.unlink(LOCK_FILE)
                        self.logger.info(f"Removed stale lock from PID {old_pid}")
                    else:
                        # In deployment environment, force override
                        os.unlink(LOCK_FILE)
                        self.logger.warning(f"Force removed lock file in deployment")
                except (ValueError, IOError):
                    # Handle corrupt lock files
                    try:
                        os.unlink(LOCK_FILE)
                        self.logger.info("Removed invalid lock file")
                    except Exception as e:
                        self.logger.error(f"Error removing invalid lock file: {e}")

            # Create with more robust error handling
            try:
                self.lock_file = open(LOCK_FILE, 'w')
                fcntl.lockf(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.lock_file.write(str(os.getpid()))
                self.lock_file.flush()
                self.logger.info(f"Successfully acquired lock for PID {os.getpid()}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to create lock file: {e}")
                # Continue anyway in deployment
                return True
                
        except IOError as e:
            if e.errno == errno.EAGAIN:
                self.logger.warning("Another instance appears to be running, forcing start anyway")
                try:
                    os.unlink(LOCK_FILE)
                    self.logger.info("Removed existing lock file")
                    return await self.acquire_lock()  # Try again
                except Exception:
                    self.logger.error("Could not remove existing lock file")
                    return True  # Continue anyway in deployment
            self.logger.error(f"Lock acquisition error: {e}")
            return True  # Continue anyway in deployment

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
    max_attempts = 5  # Increased for deployment
    
    for attempt in range(max_attempts):
        try:
            logger.info(f"Starting bot initialization (attempt {attempt+1}/{max_attempts})...")
            
            # Verify token is available with multiple retries
            token = None
            for token_attempt in range(3):
                token = os.getenv('TELEGRAM_BOT_TOKEN')
                if token:
                    logger.info(f"Token found on attempt {token_attempt+1}")
                    break
                    
                logger.warning(f"TELEGRAM_BOT_TOKEN not found (attempt {token_attempt+1}/3), waiting 10 seconds...")
                await asyncio.sleep(10)  # Longer wait for deployment environment variables
            
            if not token:
                # In deployment, we want to continue anyway as the variable might become available later
                logger.error("TELEGRAM_BOT_TOKEN environment variable is not set after retries")
                if 'REPL_SLUG' in os.environ:  # Check if we're in Replit deployment
                    logger.warning("Running in deployment environment - continuing despite missing token")
                else:
                    raise ValueError("Bot token is missing after retry")
            
            logger.info("Creating bot instance...")
            bot = MintosBot()
            
            # Wait for initialization with extended timeout for deployment
            start_time = time.time()
            init_timeout = BOT_STARTUP_TIMEOUT * 2 if 'REPL_SLUG' in os.environ else BOT_STARTUP_TIMEOUT
            init_phase = "checking token"
            
            while time.time() - start_time < init_timeout:
                try:
                    if not hasattr(bot, 'token'):
                        logger.warning(f"Waiting for bot token initialization... ({int(time.time() - start_time)}s)")
                        await asyncio.sleep(2)  # Longer sleep for deployment
                        continue
                    
                    # Once token is set, check application
                    if init_phase == "checking token":
                        init_phase = "checking application"
                        logger.info("Token initialized, waiting for application...")
                    
                    if not hasattr(bot, 'application') or not bot.application:
                        logger.warning(f"Waiting for application initialization... ({int(time.time() - start_time)}s)")
                        await asyncio.sleep(2)  # Longer sleep for deployment
                        continue
                    
                    # Bot is fully initialized
                    logger.info(f"Bot fully initialized after {int(time.time() - start_time)} seconds")
                    break
                except Exception as init_error:
                    logger.error(f"Error during initialization check: {init_error}")
                    await asyncio.sleep(2)
            
            # More lenient verification for deployment
            if 'REPL_SLUG' in os.environ:  # If in deployment
                # Give the bot instance to caller even if not fully initialized
                logger.info("In deployment - proceeding even if initialization is incomplete")
                yield bot
                return  # Exit the retry loop
            else:
                # In development, enforce strict checks
                if not hasattr(bot, 'token'):
                    raise RuntimeError("Bot failed to initialize token within timeout")
                
                if not hasattr(bot, 'application') or not bot.application:
                    raise RuntimeError("Bot application not initialized within timeout")
                
                logger.info("Bot instance created successfully with valid configuration")
                yield bot
                return  # Success, exit the retry loop
            
        except ImportError as e:
            logger.error(f"Failed to import required modules: {str(e)}")
            if attempt < max_attempts - 1:
                logger.info(f"Retrying in 10 seconds...")
                await asyncio.sleep(10)  # Longer sleep for deployment
            else:
                # In deployment, continue anyway after max attempts
                if 'REPL_SLUG' in os.environ:
                    logger.error("Max import retries reached in deployment - continuing anyway")
                    yield MintosBot()  # Provide a new instance as last resort
                    return
                else:
                    raise
        except Exception as e:
            logger.error(f"Failed to initialize bot (attempt {attempt+1}): {str(e)}")
            if attempt < max_attempts - 1:
                logger.info(f"Retrying in 10 seconds...")
                await asyncio.sleep(10)  # Longer sleep for deployment
            else:
                # In deployment, continue anyway after max attempts
                if 'REPL_SLUG' in os.environ:
                    logger.error("Max retries reached in deployment - continuing anyway")
                    yield MintosBot()  # Provide a new instance as last resort
                    return
                else:
                    raise
        finally:
            if bot and attempt == max_attempts - 1:
                logger.info("Cleaning up bot resources...")
                try:
                    await bot.cleanup()
                    logger.info("Bot cleanup completed")
                except Exception as e:
                    logger.error(f"Error during bot cleanup: {e}")

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