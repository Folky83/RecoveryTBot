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
echo Downloading and installing bot...
echo This may take a few minutes...
echo.

REM Install dependencies first
echo Installing Python packages...
python -m pip install --user aiohttp>=3.11.12
if errorlevel 1 goto install_error
python -m pip install --user beautifulsoup4>=4.13.3
if errorlevel 1 goto install_error
python -m pip install --user feedparser>=6.0.11
if errorlevel 1 goto install_error
python -m pip install --user pandas>=2.2.3
if errorlevel 1 goto install_error
python -m pip install --user psutil>=6.1.1
if errorlevel 1 goto install_error
python -m pip install --user "python-telegram-bot[job-queue]==20.7"
if errorlevel 1 goto install_error
python -m pip install --user streamlit>=1.41.1
if errorlevel 1 goto install_error
python -m pip install --user trafilatura>=2.0.0
if errorlevel 1 goto install_error
python -m pip install --user twilio>=9.4.4
if errorlevel 1 goto install_error
python -m pip install --user watchdog>=6.0.0
if errorlevel 1 goto install_error

echo.
echo Dependencies installed successfully!
echo.
echo Next steps:
echo 1. Download the bot files from: https://github.com/Folky83/RecoveryTBot
echo 2. Click "Code" -> "Download ZIP" 
echo 3. Extract to a folder
echo 4. Get bot token from @BotFather on Telegram
echo 5. Create config.txt with: TELEGRAM_BOT_TOKEN=your_token_here
echo 6. Run: python run.py
echo 7. Access dashboard at: http://localhost:5000
goto end

:install_error
echo.
echo Installation failed. Please check your internet connection.
echo You may need to run this as administrator.
goto end

:git_install
echo Installing from Git repository...
python -m pip install --user --upgrade git+https://github.com/Folky83/RecoveryTBot.git
if errorlevel 1 (
    echo Git installation failed. Try option 1 instead.
    pause
    exit /b 1
)
echo.
echo Git installation successful!
echo.
echo To run the bot:
echo 1. Get bot token from @BotFather on Telegram
echo 2. Create config.txt with: TELEGRAM_BOT_TOKEN=your_token_here
echo 3. Run: python -m mintos_bot.run
echo 4. Access dashboard at: http://localhost:5000
echo.
echo To update later, just run: python -m pip install --user --upgrade git+https://github.com/Folky83/RecoveryTBot.git
goto end

:deps_only
echo Installing dependencies only...
pip install aiohttp>=3.11.12 beautifulsoup4>=4.13.3 feedparser>=6.0.11
pip install pandas>=2.2.3 psutil>=6.1.1 "python-telegram-bot[job-queue]==20.7"
pip install streamlit>=1.41.1 trafilatura>=2.0.0 twilio>=9.4.4 watchdog>=6.0.0
echo Dependencies installed. Run: python run.py

:end
echo.
echo Setup complete!
pause