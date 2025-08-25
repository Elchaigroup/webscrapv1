# main.py - Main Streamlit Application
import streamlit as st
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd
from duckduckgo_search import DDGS
import re
from urllib.parse import urljoin, urlparse
from collections import deque, Counter
import json
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# Set page config
st.set_page_config(
    page_title="Competitor SEO Analysis Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #2E86AB;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem;
    }
    .competitor-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .recommendation-box {
        background-color: #f0f8ff;
        border-left: 4px solid #2E86AB;
        padding: 1rem;
        margin: 1rem 0;
    }
    .sidebar .sidebar-content {
        background-color: #f5f5f5;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
if 'client_data' not in st.session_state:
    st.session_state.client_data = None
if 'competitor_data' not in st.session_state:
    st.session_state.competitor_data = None

# Helper functions (core scraping logic)
def search_companies(query, max_results=20):
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
        r'\+971[\s-]?\d{1,2}[\s-]?\d{3}[\s-]?\d{4}',
        r'\b\d{2}[\s-]?\d{3}[\s-]?\d{4}\b',
        r'\+\d{1,3}[\s-]?\d{1,4}[\s-]?\d{1,4}[\s-]?\d{1,4}',
    ]

    phones = []
    for pattern in phone_patterns:
        phones.extend(re.findall(pattern, text))

    return list(set(phones))

def extract_seo_data(soup, url):
    """Extract comprehensive SEO data from the page"""
    seo_data = {
        'meta_title': '',
        'meta_title_length': 0,
        'meta_description': '',
        'meta_description_length': 0,
        'meta_keywords': '',
        'h1_tags': [],
        'h2_tags': [],
        'h3_tags': [],
        'img_count': 0,
        'img_with_alt': 0,
        'img_without_alt': 0,
        'internal_links': 0,
        'external_links': 0,
        'meta_robots': '',
        'canonical_url': '',
        'og_tags': {},
        'schema_types': [],
        'word_count': 0,
        'https': False,
        'mobile_viewport': False
    }

    # Extract title tag
    title_tag = soup.find('title')
    if title_tag:
        seo_data['meta_title'] = title_tag.get_text(strip=True)
        seo_data['meta_title_length'] = len(seo_data['meta_title'])

    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        seo_data['meta_description'] = meta_desc.get('content', '')
        seo_data['meta_description_length'] = len(seo_data['meta_description'])

    # Extract meta keywords
    meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
    if meta_keywords:
        seo_data['meta_keywords'] = meta_keywords.get('content', '')

    # Extract heading tags
    seo_data['h1_tags'] = [h.get_text(strip=True) for h in soup.find_all('h1')][:5]
    seo_data['h2_tags'] = [h.get_text(strip=True) for h in soup.find_all('h2')][:10]
    seo_data['h3_tags'] = [h.get_text(strip=True) for h in soup.find_all('h3')][:10]

    # Analyze images
    images = soup.find_all('img')
    seo_data['img_count'] = len(images)
    for img in images:
        if img.get('alt'):
            seo_data['img_with_alt'] += 1
        else:
            seo_data['img_without_alt'] += 1

    # Count links
    domain = urlparse(url).netloc
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.startswith('http'):
            link_domain = urlparse(href).netloc
            if link_domain == domain:
                seo_data['internal_links'] += 1
            else:
                seo_data['external_links'] += 1
        elif not href.startswith('#') and not href.startswith('javascript:'):
            seo_data['internal_links'] += 1

    # Technical checks
    seo_data['https'] = urlparse(url).scheme == 'https'
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    seo_data['mobile_viewport'] = viewport is not None

    # Extract Open Graph tags
    og_properties = ['title', 'description', 'image', 'type']
    for prop in og_properties:
        og_tag = soup.find('meta', property=f'og:{prop}')
        if og_tag:
            seo_data['og_tags'][prop] = og_tag.get('content', '')

    # Extract Schema.org structured data
    schema_scripts = soup.find_all('script', type='application/ld+json')
    for script in schema_scripts:
        try:
            schema_data = json.loads(script.string)
            if '@type' in schema_data:
                seo_data['schema_types'].append(schema_data['@type'])
        except:
            pass

    # Calculate word count
    text_content = soup.get_text()
    words = text_content.split()
    seo_data['word_count'] = len(words)

    return seo_data

