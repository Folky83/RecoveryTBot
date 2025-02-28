#!/usr/bin/env python3
"""
Service Manager for Telegram Bot
Provides a reliable way to manage the bot process, with
automatic restart, status monitoring, and watchdog functionality.
"""
import os
import sys
import time
import signal
import logging
import argparse
import subprocess
import fcntl
import errno
import json
from datetime import datetime
from typing import Optional, TextIO
import psutil

# Configuration
SERVICE_NAME = "mintos_telegram_bot"
PID_FILE = f"data/{SERVICE_NAME}.pid"
LOG_FILE = f"data/{SERVICE_NAME}_service.log"
LOCK_FILE = f"data/{SERVICE_NAME}.lock"
BOT_SCRIPT = "run.py"

# Process management settings
MAX_RESTART_ATTEMPTS = 5
RESTART_DELAY = 10
STATUS_CHECK_INTERVAL = 30
CACHE_CHECK_INTERVAL = 300  # 5 minutes

# Setup logging with rotating file handler
os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("service_manager")

class ProcessLock:
    """Context manager for process locking"""
    def __init__(self, lock_file: str):
        self.lock_file = lock_file
        self.lock_fd: Optional[TextIO] = None

    def __enter__(self) -> 'ProcessLock':
        try:
            if os.path.exists(self.lock_file):
                try:
                    with open(self.lock_file, 'r') as f:
                        old_pid = int(f.read().strip())
                    if not psutil.pid_exists(old_pid):
                        os.unlink(self.lock_file)
                        logger.info(f"Removed stale lock from PID {old_pid}")
                except (ValueError, IOError):
                    os.unlink(self.lock_file)
                    logger.info("Removed invalid lock file")

            self.lock_fd = open(self.lock_file, 'w')
            fcntl.lockf(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            return self
        except IOError as e:
            if e.errno == errno.EAGAIN:
                logger.error("Another instance is already running")
                sys.exit(1)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.lock_fd:
                self.lock_fd.close()
            if os.path.exists(self.lock_file):
                os.unlink(self.lock_file)
        except Exception as e:
            logger.error(f"Error cleaning up lock: {e}")

class ServiceManager:
    """Manages the Telegram bot service"""
    def __init__(self):
        self.restart_attempts = 0
        self.last_restart_time = 0

    def get_pid(self) -> Optional[int]:
        """Get the PID of the running bot process"""
        try:
            if os.path.exists(PID_FILE):
                with open(PID_FILE, 'r') as f:
                    return int(f.read().strip())
        except (ValueError, IOError) as e:
            logger.error(f"Error reading PID file: {e}")
        return None

    def save_pid(self, pid: int) -> None:
        """Save PID to file"""
        try:
            with open(PID_FILE, 'w') as f:
                f.write(str(pid))
            logger.info(f"Saved PID {pid} to {PID_FILE}")
        except IOError as e:
            logger.error(f"Error saving PID to file: {e}")

    def is_process_running(self, pid: Optional[int]) -> bool:
        """Check if process with given PID is running"""
        try:
            if pid is None:
                return False
            process = psutil.Process(pid)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
        except Exception as e:
            logger.error(f"Error checking process status: {e}")
            return False

    def check_bot_status(self) -> bool:
        """Check the status of the bot process"""
        pid = self.get_pid()
        if pid is None:
            logger.warning("No PID file found")
            return False

        if not self.is_process_running(pid):
            logger.warning(f"Process with PID {pid} is not running")
            return False

        try:
            process = psutil.Process(pid)
            cmdline = process.cmdline()
            if not (sys.executable in cmdline[0] and BOT_SCRIPT in ' '.join(cmdline)):
                logger.warning(f"Process with PID {pid} is not the bot process")
                return False
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.error(f"Error accessing process info: {e}")
            return False

    def start_bot(self) -> bool:
        """Start the bot process"""
        try:
            # Clean up any old processes
            self.stop_bot()

            logger.info("Starting the bot process...")
            stdout_file = open("data/bot_stdout.log", "a")
            stderr_file = open("data/bot_stderr.log", "a")

            process = subprocess.Popen(
                [sys.executable, BOT_SCRIPT],
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True
            )

            self.save_pid(process.pid)
            logger.info(f"Bot started with PID: {process.pid}")

            # Give it a moment to initialize
            time.sleep(5)

            if not self.is_process_running(process.pid):
                logger.error("Bot process failed to start properly")
                return False

            return True
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            return False

    def stop_bot(self) -> bool:
        """Stop the bot process"""
        pid = self.get_pid()
        if pid is None:
            logger.info("No bot process is running (no PID file)")
            return True

        try:
            logger.info(f"Stopping bot process with PID {pid}...")
            if self.is_process_running(pid):
                process = psutil.Process(pid)
                process.terminate()

                # Wait for process to terminate
                for _ in range(10):
                    if not self.is_process_running(pid):
                        break
                    time.sleep(0.5)

                # Force kill if still running
                if self.is_process_running(pid):
                    logger.warning("Process did not terminate gracefully, forcing kill")
                    process.kill()

            if os.path.exists(PID_FILE):
                os.unlink(PID_FILE)

            logger.info("Bot process stopped successfully")
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            logger.info(f"Process with PID {pid} already terminated")
            if os.path.exists(PID_FILE):
                os.unlink(PID_FILE)
            return True
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
            return False

    def check_cache_file(self) -> None:
        """Check the age of the updates cache file"""
        try:
            cache_file = "data/recovery_updates.json"
            if os.path.exists(cache_file):
                age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
                now = datetime.now()
                logger.info(f"Cache file age: {age_hours:.1f} hours (weekday: {now.weekday()})")

                # If cache is more than 24 hours old on a weekday (0-4 = Monday-Friday)
                if age_hours > 24 and now.weekday() < 5:
                    logger.warning(f"Cache file is {age_hours:.1f} hours old on a weekday")

                    # Force a refresh if we're in the correct time window
                    hour = now.hour
                    if 9 <= hour <= 18:  # Business hours (9 AM to 6 PM)
                        if self.restart_bot():
                            logger.info("Forced bot restart to refresh data")
        except Exception as e:
            logger.error(f"Error checking cache file: {e}")

    def restart_bot(self) -> bool:
        """Restart the bot process"""
        logger.info("Restarting bot process...")
        self.stop_bot()
        time.sleep(2)
        return self.start_bot()

    def monitor(self) -> None:
        """Monitor the bot status and restart if necessary"""
        logger.info("Starting status monitor...")
        last_cache_check = 0

        while True:
            try:
                current_time = time.time()

                # Check bot status
                if not self.check_bot_status():
                    if current_time - self.last_restart_time > RESTART_DELAY:
                        logger.warning(f"Bot is not running properly, attempting restart ({self.restart_attempts + 1}/{MAX_RESTART_ATTEMPTS})")
                        if self.restart_bot():
                            self.restart_attempts = 0
                            self.last_restart_time = current_time
                        else:
                            self.restart_attempts += 1
                            if self.restart_attempts >= MAX_RESTART_ATTEMPTS:
                                logger.error(f"Failed to restart bot after {MAX_RESTART_ATTEMPTS} attempts")
                                self.restart_attempts = 0
                                time.sleep(RESTART_DELAY * 10)
                    else:
                        logger.info("In restart delay period")
                else:
                    self.restart_attempts = 0
                    logger.info("Bot is running correctly")

                # Periodic cache check
                if current_time - last_cache_check >= CACHE_CHECK_INTERVAL:
                    self.check_cache_file()
                    last_cache_check = current_time

                time.sleep(STATUS_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                time.sleep(STATUS_CHECK_INTERVAL)

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Mintos Telegram Bot Service Manager")
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status', 'monitor'],
                      help='Action to perform')

    args = parser.parse_args()

    # Use process lock to ensure single instance
    with ProcessLock(LOCK_FILE):
        service = ServiceManager()

        if args.action == 'start':
            if service.check_bot_status():
                logger.info("Bot is already running")
            else:
                service.start_bot()
        elif args.action == 'stop':
            service.stop_bot()
        elif args.action == 'restart':
            service.restart_bot()
        elif args.action == 'status':
            if service.check_bot_status():
                print("Bot is running")
                sys.exit(0)
            else:
                print("Bot is not running")
                sys.exit(1)
        elif args.action == 'monitor':
            service.monitor()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Service manager stopped by user")
    except Exception as e:
        logger.error(f"Service manager failed: {e}")
        sys.exit(1)