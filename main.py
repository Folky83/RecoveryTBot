import streamlit as st
import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from bot.data_manager import DataManager
from bot.logger import setup_logger

# Set up logging
logger = setup_logger("streamlit_dashboard")
logger.info("Starting Streamlit Dashboard")

# Constants
UPDATES_FILE = os.path.join('data', 'recovery_updates.json')
CACHE_REFRESH_SECONDS = 900  # 15 minutes

def _convert_to_float(value: Any) -> Optional[float]:
    """Safely convert a value to float"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

@dataclass
class UpdateItem:
    """Represents a single update item"""
    date: str
    description: str
    year: Optional[int] = None
    status: Optional[str] = None
    recovered_amount: Optional[float] = None
    remaining_amount: Optional[float] = None
    recovery_year_from: Optional[int] = None
    recovery_year_to: Optional[int] = None

@dataclass
class CompanyUpdate:
    """Represents company updates"""
    company_name: str
    lender_id: int
    items: List[UpdateItem]

class DashboardManager:
    """Manages dashboard data and rendering"""
    def __init__(self):
        self.data_manager = DataManager()
        self.updates: List[CompanyUpdate] = []
        self._load_updates()

    def _load_updates(self) -> None:
        """Load updates from file"""
        try:
            if not os.path.exists(UPDATES_FILE):
                logger.warning(f"Updates file not found: {UPDATES_FILE}")
                return

            with open(UPDATES_FILE, 'r') as f:
                raw_updates = json.load(f)

            self.updates = []
            for update in raw_updates:
                if "items" not in update:
                    continue

                lender_id = update.get('lender_id')
                company_name = self.data_manager.get_company_name(lender_id)

                items = []
                for year_data in update["items"]:
                    for item in year_data.get("items", []):
                        items.append(UpdateItem(
                            date=item.get('date', ''),
                            description=item.get('description', ''),
                            year=year_data.get('year'),
                            status=year_data.get('status', '').replace('_', ' ').title(),
                            recovered_amount=_convert_to_float(item.get('recoveredAmount')),
                            remaining_amount=_convert_to_float(item.get('remainingAmount')),
                            recovery_year_from=item.get('expectedRecoveryYearFrom'),
                            recovery_year_to=item.get('expectedRecoveryYearTo')
                        ))

                self.updates.append(CompanyUpdate(
                    company_name=company_name,
                    lender_id=lender_id,
                    items=sorted(items, key=lambda x: x.date, reverse=True)
                ))

            logger.info(f"Loaded {len(self.updates)} company updates")
        except Exception as e:
            logger.error(f"Error loading updates: {e}", exc_info=True)
            self.updates = []

    def render_dashboard(self) -> None:
        """Render the main dashboard"""
        try:
            self._set_page_config()
            self._apply_custom_css()
            self._render_header()

            if not self.updates:
                self._render_no_updates_message()
                return

            selected_company = self._render_company_filter()
            self._render_updates(selected_company)

        except Exception as e:
            logger.error(f"Error rendering dashboard: {e}", exc_info=True)
            st.error("⚠️ An error occurred while rendering the dashboard")

    def _set_page_config(self) -> None:
        """Configure page settings"""
        st.set_page_config(
            page_title="Mintos Updates Dashboard",
            layout="wide",
            initial_sidebar_state="expanded"
        )

    def _apply_custom_css(self) -> None:
        """Apply custom CSS styling"""
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

    def _render_header(self) -> None:
        """Render dashboard header"""
        st.title("🏦 Mintos Updates Dashboard")
        st.markdown("Real-time monitoring of lending company updates from Mintos")

    def _render_no_updates_message(self) -> None:
        """Render message when no updates are available"""
        st.warning("⚠️ No updates available yet. Please wait for the bot to collect data.")
        st.info("The Telegram bot will automatically collect updates during working days at 4 PM, 5 PM, and 6 PM.")

    def _render_company_filter(self) -> str:
        """Render company filter sidebar"""
        st.sidebar.title("Filter Options")
        companies = ["All Companies"] + sorted(
            set(update.company_name for update in self.updates)
        )
        return st.sidebar.selectbox("Select Company", companies)

    def _render_updates(self, selected_company: str) -> None:
        """Render updates for selected company"""
        for company in self.updates:
            if selected_company != "All Companies" and company.company_name != selected_company:
                continue

            st.markdown(f"<h2 class='company-header'>{company.company_name}</h2>", 
                       unsafe_allow_html=True)

            for item in company.items:
                with st.expander(f"📅 {item.year} - {item.status or 'No Status'}"):
                    st.markdown(f"<p class='update-date'>🕒 {item.date}</p>", 
                              unsafe_allow_html=True)
                    
                    # Clean HTML content in description
                    clean_description = (item.description or "")
                    clean_description = (clean_description
                        .replace('\u003C', '<')
                        .replace('\u003E', '>')
                        .replace('&#39;', "'")
                        .replace('&rsquo;', "'")
                        .replace('&euro;', '€')
                        .replace('&nbsp;', ' ')
                        .replace('<br>', '\n')
                        .replace('<br/>', '\n')
                        .replace('<br />', '\n')
                        .replace('<p>', '')
                        .replace('</p>', '\n')
                        .strip())
                    
                    st.markdown(f"<div class='update-description'>{clean_description}</div>",
                              unsafe_allow_html=True)

                    if item.recovered_amount or item.remaining_amount:
                        col1, col2 = st.columns(2)
                        with col1:
                            if item.recovered_amount is not None:
                                try:
                                    st.metric("Recovered Amount", 
                                            f"€{float(item.recovered_amount):,.2f}")
                                except (ValueError, TypeError):
                                    st.metric("Recovered Amount", "€0.00")
                        with col2:
                            if item.remaining_amount is not None:
                                try:
                                    st.metric("Remaining Amount", 
                                            f"€{float(item.remaining_amount):,.2f}")
                                except (ValueError, TypeError):
                                    st.metric("Remaining Amount", "€0.00")

                    if item.recovery_year_from and item.recovery_year_to:
                        st.info(f"Expected Recovery Timeline: "
                               f"{item.recovery_year_from} - {item.recovery_year_to}")

                    st.markdown("---")

def main():
    """Main application entry point"""
    try:
        dashboard = DashboardManager()
        dashboard.render_dashboard()
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        st.error("⚠️ An error occurred while starting the application")

if __name__ == "__main__":
    main()