def calculate_seo_score(seo_data):
    """Calculate SEO score based on various factors"""
    score = 0

    # Title scoring
    if seo_data.get('meta_title'):
        if 30 <= seo_data['meta_title_length'] <= 60:
            score += 15
        else:
            score += 5

    # Description scoring
    if seo_data.get('meta_description'):
        if 120 <= seo_data['meta_description_length'] <= 160:
            score += 15
        else:
            score += 5

    # Technical SEO
    if seo_data.get('https'):
        score += 10
    if seo_data.get('mobile_viewport'):
        score += 10
    if seo_data.get('h1_tags'):
        score += 10
    if seo_data.get('img_with_alt', 0) > seo_data.get('img_without_alt', 0):
        score += 10
    if seo_data.get('schema_types'):
        score += 10
    if seo_data.get('og_tags'):
        score += 10

    # Content quality
    if seo_data.get('word_count', 0) >= 300:
        score += 10
    if seo_data.get('internal_links', 0) > 0:
        score += 10

    return min(score, 100)

def scrape_website_data(url, progress_bar=None):
    """Scrape comprehensive data from a website"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        if progress_bar:
            progress_bar.progress(0.3)
            
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        if progress_bar:
            progress_bar.progress(0.6)

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Extract basic company info
        company_name = "N/A"
        for tag in ['h1', 'title']:
            element = soup.find(tag)
            if element:
                company_name = element.get_text(strip=True)[:100]
                break

        # Extract contact info
        emails = extract_emails(response.text)
        phones = extract_phones(response.text)
        
        # Extract SEO data
        seo_data = extract_seo_data(soup, url)
        seo_score = calculate_seo_score(seo_data)
        
        # Extract content keywords
        text = soup.get_text().lower()
        words = re.findall(r'\b[a-z]+\b', text)
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        filtered_words = [w for w in words if w not in stop_words and len(w) > 3]
        word_freq = Counter(filtered_words)
        top_keywords = [word for word, count in word_freq.most_common(10)]

        if progress_bar:
            progress_bar.progress(1.0)

        return {
            'url': url,
            'domain': urlparse(url).netloc,
            'company_name': company_name,
            'emails': emails,
            'phones': phones,
            'seo_score': seo_score,
            'seo_data': seo_data,
            'top_keywords': top_keywords,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    except Exception as e:
        st.error(f"Error scraping {url}: {str(e)}")
        return None

def generate_recommendations(client_data, competitor_data):
    """Generate recommendations based on competitor analysis"""
    recommendations = []
    
    if not client_data or not competitor_data:
        return recommendations
    
    # SEO recommendations
    avg_competitor_score = sum([c['seo_score'] for c in competitor_data]) / len(competitor_data)
    if client_data['seo_score'] < avg_competitor_score:
        recommendations.append({
            'category': 'SEO Performance',
            'issue': f"Your SEO score ({client_data['seo_score']}) is below competitor average ({avg_competitor_score:.1f})",
            'action': 'Focus on improving meta titles, descriptions, and technical SEO elements',
            'priority': 'High'
        })

    # Title length recommendations
    client_title_length = client_data['seo_data'].get('meta_title_length', 0)
    if client_title_length < 30 or client_title_length > 60:
        recommendations.append({
            'category': 'Meta Title',
            'issue': f"Title length is {client_title_length} characters",
            'action': 'Optimize title length to 30-60 characters for better search visibility',
            'priority': 'Medium'
        })

    # Content recommendations
    client_word_count = client_data['seo_data'].get('word_count', 0)
    avg_competitor_words = sum([c['seo_data'].get('word_count', 0) for c in competitor_data]) / len(competitor_data)
    if client_word_count < avg_competitor_words * 0.8:
        recommendations.append({
            'category': 'Content Length',
            'issue': f"Your content ({client_word_count} words) is shorter than competitors (avg: {avg_competitor_words:.0f})",
            'action': 'Add more valuable content to improve search rankings',
            'priority': 'Medium'
        })

    # Technical SEO
    if not client_data['seo_data'].get('https'):
        recommendations.append({
            'category': 'Security',
            'issue': 'Website not using HTTPS',
            'action': 'Implement SSL certificate for security and SEO benefits',
            'priority': 'High'
        })

    if not client_data['seo_data'].get('mobile_viewport'):
        recommendations.append({
            'category': 'Mobile Optimization',
            'issue': 'Missing mobile viewport meta tag',
            'action': 'Add mobile viewport tag for better mobile experience',
            'priority': 'High'
        })

    return recommendations

# Main Streamlit App
def main():
    st.markdown('<h1 class="main-header">🔍 Competitor SEO Analysis Tool</h1>', unsafe_allow_html=True)
    
    # Sidebar for client information
    with st.sidebar:
        st.header("📋 Client Information")
        
        client_name = st.text_input("Client Company Name", placeholder="Enter company name...")
        client_url = st.text_input("Client Website URL", placeholder="https://example.com")
        client_industry = st.selectbox(
            "Industry/Sector",
            ["Sales & Marketing", "Technology", "Healthcare", "Finance", "Real Estate", "Manufacturing", "Retail", "Other"]
        )
        client_location = st.text_input("Location", value="Dubai, UAE")
        
        # Advanced options
        st.subheader("🎯 Analysis Options")
        num_competitors = st.slider("Number of competitors to analyze", 3, 10, 5)
        analysis_depth = st.selectbox("Analysis Depth", ["Quick Scan", "Standard", "Deep Analysis"])
        
        if st.button("🚀 Start Analysis", type="primary"):
            if client_url and client_name:
                st.session_state.analysis_complete = False
                run_analysis(client_name, client_url, client_industry, client_location, num_competitors, analysis_depth)
            else:
                st.error("Please provide client name and website URL")

    # Main content area
    if st.session_state.analysis_complete:
        display_results()
    else:
        # Landing page content
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            <div class="metric-card">
                <h3>🎯 Competitor Discovery</h3>
                <p>Automatically find relevant competitors based on your client's industry and location</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="metric-card">
                <h3>📊 SEO Analysis</h3>
                <p>Comprehensive SEO audit comparing your client against competitors</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="metric-card">
                <h3>💡 Recommendations</h3>
                <p>Actionable insights to outrank competitors and improve visibility</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        st.markdown("""
        ### How it works:
        1. **Enter your client's information** in the sidebar
        2. **Configure analysis settings** (number of competitors, depth)
        3. **Click "Start Analysis"** to begin the competitive research
        4. **Review detailed comparisons** and improvement recommendations
        5. **Export results** for client presentations
        """)
        
        st.info("💡 Tip: For best results, ensure your client's website URL is accessible and contains relevant business information.")

def run_analysis(client_name, client_url, industry, location, num_competitors, depth):
    """Run the complete competitor analysis"""
    
    with st.spinner("🔍 Starting competitive analysis..."):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Step 1: Analyze client website
        status_text.text("Analyzing your client's website...")
        progress_bar.progress(0.1)
        
        client_data = scrape_website_data(client_url, progress_bar)
        if not client_data:
            st.error("Could not analyze client website. Please check the URL.")
            return
        
        progress_bar.progress(0.3)
        
        # Step 2: Find competitors
        status_text.text("Searching for competitors...")
        search_queries = [
            f"{industry} companies {location}",
            f"{client_name} competitors {location}",
            f"top {industry} firms {location}",
            f"{industry} services {location}"
        ]
        
        all_competitor_urls = set()
        client_domain = urlparse(client_url).netloc
        
        for query in search_queries[:2]:  # Limit queries for faster results
            urls, titles, snippets = search_companies(query, max_results=5)
            for url in urls:
                competitor_domain = urlparse(url).netloc
                if competitor_domain != client_domain:  # Exclude client's own site
                    all_competitor_urls.add(url)
        
        competitor_urls = list(all_competitor_urls)[:num_competitors]
        progress_bar.progress(0.5)
        
        # Step 3: Analyze competitors
        competitor_data = []
        for i, url in enumerate(competitor_urls):
            status_text.text(f"Analyzing competitor {i+1}/{len(competitor_urls)}: {urlparse(url).netloc}")
            
            competitor_info = scrape_website_data(url)
            if competitor_info:
                competitor_data.append(competitor_info)
            
            progress_bar.progress(0.5 + (0.4 * (i+1) / len(competitor_urls)))
        
        # Step 4: Generate recommendations
        status_text.text("Generating recommendations...")
        recommendations = generate_recommendations(client_data, competitor_data)
        progress_bar.progress(0.95)
        
        # Store results in session state
        st.session_state.client_data = client_data
        st.session_state.competitor_data = competitor_data
        st.session_state.recommendations = recommendations
        st.session_state.analysis_complete = True
        
        progress_bar.progress(1.0)
        status_text.text("Analysis complete!")
        time.sleep(1)
        
        # Clear progress indicators
        progress_bar.empty()
        status_text.empty()
        
        st.success("🎉 Analysis completed successfully!")
        st.rerun()

def display_results():
    """Display the analysis results"""
    
    client_data = st.session_state.client_data
    competitor_data = st.session_state.competitor_data
    recommendations = st.session_state.recommendations
    
    if not client_data or not competitor_data:
        st.error("No analysis data found. Please run the analysis first.")
        return
    
    # Results header
    st.header(f"📊 Analysis Results for {client_data['company_name']}")
    
    # Key metrics overview
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Your SEO Score",
            f"{client_data['seo_score']}/100",
            delta=None
        )
    
    with col2:
        avg_competitor_score = sum([c['seo_score'] for c in competitor_data]) / len(competitor_data)
        delta = client_data['seo_score'] - avg_competitor_score
        st.metric(
            "vs Competitor Avg",
            f"{avg_competitor_score:.1f}/100",
            delta=f"{delta:+.1f}",
            delta_color="inverse"
        )
    
    with col3:
        st.metric(
            "Competitors Analyzed",
            len(competitor_data)
        )
    
    with col4:
        st.metric(
            "Recommendations",
            len(recommendations)
        )
    
    st.markdown("---")
    
    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Overview", "🏆 Competitor Comparison", "🎯 SEO Deep Dive", "💡 Recommendations", "📋 Export Results"])
    
    with tab1:
        display_overview_tab(client_data, competitor_data)
    
    with tab2:
        display_competitor_comparison_tab(client_data, competitor_data)
    
    with tab3:
        display_seo_deep_dive_tab(client_data, competitor_data)
    
    with tab4:
        display_recommendations_tab(recommendations)
    
    with tab5:
        display_export_tab(client_data, competitor_data, recommendations)

def display_overview_tab(client_data, competitor_data):
    """Display overview tab content"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🎯 Your Performance")
        
        # SEO Score gauge
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=client_data['seo_score'],
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "SEO Score"},
            delta={'reference': 50},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 50], 'color': "lightgray"},
                    {'range': [50, 85], 'color': "gray"}],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 85}
            }
        ))
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
        
        # Key metrics
        st.markdown("**Key Metrics:**")
        st.write(f"• Meta Title Length: {client_data['seo_data'].get('meta_title_length', 0)} chars")
        st.write(f"• Meta Description Length: {client_data['seo_data'].get('meta_description_length', 0)} chars")
        st.write(f"• Word Count: {client_data['seo_data'].get('word_count', 0)}")
        st.write(f"• Internal Links: {client_data['seo_data'].get('internal_links', 0)}")
        st.write(f"• Images: {client_data['seo_data'].get('img_count', 0)} total, {client_data['seo_data'].get('img_with_alt', 0)} with alt text")
    
    with col2:
        st.subheader("🏁 Competitor Landscape")
        
        # Competitor scores chart
        competitor_names = [c['company_name'][:20] + '...' if len(c['company_name']) > 20 else c['company_name'] for c in competitor_data]
        competitor_scores = [c['seo_score'] for c in competitor_data]
        
        fig = px.bar(
            x=competitor_names,
            y=competitor_scores,
            title="Competitor SEO Scores",
            labels={'x': 'Competitors', 'y': 'SEO Score'},
            color=competitor_scores,
            color_continuous_scale='viridis'
        )
        fig.add_hline(y=client_data['seo_score'], line_dash="dash", 
                     annotation_text=f"Your Score: {client_data['seo_score']}", 
                     line_color="red")
        st.plotly_chart(fig, use_container_width=True)

