import requests
import time
from .logger import setup_logger
from .config import (
    MINTOS_API_BASE,
    REQUEST_DELAY,
    MAX_RETRIES,
    RETRY_DELAY,
    REQUEST_TIMEOUT
)

logger = setup_logger(__name__)

class MintosClient:
    def __init__(self):
        self.session = requests.Session()
        
    def get_recovery_updates(self, lender_id):
        url = f"{MINTOS_API_BASE}/lender-companies/{lender_id}/recovery-updates"
        
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching updates for lender {lender_id}, attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                continue
        return None

    def fetch_all_updates(self, lender_ids):
        updates = []
        for lender_id in lender_ids:
            recovery_data = self.get_recovery_updates(lender_id)
            if recovery_data:
                updates.append({"lender_id": lender_id, **recovery_data})
            time.sleep(REQUEST_DELAY)
        return updates
