
import streamlit as st
import json
import os
from datetime import datetime
from bot.data_manager import DataManager

st.set_page_config(page_title="Mintos Updates Dashboard", layout="wide")

# Initialize DataManager
data_manager = DataManager()

st.title("Mintos Updates Dashboard")

# Load and display updates
if os.path.exists('data/recovery_updates.json'):
    with open('data/recovery_updates.json', 'r') as f:
        updates = json.load(f)
    
    for update in updates:
        if "items" in update:
            company_name = data_manager.get_company_name(update.get('lender_id'))
            st.header(company_name)
            
            for year_data in update["items"]:
                year = year_data.get('year')
                status = year_data.get('status', '').replace('_', ' ').title()
                
                st.subheader(f"{year} - {status}")
                for item in year_data.get("items", []):
                    with st.expander(f"Update from {item.get('date', 'N/A')}"):
                        st.write(item.get('description', 'No description available'))
else:
    st.warning("No updates available yet. Please wait for the bot to collect some data.")
