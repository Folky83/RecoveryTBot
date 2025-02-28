import os
import sys
import time
import logging
import subprocess
import psutil
import signal
import fcntl
import errno
from datetime import datetime

# Configuration
CHECK_INTERVAL = 300  # Check every 5 minutes
LOG_FILE = "data/watchdog.log"
LOCK_FILE = "watchdog.lock"
BOT_SCRIPT = "run.py"
MAX_RESTART_ATTEMPTS = 3
RESTART_COOLDOWN = 600  # 10 minutes between restart attempts

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("watchdog")

def acquire_lock():
    """Acquire lock file to ensure single instance"""
    try:
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, 'r') as f:
                    old_pid = int(f.read().strip())
                if not psutil.pid_exists(old_pid):
                    os.unlink(LOCK_FILE)
                    logger.info(f"Removed stale lock from PID {old_pid}")
            except (ValueError, IOError):
                os.unlink(LOCK_FILE)
                logger.info("Removed invalid lock file")

        lock_file = open(LOCK_FILE, 'w')
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        return lock_file
    except IOError as e:
        if e.errno == errno.EAGAIN:
            logger.error("Another watchdog instance is already running")
            sys.exit(1)
        raise

def is_bot_running():
    """Check if the bot process is running"""
    try:
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.cmdline()
                if cmdline and BOT_SCRIPT in ' '.join(cmdline) and 'bot_watchdog.py' not in ' '.join(cmdline):
                    logger.debug(f"Found bot process: PID {proc.pid}")
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    except Exception as e:
        logger.error(f"Error checking if bot is running: {e}")
        return False

def start_bot():
    """Start the bot process"""
    try:
        logger.info("Starting the bot process...")
        process = subprocess.Popen(
            [sys.executable, BOT_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True  # Detach process from parent
        )
        logger.info(f"Bot started with PID: {process.pid}")
        return True
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        return False

def check_cache_file():
    """Check the age of the updates cache file"""
    try:
        cache_file = "data/recovery_updates.json"
        if os.path.exists(cache_file):
            age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
            now = datetime.now()
            logger.info(f"Cache file age: {age_hours:.1f} hours (weekday: {now.weekday()})")
            
            # If cache is more than 24 hours old on a weekday (0-4 = Monday-Friday)
            if age_hours > 24 and now.weekday() < 5:
                logger.warning(f"Cache file is {age_hours:.1f} hours old on a weekday - may indicate missed updates")
                return False
        return True
    except Exception as e:
        logger.error(f"Error checking cache file: {e}")
        return True  # Continue normal operation on error

def main():
    """Main watchdog function"""
    logger.info("Starting watchdog service")
    
    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    # Acquire lock to ensure only one instance is running
    lock_file = acquire_lock()
    
    last_restart_time = 0
    restart_count = 0
    
    try:
        while True:
            try:
                # Check if bot is running
                if not is_bot_running():
                    current_time = time.time()
                    # Check cooldown period
                    if current_time - last_restart_time > RESTART_COOLDOWN:
                        logger.warning("Bot is not running, attempting to start it")
                        if start_bot():
                            last_restart_time = current_time
                            restart_count = 1
                        else:
                            restart_count += 1
                            if restart_count > MAX_RESTART_ATTEMPTS:
                                logger.error(f"Failed to start bot after {restart_count} attempts, will try again later")
                                restart_count = 0
                                time.sleep(RESTART_COOLDOWN)  # Wait longer before trying again
                    else:
                        logger.info("In cooldown period, will try to restart later")
                else:
                    # Bot is running, reset counter
                    restart_count = 0
                    logger.info("Bot is running correctly")
                    
                    # Check cache file age
                    check_cache_file()
                
                # Wait before next check
                time.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")
                time.sleep(CHECK_INTERVAL)
    finally:
        # Clean up lock file
        try:
            if lock_file:
                lock_file.close()
            if os.path.exists(LOCK_FILE):
                os.unlink(LOCK_FILE)
        except Exception as e:
            logger.error(f"Error cleaning up: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Watchdog stopped by user")
    except Exception as e:
        logger.error(f"Watchdog failed: {e}")