def display_competitor_comparison_tab(client_data, competitor_data):
    """Display detailed competitor comparison"""
    
    st.subheader("🏆 Detailed Competitor Analysis")
    
    # Create comparison DataFrame
    comparison_data = []
    
    # Add client data
    comparison_data.append({
        'Company': f"{client_data['company_name']} (YOU)",
        'Domain': client_data['domain'],
        'SEO Score': client_data['seo_score'],
        'Title Length': client_data['seo_data'].get('meta_title_length', 0),
        'Description Length': client_data['seo_data'].get('meta_description_length', 0),
        'Word Count': client_data['seo_data'].get('word_count', 0),
        'Images': client_data['seo_data'].get('img_count', 0),
        'HTTPS': '✅' if client_data['seo_data'].get('https') else '❌',
        'Mobile Ready': '✅' if client_data['seo_data'].get('mobile_viewport') else '❌',
        'H1 Tags': len(client_data['seo_data'].get('h1_tags', [])),
        'Internal Links': client_data['seo_data'].get('internal_links', 0)
    })
    
    # Add competitor data
    for comp in competitor_data:
        comparison_data.append({
            'Company': comp['company_name'],
            'Domain': comp['domain'],
            'SEO Score': comp['seo_score'],
            'Title Length': comp['seo_data'].get('meta_title_length', 0),
            'Description Length': comp['seo_data'].get('meta_description_length', 0),
            'Word Count': comp['seo_data'].get('word_count', 0),
            'Images': comp['seo_data'].get('img_count', 0),
            'HTTPS': '✅' if comp['seo_data'].get('https') else '❌',
            'Mobile Ready': '✅' if comp['seo_data'].get('mobile_viewport') else '❌',
            'H1 Tags': len(comp['seo_data'].get('h1_tags', [])),
            'Internal Links': comp['seo_data'].get('internal_links', 0)
        })
    
    df = pd.DataFrame(comparison_data)
    
    # Style the dataframe to highlight client row
    def highlight_client_row(row):
        if '(YOU)' in row['Company']:
            return ['background-color: #e6f3ff'] * len(row)
        return [''] * len(row)
    
    styled_df = df.style.apply(highlight_client_row, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

def display_seo_deep_dive_tab(client_data, competitor_data):
    """Display SEO deep dive analysis"""
    
    st.subheader("🎯 SEO Deep Dive Analysis")
    
    # SEO Categories Performance
    categories = ['Title Optimization', 'Meta Description', 'Technical SEO', 'Content Quality', 'Image Optimization', 'Link Structure']
    
    # Calculate client scores for each category
    client_scores = []
    client_seo = client_data['seo_data']
    
    # Title Optimization (0-100)
    title_score = 0
    if 30 <= client_seo.get('meta_title_length', 0) <= 60:
        title_score = 100
    elif client_seo.get('meta_title_length', 0) > 0:
        title_score = 50
    client_scores.append(title_score)
    
    # Meta Description (0-100)
    desc_score = 0
    if 120 <= client_seo.get('meta_description_length', 0) <= 160:
        desc_score = 100
    elif client_seo.get('meta_description_length', 0) > 0:
        desc_score = 50
    client_scores.append(desc_score)
    
    # Technical SEO (0-100)
    tech_score = 0
    if client_seo.get('https'):
        tech_score += 50
    if client_seo.get('mobile_viewport'):
        tech_score += 50
    client_scores.append(tech_score)
    
    # Content Quality (0-100)
    content_score = 0
    if client_seo.get('word_count', 0) >= 300:
        content_score += 50
    if client_seo.get('h1_tags'):
        content_score += 50
    client_scores.append(content_score)
    
    # Image Optimization (0-100)
    img_score = 0
    if client_seo.get('img_count', 0) > 0:
        alt_ratio = client_seo.get('img_with_alt', 0) / client_seo.get('img_count', 1)
        img_score = int(alt_ratio * 100)
    client_scores.append(img_score)
    
    # Link Structure (0-100)
    link_score = 0
    if client_seo.get('internal_links', 0) > 0:
        link_score += 50
    if client_seo.get('external_links', 0) > 0:
        link_score += 50
    client_scores.append(link_score)
    
    # Calculate average competitor scores
    avg_competitor_scores = []
    for i in range(len(categories)):
        scores = []
        for comp in competitor_data:
            comp_seo = comp['seo_data']
            if i == 0:  # Title
                if 30 <= comp_seo.get('meta_title_length', 0) <= 60:
                    scores.append(100)
                elif comp_seo.get('meta_title_length', 0) > 0:
                    scores.append(50)
                else:
                    scores.append(0)
            elif i == 1:  # Description
                if 120 <= comp_seo.get('meta_description_length', 0) <= 160:
                    scores.append(100)
                elif comp_seo.get('meta_description_length', 0) > 0:
                    scores.append(50)
                else:
                    scores.append(0)
            elif i == 2:  # Technical
                tech = 0
                if comp_seo.get('https'):
                    tech += 50
                if comp_seo.get('mobile_viewport'):
                    tech += 50
                scores.append(tech)
            elif i == 3:  # Content
                content = 0
                if comp_seo.get('word_count', 0) >= 300:
                    content += 50
                if comp_seo.get('h1_tags'):
                    content += 50
                scores.append(content)
            elif i == 4:  # Images
                img = 0
                if comp_seo.get('img_count', 0) > 0:
                    alt_ratio = comp_seo.get('img_with_alt', 0) / comp_seo.get('img_count', 1)
                    img = int(alt_ratio * 100)
                scores.append(img)
            elif i == 5:  # Links
                link = 0
                if comp_seo.get('internal_links', 0) > 0:
                    link += 50
                if comp_seo.get('external_links', 0) > 0:
                    link += 50
                scores.append(link)
        
        avg_competitor_scores.append(sum(scores) / len(scores) if scores else 0)
    
    # Create radar chart
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=client_scores,
        theta=categories,
        fill='toself',
        name='Your Website',
        line_color='blue'
    ))
    
    fig.add_trace(go.Scatterpolar(
        r=avg_competitor_scores,
        theta=categories,
        fill='toself',
        name='Competitor Average',
        line_color='red'
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100]
            )),
        showlegend=True,
        title="SEO Performance Comparison",
        height=500
    )
    
    st.plotly_chart(fig, use_container_width=True)

