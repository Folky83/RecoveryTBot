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
   pip install --upgrade git+https://github.com/yourusername/mintos-telegram-bot.git
   ```

3. **Set your Telegram bot token**:
   - Create a file called `config.txt` in any folder
   - Add your token: `TELEGRAM_BOT_TOKEN=your_bot_token_here`
   - Or set environment variable: `set TELEGRAM_BOT_TOKEN=your_bot_token_here`

4. **Run the bot**:
   ```bash
   mintos-bot
   ```

5. **Access the dashboard** at: http://localhost:5000

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

## Troubleshooting

**Bot doesn't start:**
- Check that your token is correct
- Ensure Python 3.11+ is installed
- Verify internet connection

**Dashboard not loading:**
- Check that port 5000 is not in use
- Try restarting the bot

**No updates appearing:**
- The bot checks for updates automatically
- New data appears when available from Mintos

## Support

For issues or questions, please create an issue on GitHub.

## License

This project is licensed under the MIT License.