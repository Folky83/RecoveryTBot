#!/usr/bin/env python3
"""
Service Manager for Telegram Bot
Provides a reliable way to manage the bot process, with
automatic restart and status monitoring.
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
import psutil

# Configuration
SERVICE_NAME = "mintos_telegram_bot"
PID_FILE = f"data/{SERVICE_NAME}.pid"
LOG_FILE = f"data/{SERVICE_NAME}_service.log"
BOT_SCRIPT = "run.py"
MAX_RESTART_ATTEMPTS = 5
RESTART_DELAY = 10
STATUS_CHECK_INTERVAL = 30

# Setup logging
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

def get_pid():
    """Get the PID of the running bot process"""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            return pid
        return None
    except (ValueError, IOError) as e:
        logger.error(f"Error reading PID file: {e}")
        return None

def save_pid(pid):
    """Save PID to file"""
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(pid))
        logger.info(f"Saved PID {pid} to {PID_FILE}")
    except IOError as e:
        logger.error(f"Error saving PID to file: {e}")

def is_process_running(pid):
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

def check_bot_status():
    """Check the status of the bot process"""
    pid = get_pid()
    if pid is None:
        logger.warning("No PID file found")
        return False

    if not is_process_running(pid):
        logger.warning(f"Process with PID {pid} is not running")
        return False

    # Check if it's a Python process running the bot script
    try:
        process = psutil.Process(pid)
        cmdline = process.cmdline()
        if not (sys.executable in cmdline[0] and BOT_SCRIPT in ' '.join(cmdline)):
            logger.warning(f"Process with PID {pid} is not the bot process. Command: {' '.join(cmdline)}")
            return False
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.error(f"Error accessing process info: {e}")
        return False

def start_bot():
    """Start the bot process"""
    try:
        # Clean up any old processes
        stop_bot()
        
        logger.info("Starting the bot process...")
        # Redirect output to log files
        stdout_file = open("data/bot_stdout.log", "a")
        stderr_file = open("data/bot_stderr.log", "a")
        
        # Start the process
        process = subprocess.Popen(
            [sys.executable, BOT_SCRIPT],
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True  # Detach from parent
        )
        
        # Save PID
        save_pid(process.pid)
        logger.info(f"Bot started with PID: {process.pid}")
        
        # Give it a moment to initialize
        time.sleep(5)
        
        # Verify it's still running (didn't crash immediately)
        if not is_process_running(process.pid):
            logger.error("Bot process failed to start properly")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        return False

def stop_bot():
    """Stop the bot process"""
    pid = get_pid()
    if pid is None:
        logger.info("No bot process is running (no PID file)")
        return True
    
    try:
        logger.info(f"Stopping bot process with PID {pid}...")
        if is_process_running(pid):
            process = psutil.Process(pid)
            process.terminate()
            
            # Wait for process to terminate
            for _ in range(10):
                if not is_process_running(pid):
                    break
                time.sleep(0.5)
                
            # Force kill if still running
            if is_process_running(pid):
                logger.warning(f"Process did not terminate gracefully, forcing kill")
                process.kill()
        
        # Remove PID file
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

def restart_bot():
    """Restart the bot process"""
    logger.info("Restarting bot process...")
    stop_bot()
    time.sleep(2)
    return start_bot()

def status_monitor():
    """Monitor the bot status and restart if necessary"""
    logger.info("Starting status monitor...")
    restart_attempts = 0
    
    while True:
        try:
            if not check_bot_status():
                if restart_attempts < MAX_RESTART_ATTEMPTS:
                    logger.warning(f"Bot is not running properly, attempting restart ({restart_attempts + 1}/{MAX_RESTART_ATTEMPTS})")
                    if restart_bot():
                        restart_attempts = 0
                    else:
                        restart_attempts += 1
                else:
                    logger.error(f"Failed to restart bot after {MAX_RESTART_ATTEMPTS} attempts")
                    # Reset counter but wait longer
                    restart_attempts = 0
                    time.sleep(RESTART_DELAY * 10)
            else:
                restart_attempts = 0
                logger.info("Bot is running correctly")
                
            # Check cache file age
            check_cache_file()
                
            # Wait before next check
            time.sleep(STATUS_CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"Error in status monitor: {e}")
            time.sleep(STATUS_CHECK_INTERVAL)

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
                
                # Force a refresh if we're in the correct time window
                hour = now.hour
                if 9 <= hour <= 18:  # Business hours (9 AM to 6 PM)
                    if restart_bot():
                        logger.info("Forced bot restart to refresh data")
    except Exception as e:
        logger.error(f"Error checking cache file: {e}")

def create_setup_file():
    """Create or update setup configuration file"""
    try:
        config = {
            "service_name": SERVICE_NAME,
            "auto_start": True,
            "last_start": datetime.now().isoformat(),
            "restart_count": 0,
            "enabled": True
        }
        
        with open("data/service_config.json", "w") as f:
            json.dump(config, f, indent=2)
        logger.info("Created/updated service configuration file")
    except Exception as e:
        logger.error(f"Error creating setup file: {e}")

def load_config():
    """Load service configuration"""
    try:
        if os.path.exists("data/service_config.json"):
            with open("data/service_config.json", "r") as f:
                return json.load(f)
        return None
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None

def handle_signal(sig, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {sig}, stopping service")
    stop_bot()
    sys.exit(0)

def main():
    """Main entry point"""
    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    parser = argparse.ArgumentParser(description="Mintos Telegram Bot Service Manager")
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status', 'monitor'], 
                        help='Action to perform')
    
    args = parser.parse_args()
    
    if args.action == 'start':
        if check_bot_status():
            logger.info("Bot is already running")
        else:
            start_bot()
            create_setup_file()
    elif args.action == 'stop':
        stop_bot()
    elif args.action == 'restart':
        restart_bot()
    elif args.action == 'status':
        if check_bot_status():
            print("Bot is running")
            sys.exit(0)
        else:
            print("Bot is not running")
            sys.exit(1)
    elif args.action == 'monitor':
        status_monitor()

if __name__ == "__main__":
    main()