def display_recommendations_tab(recommendations):
    """Display actionable recommendations"""
    
    st.subheader("💡 Actionable Recommendations")
    
    if not recommendations:
        st.success("🎉 Great job! Your website is performing well compared to competitors.")
        st.info("Consider monitoring competitor changes regularly to maintain your advantage.")
        return
    
    # Group recommendations by priority
    high_priority = [r for r in recommendations if r['priority'] == 'High']
    medium_priority = [r for r in recommendations if r['priority'] == 'Medium']
    
    # High priority recommendations
    if high_priority:
        st.markdown("### 🔴 High Priority Actions")
        for i, rec in enumerate(high_priority, 1):
            st.markdown(f"""
            <div class="recommendation-box">
                <h4>{i}. {rec['category']}</h4>
                <p><strong>Issue:</strong> {rec['issue']}</p>
                <p><strong>Action:</strong> {rec['action']}</p>
            </div>
            """, unsafe_allow_html=True)
    
    # Medium priority recommendations
    if medium_priority:
        st.markdown("### 🟡 Medium Priority Actions")
        for i, rec in enumerate(medium_priority, 1):
            st.markdown(f"""
            <div class="recommendation-box">
                <h4>{i}. {rec['category']}</h4>
                <p><strong>Issue:</strong> {rec['issue']}</p>
                <p><strong>Action:</strong> {rec['action']}</p>
            </div>
            """, unsafe_allow_html=True)

