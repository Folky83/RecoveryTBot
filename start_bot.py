#!/usr/bin/env python3
"""
Startup script for the Mintos Telegram Bot
This script ensures proper startup and monitoring of the bot process.
"""

import os
import sys
import time
import logging
import subprocess
import signal
import atexit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("bot_startup")

# Global variables to track child processes
bot_process = None
monitor_process = None

def cleanup():
    """Clean up child processes on exit"""
    logger.info("Cleaning up processes...")
    if monitor_process:
        try:
            monitor_process.terminate()
            logger.info("Monitor process terminated")
        except Exception as e:
            logger.error(f"Error terminating monitor process: {e}")

def handle_signal(sig, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {sig}, cleaning up")
    cleanup()
    sys.exit(0)

def main():
    """Main startup function"""
    global monitor_process
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    atexit.register(cleanup)
    
    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    # Always force clean any previous processes or lock files
    logger.info("Force cleanup of any existing processes or lock files...")
    
    # Remove any stale lock files
    lock_files = ["bot.lock", "data/bot.lock"]
    for lock_file in lock_files:
        if os.path.exists(lock_file):
            try:
                os.unlink(lock_file)
                logger.info(f"Removed lock file: {lock_file}")
            except Exception as e:
                logger.error(f"Error removing lock file {lock_file}: {e}")
    
    # Stop existing processes
    try:
        # Try multiple times with different methods
        subprocess.run([sys.executable, "service_manager.py", "stop"], 
                      check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        time.sleep(3)
        
        # Kill any python processes related to the bot (more aggressive cleanup for deployment)
        try:
            subprocess.run(["pkill", "-f", "run.py"], 
                          check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info("Killed any remaining bot processes")
        except Exception as e:
            logger.error(f"Error during pkill: {e}")
        
        time.sleep(2)
    except Exception as e:
        logger.error(f"Error stopping existing processes: {e}")
    
    # Start the bot with service manager with retry
    max_retries = 3
    for attempt in range(max_retries):
        logger.info(f"Starting bot process (attempt {attempt+1}/{max_retries})...")
        try:
            result = subprocess.run(
                [sys.executable, "service_manager.py", "start"], 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                timeout=30  # Increased timeout for deployment
            )
            logger.info(f"Bot process started successfully: {result.stdout.decode() if result.stdout else 'No output'}")
            break
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start bot (attempt {attempt+1}): {e.stderr.decode() if e.stderr else str(e)}")
            if attempt < max_retries - 1:
                logger.info("Waiting before retry...")
                time.sleep(5)
            else:
                logger.error("All attempts to start bot failed")
                # Continue anyway in deployment
        except Exception as e:
            logger.error(f"Error starting bot (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                logger.info("Waiting before retry...")
                time.sleep(5)
            else:
                logger.error("All attempts to start bot failed")
                # Continue anyway in deployment
    
    # Start the monitor process with retry
    for attempt in range(max_retries):
        logger.info(f"Starting monitor process (attempt {attempt+1}/{max_retries})...")
        try:
            monitor_process = subprocess.Popen(
                [sys.executable, "service_manager.py", "monitor"],
                stdout=subprocess.PIPE,  # Changed to capture output for debugging
                stderr=subprocess.PIPE
            )
            logger.info(f"Monitor process started with PID {monitor_process.pid}")
            break
        except Exception as e:
            logger.error(f"Failed to start monitor process (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                logger.info("Waiting before retry...")
                time.sleep(5)
            else:
                logger.error("All attempts to start monitor process failed")
                # Continue anyway in deployment
    
    logger.info("Startup completed. Bot should be operational.")
    
    # Keep the main process running
    try:
        while True:
            # Check if monitor is still running
            if monitor_process.poll() is not None:
                logger.error("Monitor process terminated unexpectedly, restarting...")
                monitor_process = subprocess.Popen(
                    [sys.executable, "service_manager.py", "monitor"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info(f"Monitor process restarted with PID {monitor_process.pid}")
            
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        cleanup()

if __name__ == "__main__":
    main()