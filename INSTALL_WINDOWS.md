# Easy Windows Installation Guide

## Step 1: Install Python
1. Download Python 3.11 or newer from [python.org](https://python.org)
2. **Important**: Check "Add Python to PATH" during installation
3. Restart your command prompt after installation

## Step 2: Install the Bot

### Option A: One-Click Install (Recommended)
1. Download `install.bat` from this repository
2. Double-click `install.bat` to run it
3. Follow the prompts

### Option B: Manual Install
Open Command Prompt and run:
```bash
pip install --upgrade git+https://github.com/yourusername/mintos-telegram-bot.git
```

## Step 3: Get Your Telegram Bot Token
1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow instructions to create your bot
4. Copy the token (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

## Step 4: Configure Your Token

### Easy Method - Create Config File
1. Create a file called `config.txt` in any folder
2. Add this line: `TELEGRAM_BOT_TOKEN=your_actual_token_here`
3. Save the file

### Alternative Method - Environment Variable
Open Command Prompt and run:
```bash
set TELEGRAM_BOT_TOKEN=your_actual_token_here
```

## Step 5: Start the Bot
Open Command Prompt and run:
```bash
mintos-bot
```

The bot will start and the dashboard will be available at: http://localhost:5000

## Troubleshooting

**"Python is not recognized"**
- Reinstall Python and check "Add Python to PATH"
- Restart your computer

**"pip is not recognized"**
- Python installation issue, reinstall Python

**Bot doesn't start**
- Check your token is correct
- Make sure you have internet connection
- Try running: `python -m mintos_bot.run`

**Dashboard won't open**
- Wait 30 seconds for startup
- Check if port 5000 is in use
- Try restarting the bot

## Running as a Service
To run the bot continuously:
1. Create a batch file with the mintos-bot command
2. Use Windows Task Scheduler to run it at startup
3. Or use a service manager like NSSM

## Need Help?
Create an issue on GitHub with your error message and we'll help you get it working.