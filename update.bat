@echo off
echo Updating Mintos Telegram Bot...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    pause
    exit /b 1
)

echo Updating from Git repository...
python -m pip install --user --upgrade --force-reinstall git+https://github.com/Folky83/RecoveryTBot.git

if errorlevel 1 (
    echo Update failed. Please check your internet connection.
    echo Alternative: Download new ZIP from GitHub and replace files manually.
    pause
    exit /b 1
)

echo.
echo Update completed successfully!
echo.
echo Your bot is now up to date.
echo Run: python -m mintos_bot.run
echo.
pause