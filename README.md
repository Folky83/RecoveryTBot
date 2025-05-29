# Mintos Telegram Bot

A sophisticated Telegram bot and dashboard for monitoring Mintos lending platform investments with advanced document scraping and intelligent data extraction capabilities.

## Features

- **Real-time Monitoring**: Track recovery updates and campaigns from Mintos
- **Document Scraping**: Automatically extract presentation, financial, and loan agreement PDFs
- **Telegram Notifications**: Get instant alerts for new updates
- **Web Dashboard**: View all updates in a user-friendly interface
- **Smart Filtering**: Filter updates by company and date
- **RSS Integration**: Monitor news and announcements

## Quick Installation for Windows

### Option 1: Install from Git (Recommended)

1. **Install Python 3.11 or newer** from [python.org](https://python.org)

2. **Install the bot** using pip:
   ```bash
   python -m pip install --user --upgrade --force-reinstall git+https://github.com/Folky83/RecoveryTBot.git
   ```

3. **Set your Telegram bot token**:
   - Create a file called `config.txt` in any folder
   - Add your token: `TELEGRAM_BOT_TOKEN=your_bot_token_here`
   - Or set environment variable: `set TELEGRAM_BOT_TOKEN=your_bot_token_here`

4. **Run the bot**:
   ```bash
   python -m mintos_bot.run
   ```

5. **Access the dashboard** at: http://localhost:5000

### Updating to Latest Version

To update the bot to the latest version:
```bash
python -m pip install --user --upgrade --force-reinstall git+https://github.com/Folky83/RecoveryTBot.git
```

### Option 2: Clone and Run

1. **Clone this repository**:
   ```bash
   git clone https://github.com/yourusername/mintos-telegram-bot.git
   cd mintos-telegram-bot
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set your Telegram bot token** (choose one method):
   
   **Method A: Create config.txt file**
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```
   
   **Method B: Set environment variable**
   ```bash
   set TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```

4. **Run the bot**:
   ```bash
   python run.py
   ```

## Getting a Telegram Bot Token

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the token that looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
5. Use this token in your configuration

## Configuration

The bot will automatically create necessary data directories and files on first run. All data is stored locally in the `data/` folder.

### Optional Configuration

You can customize the bot by editing the configuration files in the `mintos_bot/` folder:

- `constants.py` - Main configuration settings
- `config.py` - Bot behavior settings

## Usage

### Telegram Commands

- `/start` - Start the bot and get help
- `/status` - Check bot status
- `/updates` - Get recent updates
- `/companies` - List monitored companies
- `/campaigns` - View active campaigns

### Web Dashboard

Access the dashboard at `http://localhost:5000` to:
- View all recovery updates
- Filter by company
- See active campaigns
- Monitor bot status

## Important Commands to Remember

### Installation & Updates
```bash
# Install the bot (first time)
python -m pip install --user --upgrade --force-reinstall git+https://github.com/Folky83/RecoveryTBot.git

# Update to latest version
python -m pip install --user --upgrade --force-reinstall git+https://github.com/Folky83/RecoveryTBot.git
```

### Running the Bot
```bash
# Run the bot (from any directory)
python -m mintos_bot.run
```

### Package Location
The installed package is located at:
```
C:\Users\[YourUsername]\AppData\Roaming\Python\Python313\site-packages\mintos_bot\
```

But you don't need to remember this location - just use `python -m mintos_bot.run` from anywhere.

## Troubleshooting

**Bot doesn't start:**
- Check that your token is correct in config.txt
- Ensure Python 3.11+ is installed
- Try reinstalling: `python -m pip install --user --upgrade --force-reinstall git+https://github.com/Folky83/RecoveryTBot.git`

**"python-telegram-bot" compatibility errors:**
- This usually means you need to update to the latest version
- Run the reinstall command above to get compatible library versions

**Dashboard not loading:**
- Check that port 5000 is not in use
- The bot will show "Warning: main.py not found, running bot without dashboard" but will still work for Telegram

**No updates appearing:**
- The bot checks for updates automatically
- New data appears when available from Mintos

## Support

For issues or questions, please create an issue on GitHub.

## License

This project is licensed under the MIT License.