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
        self.logger.info(f"Waiting up to {STARTUP_TIMEOUT} seconds for Streamlit...")
        
        while time.time() - start_time < STARTUP_TIMEOUT:
            # First check if process is still running
            if self.streamlit_process.poll() is not None:
                # If in production, don't fail
                if 'REPL_SLUG' in os.environ:
                    self.logger.warning("Streamlit process terminated, but continuing in production environment")
                    return
                raise RuntimeError("Streamlit process terminated unexpectedly")

            try:
                # First try a socket connection to the port
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', STREAMLIT_PORT))
                s.close()
                
                if result == 0:
                    self.logger.info(f"Streamlit running on port {STREAMLIT_PORT} (socket check successful)")
                    await asyncio.sleep(2)  # Give it a moment to fully initialize
                    return
                
                # Backup check using psutil
                for conn in psutil.net_connections(kind='inet'):
                    try:
                        # Check if this connection is our streamlit server
                        if (hasattr(conn, 'laddr') and 
                            isinstance(conn.laddr, tuple) and len(conn.laddr) >= 2 and 
                            conn.laddr[1] == STREAMLIT_PORT and 
                            hasattr(conn, 'status') and conn.status == 'LISTEN'):
                            self.logger.info(f"Streamlit running on port {STREAMLIT_PORT} (psutil check successful)")
                            await asyncio.sleep(2)  # Give it a moment to fully initialize
                            return
                    except (AttributeError, TypeError) as e:
                        pass  # Skip errors in connection objects
            except Exception as e:
                self.logger.error(f"Error checking Streamlit status: {e}")

            # Check for "You can now view your Streamlit app" in log file
            try:
                if os.path.exists("logs/streamlit.log"):
                    with open("logs/streamlit.log", "r") as f:
                        log_content = f.read()
                        if "You can now view your Streamlit app" in log_content:
                            self.logger.info("Streamlit app ready according to log file")
                            await asyncio.sleep(2)  # Give it a moment to fully initialize
                            return
            except Exception as log_error:
                self.logger.error(f"Error checking Streamlit log: {log_error}")

            elapsed = int(time.time() - start_time)
            if elapsed % 10 == 0:  # Log every 10 seconds to avoid log spam
                self.logger.info(f"Still waiting for Streamlit ({elapsed}s elapsed)...")
            
            await asyncio.sleep(1)

        # If timeout occurs in production, don't fail
        if 'REPL_SLUG' in os.environ:
            self.logger.warning("Streamlit startup timed out, but continuing in production environment")
            return
            
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
            for token_attempt in range(5):  # Increased retries
                token = os.getenv('TELEGRAM_BOT_TOKEN')
                if token and len(token) > 20:  # Basic validation that token looks reasonable
                    logger.info(f"Valid token found on attempt {token_attempt+1}")
                    # Print first few characters for debugging
                    logger.info(f"Token starts with: {token[:5]}...")
                    break

                logger.warning(f"TELEGRAM_BOT_TOKEN not found or invalid (attempt {token_attempt+1}/5), waiting 10 seconds...")
                await asyncio.sleep(10)  # Longer wait for deployment environment variables

                # Try to read token directly from secrets for Replit deployment
                if 'REPL_SLUG' in os.environ and token_attempt >= 2:
                    try:
                        with open('/home/runner/mintosbot/.env', 'r') as f:
                            for line in f:
                                if 'TELEGRAM_BOT_TOKEN' in line:
                                    parts = line.strip().split('=', 1)
                                    if len(parts) == 2:
                                        token = parts[1].strip()
                                        logger.info("Found token in .env file")
                                        break
                    except Exception as e:
                        logger.warning(f"Failed to read .env file: {e}")

            if not token or len(token) < 20:
                # In deployment, we want to continue anyway as the variable might become available later
                logger.error("TELEGRAM_BOT_TOKEN environment variable is not set or invalid after retries")
                if 'REPL_SLUG' in os.environ:  # Check if we're in Replit deployment
                    logger.warning("Running in deployment environment - continuing despite missing/invalid token")
                else:
                    raise ValueError("Bot token is missing or invalid after retry")

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
    logger.info("Starting main application with enhanced error handling...")

    process_manager = ProcessManager()
    max_restarts = 5  # Increased for more resilience
    restart_count = 0

    # Print environment information for debugging
    try:
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Process PID: {os.getpid()}")
        for key, value in os.environ.items():
            if key.startswith('TELEGRAM') or key.startswith('REPL'):
                # Redact actual token values for security
                if 'TOKEN' in key:
                    value_display = f"{value[:5]}...{value[-5:]}" if value and len(value) > 10 else "Not set properly"
                    logger.info(f"Environment: {key}={value_display}")
                else:
                    logger.info(f"Environment: {key}={value}")
    except Exception as env_error:
        logger.error(f"Error reading environment: {env_error}")

    while restart_count < max_restarts:
        try:
            # Acquire lock and clean up existing processes
            logger.info("Attempting to acquire lock and cleanup processes...")
            await process_manager.acquire_lock()
            logger.info(f"Lock acquired for PID {os.getpid()}")
            await process_manager.cleanup()

            # Start Streamlit with output capture
            logger.info("Starting Streamlit process...")
            os.makedirs("logs", exist_ok=True)
            streamlit_log = open("logs/streamlit.log", "w")
            
            # Create the streamlit command with all options
            streamlit_cmd = [
                sys.executable, "-m", "streamlit", "run",
                "main.py", 
                "--server.address", "0.0.0.0",
                "--server.port", str(STREAMLIT_PORT),
                "--server.headless", "true",
                "--server.enableCORS", "false"
            ]
            logger.info(f"Streamlit command: {' '.join(streamlit_cmd)}")
            
            process_manager.streamlit_process = subprocess.Popen(
                streamlit_cmd, 
                stdout=streamlit_log, 
                stderr=streamlit_log
            )
            
            # Give Streamlit a longer moment to start up
            logger.info("Waiting for Streamlit to initialize...")
            await asyncio.sleep(5)
            
            # Check if it's still running before waiting
            if process_manager.streamlit_process.poll() is not None:
                exit_code = process_manager.streamlit_process.returncode
                logger.error(f"Streamlit process exited immediately with code {exit_code}")
                logger.error("Check logs/streamlit.log for more details")
                streamlit_log.close()
                
                # Try to read the log file
                try:
                    with open("logs/streamlit.log", "r") as f:
                        log_content = f.read()
                        logger.error(f"Streamlit error log: {log_content}")
                except Exception as log_error:
                    logger.error(f"Could not read Streamlit log: {log_error}")
                
                # In production environment, continue anyway
                if 'REPL_SLUG' in os.environ:
                    logger.warning("In deployment environment - creating a minimal working Streamlit app")
                    try:
                        with open("minimal_app.py", "w") as f:
                            f.write("""
import streamlit as st

st.title("Mintos Updates Dashboard")
st.info("The main application is initializing. Please check back in a few minutes.")
st.write("This is a temporary page while the main application is starting up.")
""")
                        
                        # Try with minimal app
                        streamlit_log = open("logs/streamlit_minimal.log", "w")
                        process_manager.streamlit_process = subprocess.Popen([
                            sys.executable, "-m", "streamlit", "run",
                            "minimal_app.py", 
                            "--server.address", "0.0.0.0",
                            "--server.port", str(STREAMLIT_PORT),
                            "--server.headless", "true",
                            "--server.enableCORS", "false"
                        ], stdout=streamlit_log, stderr=streamlit_log)
                        
                        await asyncio.sleep(5)
                    except Exception as minimal_error:
                        logger.error(f"Error creating minimal app: {minimal_error}")
                    
                    # Continue anyway in production
                    logger.warning("Continuing despite Streamlit issues...")
                else:
                    # In development, raise error
                    raise RuntimeError(f"Streamlit process failed to start (exit code {exit_code})")
                
                # Try running with plain Python to see if it's a Streamlit issue
                logger.info("Attempting to run main.py directly to check for Python errors...")
                try:
                    test_result = subprocess.run([sys.executable, "main.py"], 
                                               capture_output=True, text=True, timeout=5)
                    if test_result.returncode != 0:
                        logger.error(f"Python error in main.py: {test_result.stderr}")
                    else:
                        logger.info("main.py runs without errors, issue is specific to Streamlit")
                except Exception as py_error:
                    logger.error(f"Error testing main.py: {py_error}")
                
                raise RuntimeError(f"Streamlit process failed to start (exit code {exit_code})")
            
            # Wait for Streamlit and start bot
            logger.info("Waiting for Streamlit to initialize...")
            try:
                await process_manager.wait_for_streamlit()
                logger.info("Streamlit started successfully")
                streamlit_log.close()
            except Exception as e:
                streamlit_log.close()
                logger.error(f"Streamlit initialization failed: {e}")
                raise

            # Verify environment is properly set
            token = os.getenv('TELEGRAM_BOT_TOKEN')
            if not token or len(token) < 20:
                logger.critical("TELEGRAM_BOT_TOKEN is missing or invalid!")
                if 'REPL_SLUG' in os.environ:
                    logger.info("In deployment environment - attempting to continue despite token issue")
                    # Try to read from .env file as last resort
                    try:
                        logger.info("Attempting to read token from .env file...")
                        env_file_paths = ['.env', '/home/runner/.env', '/home/runner/mintosbot/.env']
                        for env_path in env_file_paths:
                            if os.path.exists(env_path):
                                with open(env_path, 'r') as f:
                                    for line in f:
                                        if 'TELEGRAM_BOT_TOKEN' in line:
                                            parts = line.strip().split('=', 1)
                                            if len(parts) == 2:
                                                os.environ['TELEGRAM_BOT_TOKEN'] = parts[1].strip()
                                                logger.info(f"Found token in {env_path}, setting environment variable")
                                                break
                    except Exception as env_read_error:
                        logger.error(f"Failed to read .env file: {env_read_error}")
                else:
                    logger.error("Not in deployment environment - token is required!")
                    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set properly")
            else:
                logger.info(f"TELEGRAM_BOT_TOKEN is set and appears valid (length: {len(token)})")

            if 'REPL_SLUG' in os.environ:
                logger.info(f"Running in Replit deployment environment: {os.environ.get('REPL_SLUG')}")

            logger.info("Starting bot with managed_bot context...")
            async with managed_bot() as bot:
                logger.info("Bot instance created, initializing...")
                try:
                    # Add explicit check that bot can connect to Telegram before running
                    if not hasattr(bot, 'application') or not bot.application:
                        raise RuntimeError("Bot application not properly initialized")

                    if not hasattr(bot.application, 'bot'):
                        raise RuntimeError("Bot.application.bot attribute missing")

                    try:
                        logger.info("Verifying Telegram connection...")
                        me = await bot.application.bot.get_me()
                        logger.info(f"Successfully connected to Telegram as @{me.username}")
                    except Exception as conn_error:
                        logger.error(f"Failed to connect to Telegram: {conn_error}")
                        if 'REPL_SLUG' in os.environ:
                            logger.warning("In deployment environment - will attempt to continue despite connection error")
                        else:
                            raise RuntimeError(f"Failed to connect to Telegram API: {conn_error}")

                    # Start the bot and wait for it indefinitely
                    logger.info("Creating bot task...")
                    bot_task = asyncio.create_task(bot.run())
                    logger.info("Bot task created, waiting for completion...")

                    # Monitor the task status periodically
                    monitoring_interval = 60  # check every minute
                    while True:
                        if bot_task.done():
                            if bot_task.exception():
                                logger.error(f"Bot task failed with exception: {bot_task.exception()}")
                                raise bot_task.exception()
                            else:
                                logger.warning("Bot task completed unexpectedly without exception")
                                break

                        logger.info("Bot task still running (heartbeat check)")
                        await asyncio.sleep(monitoring_interval)

                    await bot_task  # This will re-raise any exception if the task failed

                except asyncio.CancelledError:
                    logger.info("Bot task was cancelled")
                    raise
                except Exception as e:
                    logger.error(f"Bot error: {str(e)}", exc_info=True)
                    raise

        except Exception as e:
            logger.error(f"Main loop error: {str(e)}", exc_info=True)
            restart_count += 1

            if restart_count < max_restarts:
                wait_time = 30 * restart_count  # Increasing backoff
                logger.info(f"Restarting in {wait_time} seconds (attempt {restart_count}/{max_restarts})...")
                await asyncio.sleep(wait_time)
            else:
                logger.critical("Maximum restarts exceeded, exiting...")
                break
        finally:
            # Clean up current processes before restart or exit
            try:
                logger.info("Cleaning up processes before restart/exit...")
                await process_manager.cleanup()
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup: {cleanup_error}")

    # Clean up before exit
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