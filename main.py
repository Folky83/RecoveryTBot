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
CAMPAIGNS_FILE = os.path.join('data', 'campaigns.json')
COMPANY_URLS_FILE = os.path.join('data', 'company_urls_cache.json')
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
    
@dataclass
class Campaign:
    """Represents a Mintos campaign"""
    id: int
    name: str
    short_description: str
    valid_from: str
    valid_to: str
    image_url: str
    terms_conditions_link: str
    bonus_amount: Optional[str] = None
    required_principal: Optional[str] = None
    type: Optional[int] = None
    
@dataclass
class Company:
    """Represents a Mintos lending company"""
    id: str
    name: str
    url: str

class DashboardManager:
    """Manages dashboard data and rendering"""
    def __init__(self):
        self.data_manager = DataManager()
        self.updates: List[CompanyUpdate] = []
        self.campaigns: List[Campaign] = []
        self.companies: List[Company] = []
        self._load_updates()
        self._load_campaigns()
        self._load_companies()

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
            
    def _load_campaigns(self) -> None:
        """Load campaigns from file"""
        try:
            if not os.path.exists(CAMPAIGNS_FILE):
                logger.warning(f"Campaigns file not found: {CAMPAIGNS_FILE}")
                return

            with open(CAMPAIGNS_FILE, 'r') as f:
                raw_campaigns = json.load(f)

            self.campaigns = []
            for campaign in raw_campaigns:
                if not campaign.get('id'):
                    continue
                    
                # Skip campaigns without a name
                name = campaign.get('name', '')
                if not name and campaign.get('identifier'):
                    name = f"Campaign {campaign.get('identifier')}"
                elif not name:
                    name = f"Campaign #{campaign.get('id')}"
                
                # Parse dates just to validate them
                try:
                    valid_from = campaign.get('validFrom', '')
                    valid_to = campaign.get('validTo', '')
                    
                    # Clean up empty or None values
                    bonus_amount = campaign.get('bonusAmount')
                    if not bonus_amount:
                        bonus_amount = None
                        
                    required_principal = campaign.get('requiredPrincipalExposure')
                    if not required_principal:
                        required_principal = None
                    
                    self.campaigns.append(Campaign(
                        id=campaign.get('id'),
                        name=name,
                        short_description=campaign.get('shortDescription', ''),
                        valid_from=valid_from,
                        valid_to=valid_to,
                        image_url=campaign.get('imageUrl', ''),
                        terms_conditions_link=campaign.get('termsConditionsLink', ''),
                        bonus_amount=bonus_amount,
                        required_principal=required_principal,
                        type=campaign.get('type')
                    ))
                except Exception as e:
                    logger.error(f"Error parsing campaign {campaign.get('id')}: {e}")
                    continue

            # Sort campaigns by end date (validTo)
            self.campaigns.sort(key=lambda x: x.valid_to, reverse=True)
            logger.info(f"Loaded {len(self.campaigns)} campaigns")
        except Exception as e:
            logger.error(f"Error loading campaigns: {e}", exc_info=True)
            self.campaigns = []
            
    def _load_companies(self) -> None:
        """Load company information from URL cache file"""
        try:
            if not os.path.exists(COMPANY_URLS_FILE):
                logger.warning(f"Company URLs file not found: {COMPANY_URLS_FILE}")
                return

            with open(COMPANY_URLS_FILE, 'r') as f:
                raw_companies = json.load(f)

            self.companies = []
            for company_id, company_data in raw_companies.items():
                self.companies.append(Company(
                    id=company_id,
                    name=company_data.get('name', company_id.replace('-', ' ').title()),
                    url=company_data.get('url', '')
                ))

            # Sort companies by name
            self.companies.sort(key=lambda x: x.name)
            logger.info(f"Loaded {len(self.companies)} companies from URL cache")
        except Exception as e:
            logger.error(f"Error loading company URLs: {e}", exc_info=True)
            self.companies = []

    def render_dashboard(self) -> None:
        """Render the main dashboard"""
        try:
            self._set_page_config()
            self._apply_custom_css()
            self._render_header()

            # Create tabs for recovery updates, company information, and campaigns
            tab1, tab2, tab3 = st.tabs(["Recovery Updates", "Lending Companies", "Active Campaigns"])
            
            with tab1:
                if not self.updates:
                    self._render_no_updates_message()
                else:
                    selected_company = self._render_company_filter()
                    self._render_updates(selected_company)
            
            with tab2:
                self._render_companies()
            
            with tab3:
                if not self.campaigns:
                    st.warning("⚠️ No active campaigns available yet.")
                    st.info("The Telegram bot will automatically collect campaign data.")
                else:
                    self._render_campaigns()

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
        """Apply minimal CSS for formatting"""
        st.markdown("""
            <style>
            .company-header {
                font-size: 24px;
                font-weight: bold;
                margin: 10px 0;
            }
            .update-date {
                font-size: 0.9em;
            }
            .update-description {
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
        
        return st.sidebar.selectbox("Select Company", companies, 
                                   help="Filter updates by company name")

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
                    
    def _render_companies(self) -> None:
        """Render company information"""
        st.subheader("🏢 Mintos Lending Companies")
        
        if not self.companies:
            st.warning("⚠️ No company information available yet.")
            st.info("The Telegram bot will automatically collect company data.")
            return
        
        # Add search filter
        search_term = st.text_input("🔍 Search companies by name", 
                                  help="Filter companies by name (case insensitive)")
        
        # Filter companies based on search term
        filtered_companies = self.companies
        if search_term:
            filtered_companies = [
                company for company in self.companies
                if search_term.lower() in company.name.lower()
            ]
        
        # Display company count
        st.write(f"Showing {len(filtered_companies)} companies out of {len(self.companies)} total companies")
        
        # Create a grid layout for companies
        cols_per_row = 3
        
        # Calculate how many rows we need
        for i in range(0, len(filtered_companies), cols_per_row):
            # Create columns for each row
            cols = st.columns(cols_per_row)
            
            # Fill columns with companies
            for j in range(cols_per_row):
                idx = i + j
                if idx < len(filtered_companies):
                    company = filtered_companies[idx]
                    with cols[j]:
                        with st.expander(f"{company.name}", expanded=False):
                            st.markdown(f"**ID:** {company.id}")
                            
                            # Only display URL if it's available
                            if company.url:
                                # Format URL as a clickable link
                                st.markdown(f"**URL:** [{company.url}]({company.url})")
                            
                            # Add button to view documents
                            if st.button("View Documents", key=f"docs_{company.id}"):
                                # This would open a modal or redirect to documents page
                                # For now, just show a message
                                st.info(f"Document viewer for {company.name} is not implemented yet.")
                                
                            # Display updates for this company if available
                            company_updates = [u for u in self.updates if u.company_name.lower() == company.name.lower()]
                            if company_updates:
                                st.markdown("---")
                                st.markdown("**Recent Updates:**")
                                
                                # Show most recent update
                                update = company_updates[0]
                                if update.items:
                                    recent_item = update.items[0]
                                    st.markdown(f"*{recent_item.date}* - {recent_item.status or 'No Status'}")
                                    
                                    # Truncate description if it's too long
                                    desc = recent_item.description or ""
                                    if len(desc) > 100:
                                        desc = desc[:97] + "..."
                                    
                                    # Clean HTML content in description
                                    clean_description = (desc
                                        .replace('\u003C', '<')
                                        .replace('\u003E', '>')
                                        .replace('&#39;', "'")
                                        .replace('&rsquo;', "'")
                                        .replace('&euro;', '€')
                                        .replace('&nbsp;', ' ')
                                        .replace('<br>', ' ')
                                        .replace('<br/>', ' ')
                                        .replace('<br />', ' ')
                                        .replace('<p>', '')
                                        .replace('</p>', ' ')
                                        .strip())
                                    
                                    st.markdown(clean_description)
                                    
                                    # Add link to updates tab
                                    st.markdown("[See all updates](#Recovery-Updates)")
    
    def _render_campaigns(self) -> None:
        """Render active campaigns"""
        st.subheader("🎯 Active Mintos Campaigns")
        
        # Filter to show only active campaigns using the current date
        now = datetime.now()
        
        # Format the date as ISO format for comparison
        now_str = now.strftime("%Y-%m-%dT%H:%M:%S")
        
        # Filter out "Special Promotion" campaigns (based on type)
        # and only show active campaigns
        # Common campaign types:
        # - Type 1: Referral programs
        # - Type 2: Cashback campaigns
        # - Type 4: Special promotions (hidden)
        active_campaigns = [c for c in self.campaigns 
                           if c.valid_from <= now_str <= c.valid_to and c.type != 4]
        
        st.write(f"Showing {len(active_campaigns)} active campaigns (excluding special promotions) out of {len(self.campaigns)} total campaigns")
        
        # Display each campaign in a card-like expander
        for campaign in active_campaigns:
            with st.expander(f"{campaign.name or f'Campaign #{campaign.id}'}"):
                cols = st.columns([2, 1])
                
                with cols[0]:
                    # Format dates nicely
                    valid_from = datetime.fromisoformat(campaign.valid_from.replace('Z', '+00:00'))
                    valid_to = datetime.fromisoformat(campaign.valid_to.replace('Z', '+00:00'))
                    
                    # Clean HTML content for display
                    clean_description = ""
                    if campaign.short_description:
                        clean_description = campaign.short_description.replace('<p>', '').replace('</p>', '\n\n')
                        clean_description = (clean_description
                            .replace('<strong>', '**').replace('</strong>', '**')
                            .replace('<br />', '\n').replace('<br/>', '\n').replace('<br>', '\n')
                            .replace('&rsquo;', "'").replace('&euro;', '€').replace('&nbsp;', ' ')
                            .replace('<ul>', '').replace('</ul>', '')
                            .replace('<li>', '• ').replace('</li>', '\n'))
                        
                    st.markdown(clean_description, unsafe_allow_html=False)
                    
                    st.markdown("---")
                    st.caption(f"**Campaign period:** {valid_from.strftime('%d %b %Y')} - {valid_to.strftime('%d %b %Y')}")
                    
                    if campaign.bonus_amount:
                        st.success(f"Bonus: €{campaign.bonus_amount}")
                    
                    if campaign.required_principal:
                        st.info(f"Required investment: €{float(campaign.required_principal):,.2f}")
                    
                    if campaign.terms_conditions_link:
                        st.markdown(f"[Terms & Conditions]({campaign.terms_conditions_link})")
                
                with cols[1]:
                    if campaign.image_url:
                        st.image(campaign.image_url, use_column_width=True)

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