"""
RSS Reader for NASDAQ Baltic News
Handles fetching, filtering, and processing of NASDAQ Baltic RSS feeds
"""
import asyncio
import aiohttp
import feedparser
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
import re
from .logger import setup_logger
from .base_manager import BaseManager
import os

logger = setup_logger(__name__)

class RSSItem:
    """Represents a single RSS news item"""
    def __init__(self, title: str, link: str, pub_date: str, guid: str, issuer: str):
        self.title = title
        self.link = link
        self.pub_date = pub_date
        self.guid = guid
        self.issuer = issuer
        self.published_dt = self._parse_date(pub_date)
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse RSS date string to datetime object"""
        try:
            # RSS date format: "Thu, 29 May 2025 18:18:15 +0300"
            return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        except ValueError:
            try:
                # Alternative format without timezone
                dt = datetime.strptime(date_str[:25], "%a, %d %b %Y %H:%M:%S")
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.warning(f"Could not parse date: {date_str}")
                return datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'title': self.title,
            'link': self.link,
            'pub_date': self.pub_date,
            'guid': self.guid,
            'issuer': self.issuer,
            'timestamp': self.published_dt.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RSSItem':
        """Create from dictionary"""
        return cls(
            title=data['title'],
            link=data['link'],
            pub_date=data['pub_date'],
            guid=data['guid'],
            issuer=data['issuer']
        )

class RSSReader(BaseManager):
    """RSS Reader for NASDAQ Baltic news with keyword filtering"""
    
    def __init__(self):
        super().__init__('data/rss_cache.json')
        self.rss_url = "https://nasdaqbaltic.com/statistics/en/news?rss=1&num=50&issuer="
        self.keywords_file = 'data/rss_keywords.txt'
        self.sent_items_file = 'data/rss_sent_items.json'
        self.user_preferences_file = 'data/rss_user_preferences.json'
        
        # Initialize data structures
        self.keywords: Set[str] = set()
        self.sent_items: Set[str] = set()
        self.user_preferences: Dict[str, bool] = {}
        
        # Load existing data
        self._load_keywords()
        self._load_sent_items()
        self._load_user_preferences()
    
    def _load_keywords(self) -> None:
        """Load keywords from file"""
        try:
            # Try package data first, then local file
            keywords_path = self._find_data_file('rss_keywords.txt', self.keywords_file)
            
            if keywords_path and os.path.exists(keywords_path):
                with open(keywords_path, 'r', encoding='utf-8') as f:
                    self.keywords = {line.strip().lower() for line in f if line.strip()}
                logger.info(f"Loaded {len(self.keywords)} keywords for RSS filtering from {keywords_path}")
            else:
                # Create default keywords file
                default_keywords = [
                    'bigbank', 'auga', 'trigon', 'indexo', 'amber grid',
                    'litgrid', 'mainor', 'invl', 'pst group', 'tkm grupp'
                ]
                self.keywords = set(default_keywords)
                self._save_keywords()
        except Exception as e:
            logger.error(f"Error loading keywords: {e}")
            self.keywords = set()

    def _find_data_file(self, package_filename: str, fallback_path: str) -> str:
        """Find data file in package or fallback to local path"""
        try:
            # Try to find in package data
            import mintos_bot
            package_dir = os.path.dirname(mintos_bot.__file__)
            package_data_path = os.path.join(package_dir, 'data', package_filename)
            
            if os.path.exists(package_data_path):
                return package_data_path
        except Exception:
            pass
        
        # Fallback to local path
        return fallback_path
    
    def _save_keywords(self) -> None:
        """Save keywords to file"""
        try:
            os.makedirs(os.path.dirname(self.keywords_file), exist_ok=True)
            with open(self.keywords_file, 'w', encoding='utf-8') as f:
                for keyword in sorted(self.keywords):
                    f.write(f"{keyword}\n")
            logger.info(f"Saved {len(self.keywords)} keywords")
        except Exception as e:
            logger.error(f"Error saving keywords: {e}")
    
    def _load_sent_items(self) -> None:
        """Load sent item GUIDs"""
        try:
            if os.path.exists(self.sent_items_file):
                with open(self.sent_items_file, 'r') as f:
                    import json
                    data = json.load(f)
                    self.sent_items = set(data)
                logger.info(f"Loaded {len(self.sent_items)} sent RSS items")
            else:
                self.sent_items = set()
        except Exception as e:
            logger.error(f"Error loading sent items: {e}")
            self.sent_items = set()
    
    def _save_sent_items(self) -> None:
        """Save sent item GUIDs"""
        try:
            os.makedirs(os.path.dirname(self.sent_items_file), exist_ok=True)
            with open(self.sent_items_file, 'w') as f:
                import json
                json.dump(list(self.sent_items), f, indent=2)
            logger.info(f"Saved {len(self.sent_items)} sent RSS items")
        except Exception as e:
            logger.error(f"Error saving sent items: {e}")
    
    def _load_user_preferences(self) -> None:
        """Load user RSS preferences"""
        try:
            if os.path.exists(self.user_preferences_file):
                with open(self.user_preferences_file, 'r') as f:
                    import json
                    self.user_preferences = json.load(f)
                logger.info(f"Loaded RSS preferences for {len(self.user_preferences)} users")
            else:
                self.user_preferences = {}
        except Exception as e:
            logger.error(f"Error loading user preferences: {e}")
            self.user_preferences = {}
    
    def _save_user_preferences(self) -> None:
        """Save user RSS preferences"""
        try:
            os.makedirs(os.path.dirname(self.user_preferences_file), exist_ok=True)
            with open(self.user_preferences_file, 'w') as f:
                import json
                json.dump(self.user_preferences, f, indent=2)
            logger.info(f"Saved RSS preferences for {len(self.user_preferences)} users")
        except Exception as e:
            logger.error(f"Error saving user preferences: {e}")
    
    def set_user_preference(self, chat_id: str, enabled: bool) -> None:
        """Set RSS notifications preference for a user"""
        self.user_preferences[str(chat_id)] = enabled
        self._save_user_preferences()
        logger.info(f"RSS notifications {'enabled' if enabled else 'disabled'} for user {chat_id}")
    
    def get_user_preference(self, chat_id: str) -> bool:
        """Get RSS notifications preference for a user (default: False)"""
        return self.user_preferences.get(str(chat_id), False)
    
    def get_users_with_rss_enabled(self) -> List[str]:
        """Get list of users who have RSS notifications enabled"""
        return [chat_id for chat_id, enabled in self.user_preferences.items() if enabled]
    
    def add_keyword(self, keyword: str) -> None:
        """Add a keyword for filtering"""
        self.keywords.add(keyword.lower().strip())
        self._save_keywords()
    
    def remove_keyword(self, keyword: str) -> bool:
        """Remove a keyword from filtering"""
        keyword_lower = keyword.lower().strip()
        if keyword_lower in self.keywords:
            self.keywords.remove(keyword_lower)
            self._save_keywords()
            return True
        return False
    
    def get_keywords(self) -> List[str]:
        """Get all keywords"""
        return sorted(list(self.keywords))
    
    def _matches_keywords(self, item: RSSItem) -> bool:
        """Check if RSS item matches any keyword"""
        if not self.keywords:
            logger.debug("No keywords set, including all RSS items")
            return True  # If no keywords set, include all items
        
        # Check in title and issuer
        text_to_check = f"{item.title} {item.issuer}".lower()
        logger.debug(f"Checking RSS item: '{text_to_check}' against keywords: {self.keywords}")
        
        for keyword in self.keywords:
            if keyword in text_to_check:
                logger.debug(f"RSS item matched keyword '{keyword}': {item.title}")
                return True
        
        logger.debug(f"RSS item did not match any keywords: {item.title}")
        return False
    
    async def fetch_rss_feed(self) -> List[RSSItem]:
        """Fetch and parse RSS feed"""
        try:
            logger.info(f"Fetching RSS feed from {self.rss_url}")
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.rss_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        feed = feedparser.parse(content)
                        
                        items = []
                        for entry in feed.entries:
                            try:
                                # Extract CDATA content properly
                                title = entry.title if hasattr(entry, 'title') else 'No title'
                                
                                # Try to extract issuer from different RSS fields
                                issuer = 'Unknown issuer'
                                if hasattr(entry, 'issuer'):
                                    issuer = entry.issuer
                                elif hasattr(entry, 'author'):
                                    issuer = entry.author
                                elif hasattr(entry, 'description'):
                                    # Try to extract company name from description
                                    description = entry.description
                                    # Look for patterns like "Company Name -" or "Company Name:"
                                    import re
                                    match = re.search(r'^([^-:]+)[-:]', description)
                                    if match:
                                        issuer = match.group(1).strip()
                                elif hasattr(entry, 'summary'):
                                    # Try to extract from summary
                                    summary = entry.summary
                                    import re
                                    match = re.search(r'^([^-:]+)[-:]', summary)
                                    if match:
                                        issuer = match.group(1).strip()
                                
                                # Also try to extract issuer from title if it contains company patterns
                                if issuer == 'Unknown issuer':
                                    title_lower = title.lower()
                                    for keyword in self.keywords:
                                        if keyword.lower() in title_lower:
                                            issuer = keyword
                                            break
                                
                                # Debug: log the actual issuer found
                                logger.debug(f"RSS entry - Title: '{title}', Issuer: '{issuer}'")
                                
                                item = RSSItem(
                                    title=title,
                                    link=entry.link,
                                    pub_date=entry.published,
                                    guid=entry.guid,
                                    issuer=issuer
                                )
                                items.append(item)
                            except Exception as e:
                                logger.warning(f"Error parsing RSS entry: {e}")
                                continue
                        
                        logger.info(f"Fetched {len(items)} RSS items")
                        return items
                    else:
                        logger.error(f"RSS feed fetch failed with status: {response.status}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error fetching RSS feed: {e}")
            return []
    
    def get_new_items(self, items: List[RSSItem]) -> List[RSSItem]:
        """Filter out already sent items and apply keyword filtering"""
        new_items = []
        
        for item in items:
            # Skip if already sent
            if item.guid in self.sent_items:
                continue
            
            # Apply keyword filtering
            if not self._matches_keywords(item):
                continue
            
            new_items.append(item)
        
        logger.info(f"Found {len(new_items)} new filtered RSS items")
        return new_items
    
    def mark_item_as_sent(self, item: RSSItem) -> None:
        """Mark an RSS item as sent"""
        self.sent_items.add(item.guid)
        # Keep only recent items to prevent file from growing too large
        if len(self.sent_items) > 1000:
            # Sort by timestamp and keep only the most recent 800
            all_items = list(self.sent_items)
            self.sent_items = set(all_items[-800:])
        
        self._save_sent_items()
    
    def format_rss_message(self, item: RSSItem) -> str:
        """Format RSS item for Telegram message"""
        # Format date for display
        try:
            display_date = item.published_dt.strftime("%Y-%m-%d %H:%M")
        except:
            display_date = "Unknown date"
        
        message = (
            f"📰 <b>NASDAQ Baltic News</b>\n\n"
            f"<b>{item.issuer}</b>\n"
            f"{item.title}\n\n"
            f"📅 {display_date}\n"
            f"🔗 <a href=\"{item.link}\">Read more</a>"
        )
        
        return message

    async def check_and_get_new_items(self) -> List[RSSItem]:
        """Check RSS feed and return new filtered items"""
        all_items = await self.fetch_rss_feed()
        if not all_items:
            return []
        
        new_items = self.get_new_items(all_items)
        return new_items