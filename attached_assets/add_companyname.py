import json
import pandas as pd

# Load the spreadsheet containing lender IDs and company names
spreadsheet_path = r'recovery_updates\lo_names.xlsx'
df = pd.read_excel(spreadsheet_path)

# Ensure the dataframe has columns 'lender_id' and 'company_name'
df.columns = df.columns.str.strip()
lender_id_to_name = df.set_index('lender_id')['company_name'].to_dict()

# Load the JSON data
json_path = r'recovery_updates\recovery_updates.json'
with open(json_path, 'r') as file:
    data = json.load(file)

# Modify data to add title with lender_name for each entry
for entry in data:
    lender_id = entry.get('lender_id')
    if lender_id in lender_id_to_name:
        lender_name = lender_id_to_name[lender_id]
        entry['title'] = f"Update payment delay for {lender_name}"

# Save the modified JSON data back to the file
with open(json_path, 'w') as file:
    json.dump(data, file, indent=4)

print("Script executed successfully. Titles have been added to each entry.")
