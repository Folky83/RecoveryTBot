import streamlit as st
import json
import os
from datetime import datetime
from bot.data_manager import DataManager

# Page configuration
st.set_page_config(
    page_title="Mintos Updates Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize DataManager
data_manager = DataManager()

# Custom CSS for better styling
st.markdown("""
    <style>
    .company-header {
        color: #1E88E5;
        padding: 10px 0;
    }
    .update-date {
        color: #666;
        font-size: 0.9em;
    }
    .update-description {
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
    }
    </style>
""", unsafe_allow_html=True)

# Dashboard title
st.title("🏦 Mintos Updates Dashboard")
st.markdown("Real-time monitoring of lending company updates from Mintos")

# Load and display updates
if os.path.exists('data/recovery_updates.json'):
    with open('data/recovery_updates.json', 'r') as f:
        updates = json.load(f)

    # Create a sidebar for company filtering
    st.sidebar.title("Filter Options")
    # Get unique company names
    companies = set()
    for update in updates:
        if "items" in update:
            company_name = data_manager.get_company_name(update.get('lender_id'))
            companies.add(company_name)

    selected_company = st.sidebar.selectbox(
        "Select Company",
        ["All Companies"] + sorted(list(companies))
    )

    # Display updates
    for update in updates:
        if "items" in update:
            company_name = data_manager.get_company_name(update.get('lender_id'))

            # Skip if doesn't match filter
            if selected_company != "All Companies" and company_name != selected_company:
                continue

            st.markdown(f"<h2 class='company-header'>{company_name}</h2>", unsafe_allow_html=True)

            for year_data in update["items"]:
                year = year_data.get('year')
                status = year_data.get('status', '').replace('_', ' ').title()

                with st.expander(f"📅 {year} - {status}"):
                    for item in year_data.get("items", []):
                        st.markdown(f"<p class='update-date'>🕒 {item.get('date', 'N/A')}</p>", unsafe_allow_html=True)
                        st.markdown(f"<div class='update-description'>{item.get('description', 'No description available')}</div>", unsafe_allow_html=True)

                        # Display recovery information if available
                        if 'recoveredAmount' in item or 'remainingAmount' in item:
                            recovery_col1, recovery_col2 = st.columns(2)
                            with recovery_col1:
                                if item.get('recoveredAmount'):
                                    st.metric("Recovered Amount", f"€{float(item['recoveredAmount']):,.2f}")
                            with recovery_col2:
                                if item.get('remainingAmount'):
                                    st.metric("Remaining Amount", f"€{float(item['remainingAmount']):,.2f}")

                        # Display expected recovery timeline
                        if item.get('expectedRecoveryYearFrom') and item.get('expectedRecoveryYearTo'):
                            st.info(f"Expected Recovery Timeline: {item['expectedRecoveryYearFrom']} - {item['expectedRecoveryYearTo']}")

                        st.markdown("---")

else:
    st.warning("⚠️ No updates available yet. Please wait for the bot to collect some data.")
    st.info("The Telegram bot will automatically collect updates during working days at 4 PM, 5 PM, and 6 PM.")