"""
Mintos API Client
Handles communication with the Mintos marketplace API.
"""
import requests
import time
from typing import Dict, List, Optional, Any, Union
from .logger import setup_logger
from .config import (
    MINTOS_API_BASE,
    MINTOS_CAMPAIGNS_URL,
    REQUEST_DELAY,
    MAX_RETRIES,
    RETRY_DELAY,
    REQUEST_TIMEOUT,
    PROXY_HOST,
    PROXY_AUTH,
    USE_PROXY
)

logger = setup_logger(__name__)

class MintosClient:
    """Client for interacting with Mintos API"""

    def __init__(self):
        """Initialize client with session"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; Mintos Monitor Bot/1.0)',
            'Accept': 'application/json'
        })
        
        # Configure proxy if enabled
        if USE_PROXY and PROXY_HOST and PROXY_AUTH:
            self.proxies = {
                'http': f'http://{PROXY_AUTH}@{PROXY_HOST}',
                'https': f'http://{PROXY_AUTH}@{PROXY_HOST}'
            }
            logger.info(f"Proxy configured: {PROXY_HOST}")
        else:
            self.proxies = None
            logger.info("No proxy configured")

    def _make_request(self, url: str, method: str = 'GET', **kwargs) -> Optional[Dict[str, Any]]:
        """Make an HTTP request with retries and error handling"""
        # Add proxy configuration to kwargs if available
        if self.proxies:
            kwargs['proxies'] = self.proxies
            
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=REQUEST_TIMEOUT,
                    **kwargs
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed, attempt {attempt + 1}/{MAX_RETRIES}: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                continue
            except Exception as e:
                logger.error(f"Unexpected error in API request: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                continue
        return None

    def get_recovery_updates(self, lender_id: Union[int, str]) -> Optional[Dict[str, Any]]:
        """Get recovery updates for a specific lender

        Args:
            lender_id: The ID of the lender

        Returns:
            Dictionary containing recovery updates or None if request fails
        """
        url = f"{MINTOS_API_BASE}/lender-companies/{lender_id}/recovery-updates"
        response = self._make_request(url)

        if response:
            logger.info(f"Successfully retrieved updates for lender {lender_id}")
            return response

        logger.error(f"Failed to get updates for lender {lender_id} after {MAX_RETRIES} attempts")
        return None

    def fetch_all_updates(self, lender_ids: List[Union[int, str]]) -> List[Dict[str, Any]]:
        """Fetch updates for multiple lenders

        Args:
            lender_ids: List of lender IDs to fetch updates for

        Returns:
            List of updates for all lenders
        """
        updates = []
        for lender_id in lender_ids:
            try:
                recovery_data = self.get_recovery_updates(lender_id)
                if recovery_data:
                    updates.append({"lender_id": lender_id, **recovery_data})
                time.sleep(REQUEST_DELAY)
            except Exception as e:
                logger.error(f"Error fetching updates for lender {lender_id}: {str(e)}")
                continue

        logger.info(f"Fetched updates for {len(updates)} out of {len(lender_ids)} lenders")
        return updates

    def get_campaigns(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch current Mintos campaigns

        Returns:
            List of active campaigns or None if request fails
        """
        response = self._make_request(MINTOS_CAMPAIGNS_URL)

        if response:
            # Handle different response formats - sometimes it's a dict with campaigns list
            if isinstance(response, list):
                campaigns = response
            elif isinstance(response, dict) and 'campaigns' in response:
                campaigns = response['campaigns']
                if not isinstance(campaigns, list):
                    logger.error(f"Expected campaigns to be a list, got: {type(campaigns)}")
                    return None
            elif isinstance(response, dict):
                # If it's a dict but not containing 'campaigns', treat it as single campaign
                campaigns = [response]
            else:
                logger.error(f"Unexpected response format: {type(response)}")
                return None
                
            logger.info(f"Successfully retrieved {len(campaigns)} campaigns")
            return campaigns

        logger.error(f"Failed to get campaigns after {MAX_RETRIES} attempts")
        return None