import streamlit as st
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from urllib.parse import urljoin, urlparse
from collections import deque
import io
import random
from duckduckgo_search import DDGS

# Configure Streamlit page
st.set_page_config(
    page_title="Deep Company Scraper",
    page_icon="🕵️",
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
    .metric-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

def search_companies_duckduckgo(query, max_results=20):
    """Search for companies using DuckDuckGo"""
    urls = []
    titles = []
    snippets = []

    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)

        for result in results:
            urls.append(result['href'])
            titles.append(result.get('title', 'N/A'))
            snippets.append(result.get('body', 'N/A'))

    except Exception as e:
        st.error(f"Search error: {e}")

    return urls, titles, snippets

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

def is_valid_internal_link(url, base_domain):
    """Check if a URL is a valid internal link"""
    try:
        parsed = urlparse(url)
        base_parsed = urlparse(base_domain)

        if parsed.netloc != base_parsed.netloc and parsed.netloc != '':
            return False

        avoid_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.doc', '.docx', '.xls', '.xlsx']
        if any(url.lower().endswith(ext) for ext in avoid_extensions):
            return False

        avoid_patterns = ['#', 'javascript:', 'mailto:', 'tel:', 'whatsapp:', 'linkedin.com', 'facebook.com', 'twitter.com']
        if any(pattern in url.lower() for pattern in avoid_patterns):
            return False

        return True
    except:
        return False

def get_internal_links(soup, base_url, max_links=10):
    """Extract internal links from a page"""
    internal_links = set()

    for link in soup.find_all('a', href=True):
        href = link['href']
        full_url = urljoin(base_url, href)

        if is_valid_internal_link(full_url, base_url):
            internal_links.add(full_url)

    # Prioritize important pages
    priority_keywords = ['about', 'service', 'product', 'contact', 'solution', 'portfolio', 'client', 'team']
    prioritized_links = []
    other_links = []

    for link in internal_links:
        if any(keyword in link.lower() for keyword in priority_keywords):
            prioritized_links.append(link)
        else:
            other_links.append(link)

    return (prioritized_links + other_links)[:max_links]

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

def extract_structured_content(soup):
    """Extract structured content from a page"""
    content = {
        'headings': [],
        'paragraphs': [],
        'lists': []
    }

    # Extract headings
    for i in range(1, 4):
        headings = soup.find_all(f'h{i}')
        content['headings'].extend([h.get_text(strip=True) for h in headings[:5]])

    # Extract paragraphs
    paragraphs = soup.find_all('p')
    content['paragraphs'] = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50][:10]

    # Extract lists
    lists = soup.find_all('ul')
    for ul in lists[:3]:
        items = [li.get_text(strip=True) for li in ul.find_all('li')[:5]]
        if items:
            content['lists'].extend(items)

    return content

