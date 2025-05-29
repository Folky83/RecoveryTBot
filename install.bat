@echo off
echo Mintos Telegram Bot Installer
echo =============================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    echo Please install Python 3.11 or newer from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Python found. Choose installation method:
echo.
echo 1. Simple Install (Downloads ZIP, no Git required)
echo 2. Git Install (Requires Git to be installed) 
echo 3. Dependencies Only (If you already have the files)
echo.
set /p choice="Enter choice (1-3): "

if "%choice%"=="1" goto simple_install
if "%choice%"=="2" goto git_install
if "%choice%"=="3" goto deps_only
echo Invalid choice. Exiting.
pause
exit /b 1

:simple_install
echo Running simple installation...
python simple_install.py
goto end

:git_install
echo Installing from Git repository...
pip install --upgrade git+https://github.com/Folky83/RecoveryTBot.git
if errorlevel 1 (
    echo Git installation failed. Try option 1 instead.
    pause
    exit /b 1
)
echo Git installation successful!
echo Run: mintos-bot
goto end

:deps_only
echo Installing dependencies only...
pip install "aiohttp>=3.8.0" "beautifulsoup4>=4.11.0" "feedparser>=6.0.8"
pip install "pandas>=1.5.0" "psutil>=5.9.0" "python-telegram-bot[job-queue]==20.7"
pip install "streamlit>=1.25.0,<1.28.0" "trafilatura>=1.6.0" "twilio>=8.5.0" "watchdog>=2.1.0"
echo Dependencies installed. Run: python run.py

:end
echo.
echo Setup complete!
pause