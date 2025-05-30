#!/usr/bin/env python3
"""
Test script to verify proxy connection is working
"""
import asyncio
import aiohttp
import requests
import os
from mintos_bot.config import PROXY_HOST, PROXY_AUTH, USE_PROXY

async def test_proxy_aiohttp():
    """Test proxy with aiohttp (used by document scraper)"""
    print("Testing proxy with aiohttp...")
    
    if not USE_PROXY:
        print("Proxy is disabled in configuration")
        return
    
    proxy_url = f'http://{PROXY_AUTH}@{PROXY_HOST}'
    test_url = 'https://ipv4.icanhazip.com'
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(test_url, proxy=proxy_url) as response:
                if response.status == 200:
                    ip = await response.text()
                    print(f"✓ aiohttp proxy test successful - IP: {ip.strip()}")
                else:
                    print(f"✗ aiohttp proxy test failed - Status: {response.status}")
    except Exception as e:
        print(f"✗ aiohttp proxy test failed - Error: {e}")

def test_proxy_requests():
    """Test proxy with requests (used by Mintos API client)"""
    print("Testing proxy with requests...")
    
    if not USE_PROXY:
        print("Proxy is disabled in configuration")
        return
    
    proxies = {
        'http': f'http://{PROXY_AUTH}@{PROXY_HOST}',
        'https': f'http://{PROXY_AUTH}@{PROXY_HOST}'
    }
    test_url = 'https://ipv4.icanhazip.com'
    
    try:
        response = requests.get(test_url, proxies=proxies, timeout=10)
        if response.status_code == 200:
            ip = response.text.strip()
            print(f"✓ requests proxy test successful - IP: {ip}")
        else:
            print(f"✗ requests proxy test failed - Status: {response.status_code}")
    except Exception as e:
        print(f"✗ requests proxy test failed - Error: {e}")

async def main():
    print("Proxy Configuration Test")
    print("=" * 30)
    print(f"USE_PROXY: {USE_PROXY}")
    print(f"PROXY_HOST: {PROXY_HOST}")
    print(f"PROXY_AUTH: {'*' * len(PROXY_AUTH) if PROXY_AUTH else 'Not set'}")
    print()
    
    if USE_PROXY and PROXY_HOST and PROXY_AUTH:
        test_proxy_requests()
        await test_proxy_aiohttp()
    else:
        print("Proxy not properly configured - missing settings")

if __name__ == "__main__":
    asyncio.run(main())