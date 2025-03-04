#!/usr/bin/env python3
"""
Script to fetch and save a sample Mintos company page for analysis
"""
import asyncio
import aiohttp
import os
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fetch_sample')

async def fetch_page(url):
    """Fetch a web page"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.error(f"Failed to fetch {url}: HTTP {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

async def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_sample_page.py <company_name>")
        return
    
    company_name = sys.argv[1]
    url = f"https://www.mintos.com/en/lending-companies/{company_name}/"
    
    logger.info(f"Fetching page for {company_name}: {url}")
    html_content = await fetch_page(url)
    
    if html_content:
        os.makedirs('data', exist_ok=True)
        output_file = f"data/{company_name}_page.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"Saved page to {output_file}")
        
        # Count PDF links as a quick check
        pdf_count = html_content.lower().count('.pdf')
        logger.info(f"Found approximately {pdf_count} PDF references in the page")
    else:
        logger.error(f"Failed to fetch page for {company_name}")

if __name__ == "__main__":
    asyncio.run(main())