import streamlit as st
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from urllib.parse import urljoin, urlparse
from collections import deque, Counter
import json
import io
import random

# Configure Streamlit page
st.set_page_config(
    page_title="Company Scraper & SEO Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

def get_curated_company_urls():
    """Return curated list of Dubai business directories and company websites"""
    return {
        'Business Directories': [
            'https://www.dubaicompanies.ae',
            'https://www.dubaichamber.com/find-a-member',
            'https://www.yellowpages.ae/dubai',
            'https://www.zawya.com/en/companies',
            'https://gulfnews.com/business',
            'https://www.trade.gov.ae/directory',
            'https://www.godubai.com/citylife/business_directory.asp',
        ],
        'Sales & Marketing Companies': [
            'https://www.salesforce.com/ae/',
            'https://www.hubspot.com',
            'https://www.digitalboom.ae',
            'https://www.nexa.ae',
            'https://www.redseadigital.com',
            'https://www.impact.ae',
            'https://www.elephantroom.ae',
            'https://www.webpuppies.com.au',
            'https://www.gmgme.com',
            'https://www.bluechipdubai.com',
        ],
        'Business Services': [
            'https://www.pwc.com/m1/en/countries/uae.html',
            'https://www2.deloitte.com/ae/en.html',
            'https://www.ey.com/en_ae',
            'https://kpmg.com/ae/en/home.html',
            'https://www.mckinsey.com/ae/our-people/middle-east',
            'https://www.bcg.com/offices/dubai',
        ],
        'Technology Companies': [
            'https://www.microsoft.com/en-ae/',
            'https://www.oracle.com/ae/',
            'https://www.ibm.com/ae-en',
            'https://aws.amazon.com/contact-us/middle-east/',
            'https://www.sap.com/middle-east/index.html',
        ]
    }

def extract_company_links_from_directory(url, max_links=20):
    """Extract company links from business directory pages"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    company_links = []
    
    try:
        time.sleep(random.uniform(2, 4))
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Common patterns for company links in directories
        link_selectors = [
            'a[href*="company"]',
            'a[href*="business"]', 
            'a[href*="profile"]',
            'a[href*="detail"]',
            '.company-name a',
            '.business-name a',
            '.listing a',
            'h2 a', 'h3 a',
            '.title a'
        ]
        
        for selector in link_selectors:
            links = soup.select(selector)
            for link in links[:max_links]:
                href = link.get('href')
                if href:
                    full_url = urljoin(url, href)
                    title = link.get_text(strip=True) or link.get('title', 'Company')
                    
                    # Filter for likely company pages
                    if (len(title) > 3 and 
                        not any(skip in full_url.lower() for skip in ['login', 'register', 'search', 'contact-us', 'about-us']) and
                        full_url not in company_links):
                        company_links.append((full_url, title, f"Found via {urlparse(url).netloc}"))
                        
                if len(company_links) >= max_links:
                    break
            if len(company_links) >= max_links:
                break
                
    except Exception as e:
        st.warning(f"Could not extract from {url}: {str(e)[:50]}")
    
    return company_links

def extract_emails(text):
    """Extract email addresses from text"""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = list(set(re.findall(email_pattern, text)))
    return emails

def extract_phones(text):
    """Extract phone numbers from text"""
    phone_patterns = [
        r'\+971[\s-]?\d{1,2}[\s-]?\d{3}[\s-]?\d{4}',  # UAE format
        r'\b\d{2}[\s-]?\d{3}[\s-]?\d{4}\b',  # Local format
        r'\+\d{1,3}[\s-]?\d{1,4}[\s-]?\d{1,4}[\s-]?\d{1,4}',  # International
    ]
    
    phones = []
    for pattern in phone_patterns:
        phones.extend(re.findall(pattern, text))
    
    return list(set(phones))

def scrape_page_content(url, headers, timeout=10):
    """Scrape content from a single page"""
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        return soup, response.text
    except Exception as e:
        return None, None

def extract_seo_data(soup, url):
    """Extract comprehensive SEO data"""
    seo_data = {
        'meta_title': '',
        'meta_title_length': 0,
        'meta_description': '',
        'meta_description_length': 0,
        'h1_tags': [],
        'h2_tags': [],
        'img_count': 0,
        'img_with_alt': 0,
        'img_without_alt': 0,
        'word_count': 0,
        'social_media_links': {}
    }
    
    # Extract title
    title_tag = soup.find('title')
    if title_tag:
        seo_data['meta_title'] = title_tag.get_text(strip=True)
        seo_data['meta_title_length'] = len(seo_data['meta_title'])
    
    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        seo_data['meta_description'] = meta_desc.get('content', '')
        seo_data['meta_description_length'] = len(seo_data['meta_description'])
    
    # Extract headings
    seo_data['h1_tags'] = [h.get_text(strip=True) for h in soup.find_all('h1')][:5]
    seo_data['h2_tags'] = [h.get_text(strip=True) for h in soup.find_all('h2')][:10]
    
    # Analyze images
    images = soup.find_all('img')
    seo_data['img_count'] = len(images)
    for img in images:
        if img.get('alt'):
            seo_data['img_with_alt'] += 1
        else:
            seo_data['img_without_alt'] += 1
    
    # Word count
    text_content = soup.get_text()
    seo_data['word_count'] = len(text_content.split())
    
    # Social media links
    social_platforms = ['facebook', 'twitter', 'linkedin', 'instagram', 'youtube']
    for platform in social_platforms:
        social_link = soup.find('a', href=re.compile(f'{platform}.com', re.I))
        if social_link:
            seo_data['social_media_links'][platform] = social_link.get('href', '')
    
    return seo_data

def scrape_company_comprehensive(url, company_name, source, max_pages=2):
    """Comprehensive company scraping"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    all_emails = set()
    all_phones = set()
    company_info = {
        "Company Name": company_name,
        "About": "N/A",
        "Services": "N/A"
    }
    
    pages_scraped = 0
    seo_data = {}
    
    try:
        time.sleep(random.uniform(1, 3))
        soup, page_text = scrape_page_content(url, headers)
        
        if not soup:
            return None
            
        pages_scraped = 1
        
        # Extract SEO data
        seo_data = extract_seo_data(soup, url)
        
        # Extract contact info
        if page_text:
            all_emails.update(extract_emails(page_text))
            all_phones.update(extract_phones(page_text))
        
        # Extract company name from page if not provided
        if company_info["Company Name"] == company_name:
            title_tag = soup.find('title')
            if title_tag:
                company_info["Company Name"] = title_tag.get_text(strip=True)[:100]
        
        # Look for about section
        about_text = ""
        about_selectors = [
            'div[class*="about"]', 'section[class*="about"]',
            'div[id*="about"]', 'section[id*="about"]',
            'p:contains("about")', '.description', '.overview'
        ]
        
        for selector in about_selectors:
            try:
                about_elem = soup.select_one(selector)
                if about_elem:
                    text = about_elem.get_text(strip=True)
                    if len(text) > len(about_text):
                        about_text = text
            except:
                continue
        
        if about_text and len(about_text) > 50:
            company_info["About"] = about_text[:500]
        
        # Look for services
        services_keywords = ['service', 'solution', 'offer', 'expertise', 'specialize']
        services_text = ""
        
        for keyword in services_keywords:
            elements = soup.find_all(string=re.compile(keyword, re.I))
            for element in elements[:3]:
                if element.parent:
                    text = element.parent.get_text(strip=True)
                    if len(text) > 30:
                        services_text += text + "; "
        
        if services_text:
            company_info["Services"] = services_text[:400]
        
    except Exception as e:
        return None
    
    # Calculate SEO score
    seo_score = 0
    if seo_data.get('meta_title') and 30 <= seo_data['meta_title_length'] <= 60:
        seo_score += 20
    if seo_data.get('meta_description') and 120 <= seo_data['meta_description_length'] <= 160:
        seo_score += 20
    if seo_data.get('h1_tags'):
        seo_score += 15
    if seo_data.get('img_with_alt', 0) > 0:
        seo_score += 15
    if seo_data.get('social_media_links'):
        seo_score += 10
    if len(all_emails) > 0:
        seo_score += 10
    if len(all_phones) > 0:
        seo_score += 10
    
    result = {
        "URL": url,
        "Source": source,
        "Pages Scraped": pages_scraped,
        "Company Name": company_info["Company Name"],
        "About": company_info["About"],
        "Services": company_info["Services"],
        "Emails": '; '.join(list(all_emails)[:3]) if all_emails else "N/A",
        "Phones": '; '.join(list(all_phones)[:3]) if all_phones else "N/A",
        "Total Emails Found": len(all_emails),
        "Total Phones Found": len(all_phones),
        "SEO Score": seo_score,
        "Meta Title": seo_data.get('meta_title', 'N/A'),
        "Meta Description": seo_data.get('meta_description', 'N/A'),
        "H1 Tags": ', '.join(seo_data.get('h1_tags', [])),
        "Word Count": seo_data.get('word_count', 0),
        "Images Total": seo_data.get('img_count', 0),
        "Images with Alt": seo_data.get('img_with_alt', 0),
        "Social Media": ', '.join([f"{k}: {v}" for k, v in seo_data.get('social_media_links', {}).items()]) if seo_data.get('social_media_links') else "N/A"
    }
    
    return result

def main_streamlit():
    """Main Streamlit application"""
    
    st.markdown('<div class="main-header">🔍 Company Scraper & SEO Analyzer</div>', unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.header("Configuration")
    
    # Analysis mode selection
    analysis_mode = st.sidebar.selectbox(
        "Analysis Mode",
        ["Direct Company URLs", "Directory Mining", "Curated Lists"]
    )
    
    if analysis_mode == "Direct Company URLs":
        st.sidebar.subheader("Direct URL Input")
        url_input = st.sidebar.text_area(
            "Enter company URLs (one per line)",
            value="https://www.salesforce.com/ae/\nhttps://www.hubspot.com\nhttps://www.digitalboom.ae",
            help="Enter direct URLs to company websites"
        )
        
        company_urls = []
        if url_input:
            urls = [url.strip() for url in url_input.split('\n') if url.strip()]
            for url in urls:
                if url.startswith('http'):
                    company_name = urlparse(url).netloc.replace('www.', '').split('.')[0].title()
                    company_urls.append((url, company_name, "Direct Input"))
        
        max_companies = len(company_urls)
        
    elif analysis_mode == "Directory Mining":
        st.sidebar.subheader("Directory Mining")
        curated_urls = get_curated_company_urls()
        
        selected_directories = st.sidebar.multiselect(
            "Select Business Directories",
            list(curated_urls.keys()),
            default=["Business Directories"]
        )
        
        max_per_directory = st.sidebar.slider("Max companies per directory", 5, 20, 10)
        company_urls = []
        
        if selected_directories:
            for category in selected_directories:
                for directory_url in curated_urls[category][:2]:  # Limit to 2 directories per category
                    st.sidebar.info(f"Mining: {directory_url}")
                    extracted = extract_company_links_from_directory(directory_url, max_per_directory)
                    company_urls.extend(extracted)
        
        max_companies = len(company_urls)
        
    else:  # Curated Lists
        st.sidebar.subheader("Curated Company Lists")
        curated_urls = get_curated_company_urls()
        
        selected_categories = st.sidebar.multiselect(
            "Select Categories",
            list(curated_urls.keys()),
            default=["Sales & Marketing Companies"]
        )
        
        company_urls = []
        for category in selected_categories:
            for url in curated_urls[category]:
                company_name = urlparse(url).netloc.replace('www.', '').split('.')[0].title()
                company_urls.append((url, company_name, category))
        
        max_companies = len(company_urls)
    
    max_companies_to_analyze = st.sidebar.slider(
        "Max companies to analyze", 
        1, 
        min(max_companies, 50), 
        min(max_companies, 20)
    )
    
    # Main content
    st.subheader(f"Ready to analyze {len(company_urls)} companies")
    
    if company_urls:
        # Show preview
        with st.expander("Preview Companies to Analyze"):
            preview_df = pd.DataFrame(company_urls[:10], columns=["URL", "Company", "Source"])
            st.dataframe(preview_df)
    
    if st.button("🚀 Start Company Analysis", type="primary"):
        if not company_urls:
            st.error("No companies found to analyze")
            return
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        all_data = []
        companies_to_process = company_urls[:max_companies_to_analyze]
        
        for i, (url, company_name, source) in enumerate(companies_to_process):
            status_text.text(f"Analyzing {i+1}/{len(companies_to_process)}: {company_name}")
            progress_bar.progress((i + 1) / len(companies_to_process))
            
            result = scrape_company_comprehensive(url, company_name, source)
            
            if result:
                all_data.append(result)
        
        status_text.text("Analysis complete!")
        
        if all_data:
            # Create DataFrame
            df = pd.DataFrame(all_data)
            
            # Calculate quality score
            df['quality_score'] = (
                (df['Total Emails Found'] > 0).astype(int) * 3 +
                (df['Total Phones Found'] > 0).astype(int) * 3 +
                (df['Services'] != 'N/A').astype(int) * 2 +
                (df['About'] != 'N/A').astype(int) +
                df['SEO Score'] / 10
            )
            df = df.sort_values('quality_score', ascending=False)
            
            # Display results
            st.markdown('<div class="section-header">📊 Analysis Results</div>', unsafe_allow_html=True)
            
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Companies Analyzed", len(df))
            with col2:
                st.metric("With Email", sum(df['Total Emails Found'] > 0))
            with col3:
                st.metric("With Phone", sum(df['Total Phones Found'] > 0))
            with col4:
                st.metric("Avg SEO Score", f"{df['SEO Score'].mean():.1f}")
            
            # Top companies
            st.subheader("🏆 Top Companies")
            for idx, row in df.head(5).iterrows():
                with st.expander(f"#{idx + 1}: {row['Company Name']} (Quality: {row['quality_score']:.1f})"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Contact Info:**")
                        if row['Emails'] != 'N/A':
                            st.write(f"📧 {row['Emails']}")
                        if row['Phones'] != 'N/A':
                            st.write(f"📞 {row['Phones']}")
                        st.write(f"🌐 {row['URL']}")
                        st.write(f"📊 SEO Score: {row['SEO Score']}/100")
                    
                    with col2:
                        st.write("**About:**")
                        if row['About'] != 'N/A':
                            st.write(row['About'][:200] + "...")
                        st.write("**Services:**")
                        if row['Services'] != 'N/A':
                            st.write(row['Services'][:200] + "...")
            
            # Full data
            st.subheader("📋 Complete Data")
            st.dataframe(df)
            
            # Download
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv_buffer.getvalue(),
                file_name=f"company_analysis_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.error("No data was successfully collected")

if __name__ == "__main__":
    main_streamlit()