import requests
import pandas as pd
import time
import json

# Define the range of IDs
lender_ids = range(0, 250)

# List to store data for all lender companies
data = []

# Function to retrieve recovery updates for each lender company
def get_recovery_updates(lender_id):
    url = f"https://www.mintos.com/webapp/api/marketplace-api/v1/lender-companies/{lender_id}/recovery-updates"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return None

# Loop through each lender ID and gather data
for lender_id in lender_ids:
    recovery_data = get_recovery_updates(lender_id)
    if recovery_data:
        data.append({"lender_id": lender_id, **recovery_data})
    time.sleep(0.1)  # Brief pause to avoid rate limiting (adjust if necessary)

# Save data to a JSON file
with open(r"recovery_updates\recovery_updates.json", "w") as json_file:
    json.dump(data, json_file, indent=4)
    
print("Data saved to recovery_updates.json")