def scrape_company_deep(base_url, company_name, source, max_pages=5, timeout=10):
    """Deep scrape a company website by visiting multiple internal pages"""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # Initialize data collection
    all_emails = set()
    all_phones = set()
    all_services = []
    all_addresses = []
    all_text_content = []
    company_info = {
        "Company Name": company_name,
        "About": "N/A",
        "Services": "N/A",
        "Products": "N/A",
        "Clients": "N/A",
        "Team": "N/A"
    }

    # Track visited URLs
    visited_urls = set()
    urls_to_visit = deque([base_url])
    pages_scraped = 0

    while urls_to_visit and pages_scraped < max_pages:
        current_url = urls_to_visit.popleft()

        if current_url in visited_urls:
            continue

        visited_urls.add(current_url)

        # Add delay to be respectful
        time.sleep(random.uniform(1, 2))

        # Scrape the page
        soup, page_text = scrape_page_content(current_url, headers, timeout)

        if not soup:
            continue

        pages_scraped += 1

        # Extract emails and phones from this page
        if page_text:
            all_emails.update(extract_emails(page_text))
            all_phones.update(extract_phones(page_text))
            all_text_content.append(page_text)

        # Extract structured content
        structured_content = extract_structured_content(soup)

        # Extract company name (from first page)
        if pages_scraped == 1:
            for tag in ['h1', 'title']:
                element = soup.find(tag)
                if element:
                    company_info["Company Name"] = element.get_text(strip=True)[:100]
                    break

        # Look for specific sections based on URL or content
        url_lower = current_url.lower()

        # About page
        if 'about' in url_lower or pages_scraped == 1:
            about_keywords = ['about', 'who we are', 'company', 'overview', 'mission', 'vision']
            for keyword in about_keywords:
                header = soup.find(['h1', 'h2', 'h3'], string=re.compile(keyword, re.I))
                if header:
                    next_elements = header.find_next_siblings(['p', 'div'])[:3]
                    about_text = ' '.join([elem.get_text(strip=True) for elem in next_elements])
                    if about_text and len(about_text) > len(company_info["About"]):
                        company_info["About"] = about_text[:500]

        # Services page
        if 'service' in url_lower or 'solution' in url_lower:
            service_sections = soup.find_all(['div', 'section'], class_=re.compile('service|solution', re.I))
            for section in service_sections[:3]:
                services = section.get_text(strip=True)
                if services:
                    all_services.append(services[:200])

            # Also collect from lists
            if structured_content['lists']:
                all_services.extend(structured_content['lists'])

        # Products page
        if 'product' in url_lower:
            product_sections = soup.find_all(['div', 'section'], class_=re.compile('product', re.I))
            products = []
            for section in product_sections[:3]:
                product_text = section.get_text(strip=True)
                if product_text:
                    products.append(product_text[:200])
            if products:
                company_info["Products"] = '; '.join(products[:5])

        # Contact page
        if 'contact' in url_lower:
            # Look for address
            address_keywords = ['address', 'location', 'office', 'dubai', 'uae', 'united arab emirates']
            for keyword in address_keywords:
                elements = soup.find_all(string=re.compile(keyword, re.I))
                for element in elements:
                    if element.parent:
                        address_text = element.parent.get_text(strip=True)
                        if 20 < len(address_text) < 200:
                            all_addresses.append(address_text)

        # Clients/Portfolio page
        if 'client' in url_lower or 'portfolio' in url_lower:
            client_sections = soup.find_all(['div', 'section'], class_=re.compile('client|portfolio', re.I))
            clients = []
            for section in client_sections[:2]:
                client_text = section.get_text(strip=True)
                if client_text:
                    clients.append(client_text[:200])
            if clients:
                company_info["Clients"] = '; '.join(clients[:3])

        # Team page
        if 'team' in url_lower or 'people' in url_lower:
            team_sections = soup.find_all(['div', 'section'], class_=re.compile('team|people|staff', re.I))
            team_info = []
            for section in team_sections[:2]:
                team_text = section.get_text(strip=True)
                if team_text:
                    team_info.append(team_text[:200])
            if team_info:
                company_info["Team"] = '; '.join(team_info[:2])

        # Get internal links for next iteration
        if pages_scraped < max_pages:
            internal_links = get_internal_links(soup, base_url, max_links=5)
            for link in internal_links:
                if link not in visited_urls:
                    urls_to_visit.append(link)

    # Compile final services list
    if all_services:
        unique_services = list(set(all_services))
        company_info["Services"] = '; '.join(unique_services[:15])

    # Extract social media links from all pages
    social_media = {}
    social_platforms = ['facebook', 'twitter', 'linkedin', 'instagram', 'youtube']

    for page_text in all_text_content:
        for platform in social_platforms:
            if platform not in social_media:
                pattern = rf'https?://(?:www\.)?{platform}\.com/[\w\-/]+'
                matches = re.findall(pattern, page_text, re.I)
                if matches:
                    social_media[platform] = matches[0]

    # Compile final results
    result = {
        "URL": base_url,
        "Source": source,
        "Pages Scraped": pages_scraped,
        "Company Name": company_info["Company Name"],
        "About": company_info["About"],
        "Services": company_info["Services"],
        "Products": company_info["Products"],
        "Emails": '; '.join(list(all_emails)[:5]) if all_emails else "N/A",
        "Phones": '; '.join(list(all_phones)[:5]) if all_phones else "N/A",
        "Address": all_addresses[0] if all_addresses else "N/A",
        "Clients": company_info["Clients"],
        "Team Info": company_info["Team"],
        "Social Media": ', '.join([f"{k}: {v}" for k, v in social_media.items()]) if social_media else "N/A",
        "Total Emails Found": len(all_emails),
        "Total Phones Found": len(all_phones),
        "Pages Visited": list(visited_urls)
    }

    return result

