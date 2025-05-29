@echo off
echo Installing Mintos Telegram Bot (No Git Required)...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    echo Please install Python 3.11 or newer from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Python found. Installing dependencies...

REM Install dependencies directly
pip install aiohttp>=3.11.12
pip install beautifulsoup4>=4.13.3
pip install feedparser>=6.0.11
pip install pandas>=2.2.3
pip install psutil>=6.1.1
pip install "python-telegram-bot[job-queue]==20.7"
pip install streamlit>=1.41.1
pip install trafilatura>=2.0.0
pip install twilio>=9.4.4
pip install watchdog>=6.0.0

if errorlevel 1 (
    echo Installation failed. Please check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo Dependencies installed successfully!
echo.
echo Next steps:
echo 1. Download the bot code from GitHub (as ZIP file, no Git needed)
echo 2. Extract the ZIP file to a folder
echo 3. Get a bot token from @BotFather on Telegram
echo 4. Create a config.txt file with: TELEGRAM_BOT_TOKEN=your_token_here
echo 5. Run: python run.py
echo.
echo Or visit: https://github.com/yourusername/mintos-telegram-bot
echo Click "Code" -> "Download ZIP" to get the files without Git
echo.
pause