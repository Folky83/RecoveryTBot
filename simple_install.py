#!/usr/bin/env python3
"""
Simple installer for Mintos Telegram Bot
Downloads and sets up the bot without complex package management
"""

import os
import sys
import subprocess
import urllib.request
import zipfile
import tempfile
import shutil

def check_python():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("Error: Python 3.8 or higher is required")
        return False
    print(f"✓ Python {sys.version.split()[0]} found")
    return True

def install_dependencies():
    """Install required Python packages"""
    packages = [
        "aiohttp>=3.11.12",
        "beautifulsoup4>=4.13.3", 
        "feedparser>=6.0.11",
        "pandas>=2.2.3",
        "psutil>=6.1.1",
        "python-telegram-bot[job-queue]==20.7",
        "streamlit>=1.41.1",
        "trafilatura>=2.0.0",
        "twilio>=9.4.4",
        "watchdog>=6.0.0"
    ]
    
    print("Installing Python packages...")
    print("This may take a few minutes...")
    
    for package in packages:
        try:
            print(f"Installing {package.split('>=')[0].split('==')[0]}...")
            result = subprocess.run([sys.executable, "-m", "pip", "install", package, "--user"], 
                                 capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✓ Installed {package.split('>=')[0].split('==')[0]}")
            else:
                print(f"✗ Failed to install {package}")
                print(f"Error: {result.stderr}")
                return False
        except Exception as e:
            print(f"✗ Failed to install {package}: {e}")
            return False
    return True

def download_bot():
    """Download bot files from GitHub"""
    repo_url = "https://github.com/Folky83/RecoveryTBot/archive/refs/heads/main.zip"
    
    print("Downloading bot files...")
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "bot.zip")
            
            # Download ZIP file
            urllib.request.urlretrieve(repo_url, zip_path)
            print("✓ Downloaded bot files")
            
            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find extracted directory
            extracted_dirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
            if not extracted_dirs:
                print("✗ Could not find extracted files")
                return False
                
            source_dir = os.path.join(temp_dir, extracted_dirs[0])
            target_dir = "mintos-telegram-bot"
            
            # Copy to current directory
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            shutil.copytree(source_dir, target_dir)
            print(f"✓ Bot files extracted to {target_dir}")
            
            return target_dir
            
    except Exception as e:
        print(f"✗ Failed to download bot: {e}")
        return False

def create_config_instructions(bot_dir):
    """Create configuration instructions"""
    config_path = os.path.join(bot_dir, "config.txt")
    
    print("\n" + "="*50)
    print("SETUP COMPLETE!")
    print("="*50)
    print(f"Bot installed in: {os.path.abspath(bot_dir)}")
    print("\nNext steps:")
    print("1. Get a bot token from @BotFather on Telegram:")
    print("   - Open Telegram and search for @BotFather")
    print("   - Send /newbot and follow instructions")
    print("   - Copy the token (looks like: 123456789:ABC...)")
    print()
    print(f"2. Create config file: {config_path}")
    print("   Add this line: TELEGRAM_BOT_TOKEN=your_token_here")
    print()
    print(f"3. Run the bot:")
    print(f"   cd {bot_dir}")
    print("   python run.py")
    print()
    print("4. Access dashboard at: http://localhost:5000")
    print("="*50)

def main():
    """Main installation function"""
    print("Mintos Telegram Bot - Simple Installer")
    print("=" * 40)
    
    if not check_python():
        input("Press Enter to exit...")
        return
    
    if not install_dependencies():
        print("\n✗ Failed to install dependencies")
        input("Press Enter to exit...")
        return
    
    bot_dir = download_bot()
    if not bot_dir:
        print("\n✗ Failed to download bot files")
        input("Press Enter to exit...")
        return
    
    create_config_instructions(bot_dir)
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()