#!/usr/bin/env python3
import os
import sys
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import hashlib
import json
from typing import Dict, Any, List

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('document_metadata_test')

def generate_document_id(title: str, url: str, date: str) -> str:
    """Generate a unique ID for a document based on its properties"""
    hash_input = f"{title}|{url}|{date}".encode('utf-8')
    return hashlib.md5(hash_input).hexdigest()

def detect_document_type(title: str, url: str) -> str:
    """Detect the type of document based on title and URL"""
    title_lower = title.lower()
    url_lower = url.lower()
    
    # Financial documents
    if any(term in title_lower for term in ['financial', 'finance', 'statement', 'report', 'balance sheet', 
                                           'income statement', 'cash flow', 'annual report',
                                           'quarterly report', 'profit', 'loss']):
        return 'financial'
        
    # Presentation documents
    if any(term in title_lower for term in ['presentation', 'overview', 'introduction', 'about',
                                          'company profile', 'investor']):
        return 'presentation'
        
    # Regulatory documents
    if any(term in title_lower for term in ['regulatory', 'regulation', 'compliance', 'law', 'legal',
                                          'terms', 'conditions', 'policy', 'procedure']):
        return 'regulatory'
        
    # Agreement documents
    if any(term in title_lower for term in ['agreement', 'contract', 'terms', 'loan agreement', 
                                          'assignment', 'guarantee']):
        return 'agreement'
        
    # Default to generic document
    return 'general'

def detect_country_info(title: str, url: str) -> Dict[str, Any]:
    """Detect country information in document title or URL"""
    title_lower = title.lower()
    url_lower = url.lower()
    
    country_data = {}
    
    # List of countries to check for
    countries = [
        # Europe
        'latvia', 'estonia', 'lithuania', 'poland', 'germany', 'france', 'spain', 'italy',
        'uk', 'united kingdom', 'great britain', 'netherlands', 'belgium', 'luxembourg',
        'sweden', 'norway', 'finland', 'denmark', 'czech', 'slovakia', 'austria', 'switzerland',
        'hungary', 'romania', 'bulgaria', 'greece', 'croatia', 'slovenia', 'serbia', 'bosnia',
        'albania', 'macedonia', 'montenegro', 'moldova', 'ukraine', 'belarus', 'russia',
        
        # Asia
        'turkey', 'kazakhstan', 'uzbekistan', 'kyrgyzstan', 'tajikistan', 'turkmenistan',
        'azerbaijan', 'armenia', 'georgia', 'china', 'japan', 'korea', 'india', 'pakistan',
        'bangladesh', 'vietnam', 'thailand', 'malaysia', 'indonesia', 'philippines', 'singapore',
        
        # Africa
        'egypt', 'morocco', 'algeria', 'tunisia', 'libya', 'nigeria', 'south africa', 'kenya',
        'ethiopia', 'ghana', 'tanzania', 'uganda',
        
        # Americas
        'usa', 'united states', 'canada', 'mexico', 'brazil', 'argentina', 'chile', 
        'colombia', 'peru', 'venezuela', 'ecuador', 'bolivia'
    ]
    
    # Regions
    regions = [
        'europe', 'western europe', 'eastern europe', 'central europe', 'northern europe', 'southern europe',
        'asia', 'east asia', 'south asia', 'southeast asia', 'central asia', 'middle east',
        'africa', 'north africa', 'sub-saharan africa', 'west africa', 'east africa', 'southern africa',
        'americas', 'north america', 'south america', 'central america', 'latin america',
        'oceania', 'australia', 'new zealand', 'pacific'
    ]
    
    # Check for country mentions
    detected_countries = []
    for country in countries:
        if country in title_lower or country in url_lower:
            detected_countries.append(country)
            
    # Check for region mentions
    detected_regions = []
    for region in regions:
        if region in title_lower or region in url_lower:
            detected_regions.append(region)
            
    # If we found country information, return it
    if detected_countries or detected_regions:
        country_data = {
            'is_country_specific': True,
            'countries': detected_countries,
            'regions': detected_regions
        }
    else:
        country_data = {
            'is_country_specific': False
        }
        
    return country_data

