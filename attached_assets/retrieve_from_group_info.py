import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterUrl, MessageEntityUrl
from urllib.parse import urlparse
import validators
import xml.etree.ElementTree as ET

# Replace with your API credentials
API_ID = '24210317'
API_HASH = '06c49c758f2505cfb336564ae12fdf92'
SESSION_NAME = 'user_account_session'  # Session name for Telethon
GROUP_NAME = 'Mintos.com community chat'  # Replace with the group name or ID

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

EXCLUDED_DOMAINS = ["mintos.com", "beyondp2p", "t.me"]

def ensure_scheme(url):
    """Add https:// scheme if missing or correct the scheme if malformed."""
    parsed_url = urlparse(url)
    if not parsed_url.scheme or parsed_url.scheme not in ['http', 'https']:
        return f'https://{parsed_url.netloc}{parsed_url.path}' if parsed_url.netloc else f'https://{parsed_url.path}'
    return url

def is_excluded_url(url):
    """Check if the URL is from excluded domains or improperly formatted."""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()
    return any(excluded in domain for excluded in EXCLUDED_DOMAINS) or not validators.url(url)

def generate_preview_from_og(url):
    """Fetch and parse the webpage for Open Graph metadata."""
    url = ensure_scheme(url)

    if is_excluded_url(url):
        print(f"Excluded URL: {url}")
        return None

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract Open Graph metadata
        def get_meta_content(property_name):
            tag = soup.find('meta', property=property_name)
            return tag['content'] if tag and tag.has_attr('content') else None

        description = get_meta_content('og:description') or 'No description available.'

        # Exclude items with no meaningful description
        if description == 'No description available.':
            print(f"Excluded due to missing description: {url}")
            return None

        return {
            'title': get_meta_content('og:title') or 'No title',
            'description': description,
            'thumbnail': get_meta_content('og:image'),
            'pub_date': get_meta_content('article:published_time') or '',
            'link': url
        }

    except requests.exceptions.RequestException as e:
        print(f"Error generating preview for {url}: {e}")
        return None

async def extract_shared_links(client, group_name):
    group_entity = None
    async for dialog in client.iter_dialogs():
        if group_name in (dialog.name, str(dialog.entity.id)):
            group_entity = dialog.entity
            break

    if not group_entity:
        raise ValueError(f"Group '{group_name}' not found. Ensure you are a member.")

    links = []
    async for message in client.iter_messages(group_entity, filter=InputMessagesFilterUrl(), limit=50):
        if message.entities:
            for entity in message.entities:
                if isinstance(entity, MessageEntityUrl):
                    link = message.text[entity.offset:entity.offset + entity.length]
                    if not is_excluded_url(link):
                        links.append({
                            'url': link,
                            'message_date': message.date.isoformat()  # Store message date as ISO format string
                        })

    return links

def generate_preview_from_og(url, fallback_date):
    """Fetch and parse the webpage for Open Graph metadata, with a fallback date."""
    url = ensure_scheme(url)

    if is_excluded_url(url):
        print(f"Excluded URL: {url}")
        return None

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract Open Graph metadata
        def get_meta_content(property_name):
            tag = soup.find('meta', property=property_name)
            return tag['content'] if tag and tag.has_attr('content') else None

        description = get_meta_content('og:description') or 'No description available.'

        # Exclude items with no meaningful description
        if description == 'No description available.':
            print(f"Excluded due to missing description: {url}")
            return None

        return {
            'title': get_meta_content('og:title') or 'No title',
            'description': description,
            'thumbnail': get_meta_content('og:image'),
            'pub_date': get_meta_content('article:published_time') or fallback_date,
            'link': url
        }

    except requests.exceptions.RequestException as e:
        print(f"Error generating preview for {url}: {e}")
        return None

async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    links = await extract_shared_links(client, GROUP_NAME)
    print(f"Extracted {len(links)} shared links:")

    # Generate previews using Open Graph metadata and create RSS feed
    links_with_previews = [
        generate_preview_from_og(link_info['url'], link_info['message_date'])
        for link_info in links
        if (preview := generate_preview_from_og(link_info['url'], link_info['message_date'])) is not None
    ]
    create_rss_feed(links_with_previews)

    print(f"RSS feed has been created with {len(links_with_previews)} items.")
    await client.disconnect()

# Ensure this part is placed above the `main` function
def create_rss_feed(items):
    """Create an RSS feed from the extracted items."""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    # Add RSS feed metadata
    ET.SubElement(channel, "title").text = "Interesting webpages"
    ET.SubElement(channel, "description").text = "This feed contains shared links found online."
    ET.SubElement(channel, "link").text = "http://example.com/rss"

    # Add items to the RSS feed
    for item in items:
        if item:  # Ensure the item is not None
            rss_item = ET.SubElement(channel, "item")
            ET.SubElement(rss_item, "title").text = item['title']
            ET.SubElement(rss_item, "link").text = item['link']
            ET.SubElement(rss_item, "description").text = item['description']
            ET.SubElement(rss_item, "pubDate").text = item['pub_date']

            if item['thumbnail']:
                ET.SubElement(rss_item, "enclosure", url=item['thumbnail'], type="image/jpeg")

    # Generate the RSS XML string
    tree = ET.ElementTree(rss)
    tree.write("url_feed.xml", encoding="utf-8", xml_declaration=True)
    print("RSS feed has been created as 'url_feed.xml'.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
