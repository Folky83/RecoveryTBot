# Standalone Mintos Campaign Monitor

This completely self-contained script monitors Mintos campaigns and sends Telegram notifications for new campaigns. It's designed to run independently on your laptop without requiring any other files from the main project.

## Features

- Completely standalone - all code is contained in a single Python file
- Checks for new Mintos campaigns at regular intervals (default: every 60 seconds)
- Sends immediate Telegram notifications when new campaigns are detected
- Filters out already-seen campaigns to prevent duplicate notifications
- Only notifies about currently active campaigns
- Robust error handling and automatic retry mechanism for failed messages
- Supports multiple users/channels for notifications

## Requirements

- Python 3.7+
- python-telegram-bot library
- requests library
- Telegram Bot Token set as an environment variable

## Installation

1. Make sure you have all the required Python packages installed:
   ```
   pip install python-telegram-bot requests
   ```

2. Ensure the script has executable permissions:
   ```
   chmod +x standalone_campaign_monitor.py
   ```

3. Set your Telegram Bot Token as an environment variable:
   ```
   export TELEGRAM_BOT_TOKEN="your_bot_token_here"
   ```

## Usage

Run the script with default settings:

```
python standalone_campaign_monitor.py
```

The script uses the Telegram bot token automatically from the environment variables configured on the system.

Additional options:

```
# Change the check interval (default is 60 seconds)
python standalone_campaign_monitor.py --check-interval 30
```

## Running on a different system

The script already has the Telegram bot token hardcoded for convenience. If you want to use your own token:

Edit the script to update your token by changing this line:

```python
# Telegram bot token - hardcoded for local use
TELEGRAM_BOT_TOKEN = "7368080976:AAE0vM2--epmISjYnrq5zvshFFBFiIvUS9M"
```

to your own token:

```python
# Telegram bot token - hardcoded for local use
TELEGRAM_BOT_TOKEN = "YOUR_ACTUAL_TOKEN_HERE"
```

## How It Works

1. The script checks for new campaigns on the Mintos website.
2. It compares the retrieved campaigns with previously seen ones.
3. If new campaigns are found, it sends notifications to all registered users.
4. The script maintains a local data directory to track:
   - Previously seen campaigns
   - List of users/chats to notify
   - Campaign cache to avoid unnecessary API calls

## Adding Users

You need to add user IDs to the `data/users.json` file manually if you want to notify multiple users.

Create a file at `data/users.json` with the following structure:
```json
{
  "YOUR_TELEGRAM_ID": "your_username",
  "ANOTHER_USER_ID": "their_username"
}
```

Replace `YOUR_TELEGRAM_ID` with your Telegram user ID (a number). You can get this by talking to @userinfobot on Telegram.

## Running as a Background Service

### Option 1: Using nohup (Linux/macOS)

```
nohup ./standalone_campaign_monitor.py > campaign_monitor.log 2>&1 &
```

### Option 2: Using systemd (Linux)

Create a systemd service file:

```
[Unit]
Description=Mintos Campaign Monitor
After=network.target

[Service]
ExecStart=/path/to/standalone_campaign_monitor.py
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
7. In the task settings, set environment variables for TELEGRAM_BOT_TOKEN

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
- All dependencies are included in the script itself