def format_document_message(document: Dict[str, Any]) -> str:
    """Format a notification message for a new document"""
    company_name = document.get('company_name', 'Unknown Company')
    title = document.get('title', 'Untitled Document')
    date = document.get('date', 'Unknown date')
    url = document.get('url', '#')
    document_type = document.get('document_type', 'general')
    country_info = document.get('country_info', {})
    
    # Determine emoji based on document type
    emoji = "📄"
    if document_type == "financial":
        emoji = "💰"
    elif document_type == "presentation":
        emoji = "📊"
    elif document_type == "regulatory":
        emoji = "⚖️"
    elif document_type == "agreement":
        emoji = "📝"
        
    # Create message with metadata
    message = (
        f"{emoji} <b>New {document_type.capitalize()} Document</b>\n\n"
        f"🏢 <b>Company:</b> {company_name}\n"
        f"📋 <b>Title:</b> {title}\n"
        f"📅 <b>Published:</b> {date}\n"
    )
    
    # Add country-specific information if available
    if country_info and country_info.get('is_country_specific', False):
        countries = country_info.get('countries', [])
        regions = country_info.get('regions', [])
        
        if countries:
            countries_str = ", ".join(country.capitalize() for country in countries)
            message += f"🌍 <b>Countries:</b> {countries_str}\n"
            
        if regions:
            regions_str = ", ".join(region.capitalize() for region in regions)
            message += f"🗺️ <b>Regions:</b> {regions_str}\n"
    
    # Add download link
    message += f"\n<a href='{url}'>📥 Download Document</a>"
    
    return message

def test_document_metadata():
    """Test document metadata extraction and formatting"""
    logger.info("Testing document metadata extraction and message formatting")
    
    # Test documents representing different types and country-specific information
    test_documents = [
        {
            "title": "Financial Report 2024 Q1",
            "url": "https://example.com/financial-report-2024-q1.pdf",
            "date": "2024-03-15",
            "company_name": "TestCorp Finance"
        },
        {
            "title": "Company Presentation",
            "url": "https://example.com/company-presentation.pdf",
            "date": "2024-02-28",
            "company_name": "InvestGroup"
        },
        {
            "title": "Regulatory Compliance Update",
            "url": "https://example.com/regulatory-update.pdf",
            "date": "2024-01-10",
            "company_name": "LegalFinance"
        },
        {
            "title": "Loan Agreement Terms",
            "url": "https://example.com/loan-agreement.pdf",
            "date": "2024-03-01",
            "company_name": "EasyLoans"
        },
        {
            "title": "European Market Overview",
            "url": "https://example.com/european-market.pdf",
            "date": "2024-02-15",
            "company_name": "GlobalInsights"
        },
        {
            "title": "Operations in Turkey and Georgia",
            "url": "https://example.com/turkey-georgia-operations.pdf",
            "date": "2024-03-10",
            "company_name": "ExpansionGroup"
        },
        {
            "title": "Investment Opportunities in Western Europe",
            "url": "https://example.com/western-europe-investments.pdf",
            "date": "2024-01-30",
            "company_name": "EuroInvest"
        }
    ]
    
    logger.info(f"Processing {len(test_documents)} test documents")
    
    # Process each document and enhance with metadata
    enhanced_documents = []
    for doc in test_documents:
        # Generate a unique ID
        doc_id = generate_document_id(doc['title'], doc['url'], doc['date'])
        
        # Detect document type
        doc_type = detect_document_type(doc['title'], doc['url'])
        
        # Detect country information
        country_info = detect_country_info(doc['title'], doc['url'])
        
        # Create enhanced document
        enhanced_doc = {
            **doc,
            'id': doc_id,
            'document_type': doc_type,
            'country_info': country_info
        }
        
        enhanced_documents.append(enhanced_doc)
        
        # Log detection results
        logger.info(f"Document: {doc['title']}")
        logger.info(f"  Type detected: {doc_type}")
        if country_info.get('is_country_specific', False):
            countries = country_info.get('countries', [])
            regions = country_info.get('regions', [])
            if countries:
                logger.info(f"  Countries detected: {', '.join(countries)}")
            if regions:
                logger.info(f"  Regions detected: {', '.join(regions)}")
        else:
            logger.info("  No country/region information detected")
            
        # Format message and display
        message = format_document_message(enhanced_doc)
        logger.info(f"Formatted message:\n{message}\n")
    
    logger.info("Test completed")

if __name__ == "__main__":
    test_document_metadata()