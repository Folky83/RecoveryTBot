# Mintos Campaign Monitor

This standalone script monitors Mintos campaigns every minute and sends Telegram notifications for new campaigns. It's designed to be run independently from the main Mintos Telegram bot.

## Features

- Checks for new Mintos campaigns at regular intervals (default: every 60 seconds)
- Sends immediate Telegram notifications when new campaigns are detected
- Filters out already-seen campaigns to prevent duplicate notifications
- Only notifies about currently active campaigns
- Robust error handling and automatic retry mechanism for failed messages
- Supports multiple users/channels for notifications

## Requirements

- Python 3.7+
- python-telegram-bot library
- Telegram Bot Token set as an environment variable

## Installation

1. Make sure you have all the required Python packages installed
2. Ensure the script has executable permissions:
   ```
   chmod +x campaign_monitor.py
   ```
3. Set your Telegram Bot Token as an environment variable:
   ```
   export TELEGRAM_BOT_TOKEN="your_bot_token_here"
   ```

## Usage

Run the script with the default 60-second check interval:

```
./campaign_monitor.py
```

Or specify a different check interval (in seconds):

```
./campaign_monitor.py --check-interval 30
```

## Running as a Background Service

To run the script as a background service on your laptop, you can:

### Option 1: Using nohup (Linux/macOS)

```
nohup ./campaign_monitor.py > campaign_monitor.log 2>&1 &
```

### Option 2: Using systemd (Linux)

Create a systemd service file:

```
[Unit]
Description=Mintos Campaign Monitor
After=network.target

[Service]
ExecStart=/path/to/campaign_monitor.py
Environment="TELEGRAM_BOT_TOKEN=your_bot_token_here"
Restart=on-failure
User=yourusername

[Install]
WantedBy=multi-user.target
```

Save this to `/etc/systemd/system/mintos-campaign-monitor.service` and enable/start:

```
sudo systemctl enable mintos-campaign-monitor.service
sudo systemctl start mintos-campaign-monitor.service
```

### Option 3: Using Task Scheduler (Windows)

1. Open Task Scheduler
2. Create a new basic task
3. Set the trigger to "At startup" or "At log on"
4. Set the action to "Start a program"
5. Browse to your Python executable and add the script as an argument
6. Make sure to set the "Start in" directory to where your script is located

## Terminating the Script

To stop the script, press Ctrl+C or send a SIGTERM signal to the process:

```
kill <process_id>
```

## Notes

- The script will automatically retry sending failed messages
- Campaigns marked as "Special Promotion" (type 4) are filtered out
- The script creates a data directory if it doesn't exist
- Cache files are used to track which campaigns have already been sent