def get_curated_company_urls():
    """Return curated list of Dubai business directories and company websites"""
    return {
        'Business Directories': [
            'https://www.dubaicompanies.ae',
            'https://www.dubaichamber.com/find-a-member',
            'https://www.yellowpages.ae/dubai',
            'https://www.zawya.com/en/companies',
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
        ],
        'Business Services': [
            'https://www.pwc.com/m1/en/countries/uae.html',
            'https://www2.deloitte.com/ae/en.html',
            'https://www.ey.com/en_ae',
            'https://kpmg.com/ae/en/home.html',
        ],
        'Technology Companies': [
            'https://www.microsoft.com/en-ae/',
            'https://www.oracle.com/ae/',
            'https://www.ibm.com/ae-en',
            'https://aws.amazon.com/contact-us/middle-east/',
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
                    
                    if (len(title) > 3 and 
                        not any(skip in full_url.lower() for skip in ['login', 'register', 'search', 'contact-us', 'about-us']) and
                        full_url not in [cl[0] for cl in company_links]):
                        company_links.append((full_url, title, f"Found via {urlparse(url).netloc}"))
                        
                if len(company_links) >= max_links:
                    break
            if len(company_links) >= max_links:
                break
                
    except Exception as e:
        st.warning(f"Could not extract from {url}: {str(e)[:50]}")
    
    return company_links

def main_streamlit():
    """Main Streamlit application"""
    
    st.markdown('<div class="main-header">🕵️ Deep Company Scraper</div>', unsafe_allow_html=True)
    
    st.markdown("""
    This tool performs **deep scraping** of company websites by crawling multiple internal pages to extract comprehensive business information including contact details, services, team info, and more.
    """)
    
    # Sidebar
    st.sidebar.header("Deep Scraping Configuration")
    
    # Analysis mode selection
    analysis_mode = st.sidebar.selectbox(
        "Data Source",
        ["DuckDuckGo Search", "Direct Company URLs", "Directory Mining", "Curated Company Lists"]
    )
    
    # Deep scraping parameters
    st.sidebar.subheader("Scraping Depth")
    max_pages_per_site = st.sidebar.slider(
        "Max pages to scrape per company", 
        2, 10, 5,
        help="Number of internal pages to crawl per company website"
    )
    
    scraping_delay = st.sidebar.slider(
        "Delay between requests (seconds)", 
        1, 5, 2,
        help="Delay to be respectful to target websites"
    )
    
    timeout_setting = st.sidebar.slider(
        "Request timeout (seconds)", 
        5, 20, 10,
        help="How long to wait for each page to load"
    )
    
    if analysis_mode == "DuckDuckGo Search":
        st.sidebar.subheader("Search Configuration")
        search_queries = st.sidebar.text_area(
            "Search Queries (one per line)",
            value="sales companies Dubai UAE\nB2B sales agencies Dubai\nsales outsourcing companies Dubai\nsales consultancy Dubai UAE\ntop sales agencies Dubai",
            help="Enter search queries to find companies automatically"
        )
        
        max_results_per_query = st.sidebar.slider("Max results per query", 3, 10, 5)
        
        company_urls = []
        if search_queries and st.sidebar.button("🔎 Run Search"):
            queries = [q.strip() for q in search_queries.split('\n') if q.strip()]
            
            search_progress = st.progress(0)
            search_status = st.empty()
            seen_domains = set()
            
            for i, query in enumerate(queries):
                search_status.text(f"Searching: {query}")
                search_progress.progress((i + 1) / len(queries))
                
                urls, titles, snippets = search_companies_duckduckgo(query, max_results_per_query)
                
                for url, title, snippet in zip(urls, titles, snippets):
                    domain = urlparse(url).netloc
                    if domain not in seen_domains:
                        seen_domains.add(domain)
                        company_urls.append((url, title, f"Search: {query}"))
            
            search_status.text(f"Search completed! Found {len(company_urls)} unique companies")
            st.session_state.company_urls = company_urls
        
        if 'company_urls' in st.session_state:
            company_urls = st.session_state.company_urls
            max_companies = len(company_urls)
        else:
            company_urls = []
            max_companies = 0
    
    elif analysis_mode == "Direct Company URLs":
        st.sidebar.subheader("Direct URL Input")
        url_input = st.sidebar.text_area(
            "Enter company URLs (one per line)",
            value="https://www.salesforce.com/ae/\nhttps://www.hubspot.com\nhttps://www.digitalboom.ae\nhttps://www.nexa.ae",
            help="Paste direct URLs to company websites"
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
        st.sidebar.subheader("Business Directory Mining")
        curated_urls = get_curated_company_urls()
        
        selected_directories = st.sidebar.multiselect(
            "Select Business Directories",
            list(curated_urls.keys()),
            default=["Business Directories"],
            help="Select directories to extract company links from"
        )
        
        max_per_directory = st.sidebar.slider("Max companies per directory", 5, 30, 15)
        
        company_urls = []
        if selected_directories and st.sidebar.button("🔍 Extract from Directories"):
            extract_progress = st.progress(0)
            extract_status = st.empty()
            
            for i, category in enumerate(selected_directories):
                extract_status.text(f"Mining category: {category}")
                extract_progress.progress((i + 1) / len(selected_directories))
                
                for directory_url in curated_urls[category][:2]:
                    st.sidebar.info(f"Extracting from: {directory_url}")
                    extracted = extract_company_links_from_directory(directory_url, max_per_directory)
                    company_urls.extend(extracted)
            
            extract_status.text(f"Extraction completed! Found {len(company_urls)} companies")
            st.session_state.directory_companies = company_urls
        
        if 'directory_companies' in st.session_state:
            company_urls = st.session_state.directory_companies
            max_companies = len(company_urls)
        else:
            company_urls = []
            max_companies = 0
        
    else:  # Curated Lists
        st.sidebar.subheader("Curated Company Lists")
        curated_urls = get_curated_company_urls()
        
        selected_categories = st.sidebar.multiselect(
            "Select Categories",
            list(curated_urls.keys()),
            default=["Sales & Marketing Companies"],
            help="Select pre-curated company categories"
        )
        
        company_urls = []
        for category in selected_categories:
            for url in curated_urls[category]:
                company_name = urlparse(url).netloc.replace('www.', '').split('.')[0].title()
                company_urls.append((url, company_name, category))
        
        max_companies = len(company_urls)
    
    # Analysis parameters
    max_companies_to_analyze = st.sidebar.slider(
        "Max companies to analyze", 
        1, 
        min(max_companies, 30), 
        min(max_companies, 10) if max_companies > 0 else 1
    )
    
    # Main content
    if max_companies > 0:
        st.subheader(f"Ready to deep scrape {len(company_urls)} companies")
        
        # Show preview
        with st.expander("Preview Companies to Analyze"):
            preview_df = pd.DataFrame(company_urls[:15], columns=["URL", "Company", "Source"])
            st.dataframe(preview_df, use_container_width=True)
    
    if company_urls and st.button("🚀 Start Deep Scraping", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_placeholder = st.empty()
        
        all_data = []
        companies_to_process = company_urls[:max_companies_to_analyze]
        
        for i, (url, company_name, source) in enumerate(companies_to_process):
            status_text.text(f"Deep scraping {i+1}/{len(companies_to_process)}: {company_name}")
            progress_bar.progress((i + 1) / len(companies_to_process))
            
            result = scrape_company_deep(
                url, 
                company_name, 
                source, 
                max_pages=max_pages_per_site, 
                timeout=timeout_setting
            )
            
            if result:
                all_data.append(result)
                
                # Show live updates
                with results_placeholder.container():
                    st.write(f"✅ **{result['Company Name']}** - Found {result['Total Emails Found']} emails, {result['Total Phones Found']} phones across {result['Pages Scraped']} pages")
        
        status_text.text("🎉 Deep scraping complete!")
        
        if all_data:
            # Create DataFrame
            df = pd.DataFrame(all_data)
            
            # Calculate comprehensive quality score
            df['quality_score'] = (
                (df['Total Emails Found'] > 0).astype(int) * 4 +
                (df['Total Phones Found'] > 0).astype(int) * 4 +
                (df['Services'] != 'N/A').astype(int) * 3 +
                (df['Products'] != 'N/A').astype(int) * 2 +
                (df['About'] != 'N/A').astype(int) * 2 +
                (df['Clients'] != 'N/A').astype(int) * 2 +
                (df['Address'] != 'N/A').astype(int) * 2 +
                (df['Team Info'] != 'N/A').astype(int) * 1 +
                df['Pages Scraped'] * 0.5
            )
            df = df.sort_values('quality_score', ascending=False)
            
            # Display results
            st.markdown('<div class="section-header">📊 Deep Scraping Results</div>', unsafe_allow_html=True)
            
            # Enhanced metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Companies Scraped", len(df))
            with col2:
                st.metric("Total Pages Scraped", df['Pages Scraped'].sum())
            with col3:
                st.metric("With Email", sum(df['Total Emails Found'] > 0))
            with col4:
                st.metric("With Phone", sum(df['Total Phones Found'] > 0))
            with col5:
                st.metric("Avg Quality Score", f"{df['quality_score'].mean():.1f}")
            
            # Data quality breakdown
            st.subheader("📈 Data Quality Breakdown")
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Contact Information:**")
                st.write(f"- Companies with emails: {sum(df['Total Emails Found'] > 0)}/{len(df)}")
                st.write(f"- Companies with phones: {sum(df['Total Phones Found'] > 0)}/{len(df)}")
                st.write(f"- Companies with addresses: {sum(df['Address'] != 'N/A')}/{len(df)}")
                st.write(f"- Total unique emails found: {df['Total Emails Found'].sum()}")
                st.write(f"- Total unique phones found: {df['Total Phones Found'].sum()}")
            
            with col2:
                st.write("**Business Information:**")
                st.write(f"- Companies with services info: {sum(df['Services'] != 'N/A')}/{len(df)}")
                st.write(f"- Companies with products info: {sum(df['Products'] != 'N/A')}/{len(df)}")
                st.write(f"- Companies with about section: {sum(df['About'] != 'N/A')}/{len(df)}")
                st.write(f"- Companies with client info: {sum(df['Clients'] != 'N/A')}/{len(df)}")
                st.write(f"- Companies with team info: {sum(df['Team Info'] != 'N/A')}/{len(df)}")
            
            # Top companies with detailed information
            st.subheader("🏆 Top Companies (by Data Quality)")
            for idx, row in df.head(8).iterrows():
                with st.expander(f"#{idx + 1}: {row['Company Name']} (Quality Score: {row['quality_score']:.1f})"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write("**Contact Information:**")
                        if row['Emails'] != 'N/A':
                            st.write(f"📧 **Emails:** {row['Emails']}")
                        if row['Phones'] != 'N/A':
                            st.write(f"📞 **Phones:** {row['Phones']}")
                        if row['Address'] != 'N/A':
                            st.write(f"📍 **Address:** {row['Address'][:100]}...")
                        if row['Social Media'] != 'N/A':
                            st.write(f"🌐 **Social:** {row['Social Media']}")
                        
                        st.write(f"🔗 **URL:** {row['URL']}")
                        st.write(f"📄 **Pages Scraped:** {row['Pages Scraped']}")
                    
                    with col2:
                        st.write("**Business Information:**")
                        if row['About'] != 'N/A':
                            st.write(f"**About:** {row['About'][:200]}...")
                        if row['Services'] != 'N/A':
                            st.write(f"**Services:** {row['Services'][:200]}...")
                        if row['Products'] != 'N/A':
                            st.write(f"**Products:** {row['Products'][:200]}...")
                    
                    with col3:
                        st.write("**Additional Info:**")
                        if row['Clients'] != 'N/A':
                            st.write(f"**Clients:** {row['Clients'][:150]}...")
                        if row['Team Info'] != 'N/A':
                            st.write(f"**Team:** {row['Team Info'][:150]}...")
                        
                        # Show scraped pages
                        if len(row['Pages Visited']) > 1:
                            st.write("**Pages Visited:**")
                            for page in row['Pages Visited'][:3]:
                                st.write(f"- {page}")
                            if len(row['Pages Visited']) > 3:
                                st.write(f"... and {len(row['Pages Visited']) - 3} more pages")
            
            # Full data table
            st.subheader("📋 Complete Deep Scraping Data")
            
            # Remove the Pages Visited column for the display (too long)
            display_df = df.drop('Pages Visited', axis=1)
            st.dataframe(display_df, use_container_width=True)
            
            # Enhanced download options
            st.subheader("💾 Download Results")
            
            col1, col2 = st.columns(2)
            with col1:
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                
                st.download_button(
                    label="📥 Download Full Results (CSV)",
                    data=csv_buffer.getvalue(),
                    file_name=f"deep_company_scraping_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            with col2:
                # Create a summary report
                summary_data = []
                for _, row in df.iterrows():
                    summary_data.append({
                        'Company': row['Company Name'],
                        'URL': row['URL'],
                        'Emails': row['Total Emails Found'],
                        'Phones': row['Total Phones Found'],
                        'Pages_Scraped': row['Pages Scraped'],
                        'Quality_Score': row['quality_score']
                    })
                
                summary_df = pd.DataFrame(summary_data)
                summary_csv = io.StringIO()
                summary_df.to_csv(summary_csv, index=False)
                
                st.download_button(
                    label="📊 Download Summary (CSV)",
                    data=summary_csv.getvalue(),
                    file_name=f"company_summary_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            # Scraping insights
            with st.expander("🔍 Deep Scraping Insights"):
                st.write("**Scraping Performance:**")
                st.write(f"- Average pages scraped per company: {df['Pages Scraped'].mean():.1f}")
                st.write(f"- Most productive scrape: {df['Pages Scraped'].max()} pages")
                st.write(f"- Success rate: {len(df)}/{len(companies_to_process)} companies ({len(df)/len(companies_to_process)*100:.1f}%)")
                
                st.write("**Data Richness:**")
                high_quality = df[df['quality_score'] >= 10]
                medium_quality = df[(df['quality_score'] >= 5) & (df['quality_score'] < 10)]
                low_quality = df[df['quality_score'] < 5]
                
                st.write(f"- High quality profiles (score ≥10): {len(high_quality)} companies")
                st.write(f"- Medium quality profiles (score 5-9): {len(medium_quality)} companies")
                st.write(f"- Low quality profiles (score <5): {len(low_quality)} companies")
                
                st.write("**Contact Discovery:**")
                st.write(f"- Best email discovery: {df['Total Emails Found'].max()} emails from one company")
                st.write(f"- Best phone discovery: {df['Total Phones Found'].max()} phones from one company")
                st.write(f"- Companies with both email and phone: {sum((df['Total Emails Found'] > 0) & (df['Total Phones Found'] > 0))}")
        else:
            st.error("❌ No data was successfully collected. Try adjusting your parameters or target URLs.")

if __name__ == "__main__":
    main_streamlit()