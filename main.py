import streamlit as st
import json
import os
import logging
from datetime import datetime
from bot.data_manager import DataManager
from bot.logger import setup_logger

# Set up logging
logger = setup_logger("streamlit_dashboard")
logger.info("Starting Streamlit Dashboard")

try:
    # Page configuration
    st.set_page_config(
        page_title="Mintos Updates Dashboard",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    logger.info("Page configuration set successfully")

    # Initialize DataManager
    data_manager = DataManager()
    logger.info("DataManager initialized")

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
    updates_file = 'data/recovery_updates.json'
    if os.path.exists(updates_file):
        logger.info(f"Loading updates from {updates_file}")
        try:
            with open(updates_file, 'r') as f:
                updates = json.load(f)
            logger.info(f"Successfully loaded {len(updates)} updates")

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
        except Exception as e:
            logger.error(f"Error loading or processing updates: {str(e)}", exc_info=True)
            st.error(f"Error loading updates: {str(e)}")

    else:
        logger.warning(f"Updates file not found at {updates_file}")
        st.warning("⚠️ No updates available yet. Please wait for the bot to collect some data.")
        st.info("The Telegram bot will automatically collect updates during working days at 4 PM, 5 PM, and 6 PM.")

except Exception as e:
    logger.error(f"Critical error in Streamlit application: {str(e)}", exc_info=True)
    st.error("⚠️ An error occurred while starting the application. Please check the logs for details.")

if __name__ == "__main__":
    import streamlit.web.bootstrap
    streamlit.web.bootstrap.run(main, "", args=['--server.port=5000', '--server.address=0.0.0.0'], flag_options={})