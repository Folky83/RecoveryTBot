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
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc_with_connections = Process(proc.pid)
                    for conn in proc_with_connections.connections():
                        if conn.laddr.port == port:
                            self.logger.info(f"Killing process {proc.pid} using port {port}")
                            proc.kill()
                            await asyncio.sleep(PROCESS_KILL_WAIT)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            self.logger.error(f"Error killing port process: {e}")

    async def cleanup_processes(self) -> None:
        """Clean up all related processes"""
        try:
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
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        proc_with_connections = Process(proc.pid)
                        for conn in proc_with_connections.connections():
                            if conn.laddr.port == STREAMLIT_PORT and conn.status == 'LISTEN':
                                self.logger.info(f"Streamlit running on port {STREAMLIT_PORT}")
                                await asyncio.sleep(2)
                                return
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except Exception as e:
                self.logger.error(f"Error checking Streamlit status: {e}")

            await asyncio.sleep(1)

        raise TimeoutError("Streamlit failed to start within timeout")

    async def cleanup(self) -> None:
        """Cleanup all resources"""
        try:
            self.logger.info("Starting cleanup process...")
            await self.cleanup_processes()

            if self.lock_file:
                try:
                    os.unlink(LOCK_FILE)
                    if hasattr(self.lock_file, 'close'):
                        self.lock_file.close()
                except Exception:
                    pass

            self.logger.info("Cleanup completed")
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")

@contextlib.asynccontextmanager
async def managed_bot():
    """Context manager for bot lifecycle"""
    from bot.telegram_bot import MintosBot
    bot = None
    try:
        bot = MintosBot()
        yield bot
    finally:
        if bot:
            await bot.cleanup()

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
            "--server.port", "80"
        ])

        # Wait for Streamlit and start bot
        await process_manager.wait_for_streamlit()
        logger.info("Streamlit started successfully")

        async with managed_bot() as bot:
            await bot.cleanup()  # Ensure clean state
            await asyncio.sleep(2)
            bot_task = asyncio.create_task(bot.run())
            await bot_task

    except Exception as e:
        logger.error(f"Application error: {e}")
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
    except Exception:
        pass
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(main())