def display_export_tab(client_data, competitor_data, recommendations):
    """Display export options"""
    
    st.subheader("📋 Export Analysis Results")
    
    # CSV export
    if st.button("📥 Download CSV Report"):
        csv_data = []
        
        # Add client data
        csv_data.append({
            'Type': 'Client',
            'Company': client_data['company_name'],
            'Domain': client_data['domain'],
            'SEO Score': client_data['seo_score'],
            'Title Length': client_data['seo_data'].get('meta_title_length', 0),
            'Description Length': client_data['seo_data'].get('meta_description_length', 0),
            'Word Count': client_data['seo_data'].get('word_count', 0),
            'HTTPS': client_data['seo_data'].get('https', False),
            'Mobile Ready': client_data['seo_data'].get('mobile_viewport', False)
        })
        
        # Add competitor data
        for comp in competitor_data:
            csv_data.append({
                'Type': 'Competitor',
                'Company': comp['company_name'],
                'Domain': comp['domain'],
                'SEO Score': comp['seo_score'],
                'Title Length': comp['seo_data'].get('meta_title_length', 0),
                'Description Length': comp['seo_data'].get('meta_description_length', 0),
                'Word Count': comp['seo_data'].get('word_count', 0),
                'HTTPS': comp['seo_data'].get('https', False),
                'Mobile Ready': comp['seo_data'].get('mobile_viewport', False)
            })
        
        df = pd.DataFrame(csv_data)
        csv = df.to_csv(index=False)
        
        st.download_button(
            label="💾 Download Analysis Data",
            data=csv,
            file_name=f"competitor_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    # Reset analysis button
    st.markdown("---")
    if st.button("🔄 Start New Analysis", type="secondary"):
        # Clear session state
        for key in ['analysis_complete', 'client_data', 'competitor_data', 'recommendations']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

if __name__ == "__main__":
    main()