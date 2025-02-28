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
    
    # First, stop any existing processes
    logger.info("Stopping any existing bot processes...")
    try:
        subprocess.run([sys.executable, "service_manager.py", "stop"], 
                      check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(2)
    except Exception as e:
        logger.error(f"Error stopping existing processes: {e}")
    
    # Start the bot with service manager
    logger.info("Starting bot process...")
    try:
        subprocess.run([sys.executable, "service_manager.py", "start"], 
                      check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start bot: {e.stderr.decode() if e.stderr else str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        sys.exit(1)
    
    # Start the monitor process
    logger.info("Starting monitor process...")
    try:
        monitor_process = subprocess.Popen(
            [sys.executable, "service_manager.py", "monitor"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info(f"Monitor process started with PID {monitor_process.pid}")
    except Exception as e:
        logger.error(f"Failed to start monitor process: {e}")
        sys.exit(1)
    
    logger.info("Startup completed successfully")
    
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