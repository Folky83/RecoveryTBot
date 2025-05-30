"""
RSS Reader for Multiple News Sources
Handles fetching, filtering, and processing of RSS feeds from:
- NASDAQ Baltic News (with keyword filtering)
- Mintos News (no filtering)
- FFNews (with keyword filtering on titles)
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
    def __init__(self, title: str, link: str, pub_date: str, guid: str, issuer: str, feed_source: str = "nasdaq"):
        self.title = title
        self.link = link
        self.pub_date = pub_date
        self.guid = guid
        self.issuer = issuer
        self.feed_source = feed_source  # "nasdaq", "mintos", or "ffnews"
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
            'feed_source': self.feed_source,
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
            issuer=data['issuer'],
            feed_source=data.get('feed_source', 'nasdaq')
        )

class RSSReader(BaseManager):
    """RSS Reader for multiple news sources with keyword filtering"""
    
    def __init__(self):
        super().__init__('data/rss_cache.json')
        
        # Feed URLs
        self.feed_urls = {
            'nasdaq': "https://nasdaqbaltic.com/statistics/en/news?rss=1&num=50&issuer=",
            'mintos': "https://www.mintos.com/blog/category/news/feed/",
            'ffnews': "https://ffnews.com/category/newsarticle/feed/"
        }
        
        # Feed configurations with different update intervals and proxy settings
        self.feed_configs = {
            'nasdaq': {'interval_minutes': 15, 'use_proxy': True},
            'mintos': {'interval_minutes': 60, 'use_proxy': False},
            'ffnews': {'interval_minutes': 60, 'use_proxy': False}
        }
        
        # Last check timestamps for each feed
        self.last_check_times = {
            'nasdaq': None,
            'mintos': None, 
            'ffnews': None
        }
        
        self.keywords_file = 'data/rss_keywords.txt'
        self.sent_items_file = 'data/rss_sent_items.json'
        self.user_preferences_file = 'data/rss_user_preferences.json'
        self.last_check_file = 'data/rss_last_check.json'
        
        # Initialize data structures
        self.keywords: Set[str] = set()
        self.sent_items: Set[str] = set()
        self.user_preferences: Dict[str, bool] = {}
        
        # Load existing data
        self._load_keywords()
        self._load_sent_items()
        self._load_user_preferences()
        self._load_last_check_times()
    
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

    def _load_last_check_times(self) -> None:
        """Load last check timestamps for each feed"""
        try:
            if os.path.exists(self.last_check_file):
                import json
                with open(self.last_check_file, 'r') as f:
                    data = json.load(f)
                    for feed, timestamp in data.items():
                        if feed in self.last_check_times:
                            self.last_check_times[feed] = datetime.fromisoformat(timestamp) if timestamp else None
                logger.info(f"Loaded last check times for {len(data)} feeds")
        except Exception as e:
            logger.error(f"Error loading last check times: {e}")

    def _save_last_check_times(self) -> None:
        """Save last check timestamps for each feed"""
        try:
            import json
            os.makedirs(os.path.dirname(self.last_check_file), exist_ok=True)
            data = {}
            for feed, timestamp in self.last_check_times.items():
                data[feed] = timestamp.isoformat() if timestamp else None
            with open(self.last_check_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug("Saved last check times")
        except Exception as e:
            logger.error(f"Error saving last check times: {e}")
    
    def _should_check_feed(self, feed_source: str) -> bool:
        """Check if enough time has passed to check a specific feed"""
        config = self.feed_configs.get(feed_source)
        if not config:
            return False
            
        last_check = self.last_check_times.get(feed_source)
        if not last_check:
            return True  # Never checked before
            
        now = datetime.now(timezone.utc)
        time_diff = now - last_check
        required_interval = config['interval_minutes'] * 60  # Convert to seconds
        
        should_check = time_diff.total_seconds() >= required_interval
        logger.debug(f"Feed {feed_source}: last check {time_diff.total_seconds():.0f}s ago, required {required_interval}s, should_check={should_check}")
        return should_check

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
        """Check if RSS item matches any keyword based on feed source"""
        # For Mintos feed, no filtering required
        if item.feed_source == "mintos":
            return True
        
        # For other feeds, apply keyword filtering
        if not self.keywords:
            logger.debug("No keywords set, including all RSS items")
            return True  # If no keywords set, include all items
        
        # For FFNews, only check title
        if item.feed_source == "ffnews":
            text_to_check = item.title.lower()
        else:
            # For NASDAQ and other feeds, check title and issuer
            text_to_check = f"{item.title} {item.issuer}".lower()
        
        logger.debug(f"Checking {item.feed_source} RSS item: '{text_to_check}' against keywords: {self.keywords}")
        
        for keyword in self.keywords:
            if keyword in text_to_check:
                logger.debug(f"RSS item matched keyword '{keyword}': {item.title}")
                return True
        
        logger.debug(f"RSS item did not match any keywords: {item.title}")
        return False
    
    async def fetch_single_feed(self, feed_source: str, url: str) -> List[RSSItem]:
        """Fetch and parse a single RSS feed"""
        try:
            logger.info(f"Fetching {feed_source} RSS feed from {url}")
            
            # Get feed configuration
            config = self.feed_configs.get(feed_source, {})
            use_proxy = config.get('use_proxy', True)
            
            timeout = aiohttp.ClientTimeout(total=30)
            
            # Configure session with or without proxy
            connector_kwargs = {}
            session_kwargs = {'timeout': timeout}
            
            if use_proxy:
                # Use proxy for NASDAQ Baltic feed
                try:
                    proxy_url = os.getenv('PROXY_URL')
                    if proxy_url:
                        session_kwargs['connector'] = aiohttp.TCPConnector()
                        logger.debug(f"Using proxy for {feed_source} feed")
                    else:
                        logger.debug(f"No proxy configured for {feed_source} feed")
                except Exception as e:
                    logger.warning(f"Proxy setup failed for {feed_source}: {e}")
            else:
                logger.debug(f"Bypassing proxy for {feed_source} feed")
            
            async with aiohttp.ClientSession(**session_kwargs) as session:
                # Add proxy to request if configured
                request_kwargs = {}
                if use_proxy:
                    proxy_url = os.getenv('PROXY_URL')
                    if proxy_url:
                        request_kwargs['proxy'] = proxy_url
                
                async with session.get(url, **request_kwargs) as response:
                    if response.status == 200:
                        content = await response.text()
                        feed = feedparser.parse(content)
                        
                        items = []
                        for entry in feed.entries:
                            try:
                                title = entry.title if hasattr(entry, 'title') else 'No title'
                                
                                # Handle different feed structures
                                if feed_source == "mintos":
                                    issuer = "Mintos"
                                elif feed_source == "ffnews":
                                    issuer = entry.author if hasattr(entry, 'author') else "FF News"
                                else:  # nasdaq
                                    # Try to extract issuer from different RSS fields
                                    issuer = 'Unknown issuer'
                                    if hasattr(entry, 'issuer'):
                                        issuer = entry.issuer
                                    elif hasattr(entry, 'author'):
                                        issuer = entry.author
                                    elif hasattr(entry, 'description'):
                                        # Try to extract company name from description
                                        description = entry.description
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
                                
                                logger.debug(f"{feed_source} RSS entry - Title: '{title}', Issuer: '{issuer}'")
                                
                                item = RSSItem(
                                    title=title,
                                    link=entry.link,
                                    pub_date=entry.published,
                                    guid=entry.guid,
                                    issuer=issuer,
                                    feed_source=feed_source
                                )
                                items.append(item)
                            except Exception as e:
                                logger.warning(f"Error parsing {feed_source} RSS entry: {e}")
                                continue
                        
                        logger.info(f"Fetched {len(items)} items from {feed_source}")
                        return items
                    else:
                        logger.error(f"{feed_source} RSS feed fetch failed with status: {response.status}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error fetching {feed_source} RSS feed: {e}")
            return []

    async def fetch_rss_feed(self) -> List[RSSItem]:
        """Fetch and parse RSS feeds based on their individual update frequencies"""
        all_items = []
        feeds_checked = []
        
        # Check each feed individually based on its update frequency
        for feed_source, url in self.feed_urls.items():
            if self._should_check_feed(feed_source):
                logger.info(f"Checking {feed_source} feed (due for update)")
                items = await self.fetch_single_feed(feed_source, url)
                all_items.extend(items)
                feeds_checked.append(feed_source)
                
                # Update last check time for this feed
                self.last_check_times[feed_source] = datetime.now(timezone.utc)
            else:
                logger.debug(f"Skipping {feed_source} feed (not due for update yet)")
        
        # Save updated check times if any feeds were checked
        if feeds_checked:
            self._save_last_check_times()
            logger.info(f"Fetched total of {len(all_items)} RSS items from {len(feeds_checked)} feeds: {', '.join(feeds_checked)}")
        else:
            logger.debug("No feeds were due for checking")
        
        return all_items

    async def fetch_all_rss_feeds_force(self) -> List[RSSItem]:
        """Force fetch all RSS feeds regardless of timing (for admin use)"""
        all_items = []
        
        # Force check all feeds
        for feed_source, url in self.feed_urls.items():
            logger.info(f"Force checking {feed_source} feed for admin")
            items = await self.fetch_single_feed(feed_source, url)
            all_items.extend(items)
        
        logger.info(f"Force fetched total of {len(all_items)} RSS items from {len(self.feed_urls)} feeds")
        return all_items
    
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
    
    def get_filtered_items_for_admin(self, items: List[RSSItem]) -> List[RSSItem]:
        """Apply only keyword filtering (no 'already sent' check) for admin operations"""
        filtered_items = []
        
        for item in items:
            # Apply keyword filtering only
            if not self._matches_keywords(item):
                continue
            
            filtered_items.append(item)
        
        logger.info(f"Found {len(filtered_items)} keyword-filtered RSS items for admin")
        return filtered_items
    
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
        """Format RSS item for Telegram message based on feed source"""
        # Format date for display
        try:
            display_date = item.published_dt.strftime("%Y-%m-%d %H:%M")
        except:
            display_date = "Unknown date"
        
        if item.feed_source == "mintos":
            message = (
                f"📈 <b>Mintos News</b>\n\n"
                f"<b>{item.title}</b>\n\n"
                f"📅 {display_date}\n"
                f"🔗 <a href=\"{item.link}\">Read more</a>"
            )
        elif item.feed_source == "ffnews":
            message = (
                f"💼 <b>Fintech Finance News</b>\n\n"
                f"<b>{item.title}</b>\n\n"
                f"✍️ {item.issuer}\n"
                f"📅 {display_date}\n"
                f"🔗 <a href=\"{item.link}\">Read more</a>"
            )
        else:  # nasdaq
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