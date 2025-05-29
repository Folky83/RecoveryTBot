@echo off
echo Installing Mintos Telegram Bot...
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

echo Python found. Installing bot...
pip install --upgrade git+https://github.com/yourusername/mintos-telegram-bot.git

if errorlevel 1 (
    echo Installation failed. Please check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo Installation complete!
echo.
echo To configure your bot:
echo 1. Get a bot token from @BotFather on Telegram
echo 2. Create a config.txt file with: TELEGRAM_BOT_TOKEN=your_token_here
echo 3. Run: mintos-bot
echo.
echo Or set environment variable: set TELEGRAM_BOT_TOKEN=your_token_here
echo.
pause