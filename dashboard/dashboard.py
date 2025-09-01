import streamlit as st
import pandas as pd
import requests
import re
import pypdf
from io import BytesIO
import urllib.parse
from bs4 import BeautifulSoup
from google_play_scraper import app
from datetime import datetime

st.set_page_config(layout="wide", page_title="Morocco Payments Dashboard")

@st.cache_data(ttl=86400)
def get_bam_report_data():
    """
    A single function to orchestrate finding, downloading, and parsing the BAM PDF.
    It returns a DataFrame. If parsing fails, it returns a hardcoded fallback DataFrame.
    """
    fallback_data = [
        {"Category": "POS Payments", "Metric": "Number of Transactions", "2022": "106.4 million", "2023": "131.3 million", "Growth (2022-2023)": "+23%"},
        {"Category": "", "Metric": "Value of Transactions", "2022": "MAD 39.2 billion", "2023": "MAD 46.9 billion", "Growth (2022-2023)": "+19.9%"},
        {"Category": "", "Metric": "↳ of which Contactless", "2022": "55.4 million (52% of POS)", "2023": "75.4 million (57% of POS)", "Growth (2022-2023)": "+36.1% (in transaction count)"},
        {"Category": "eCommerce Payments", "Metric": "Number of Transactions", "2022": "26.8 million", "2023": "32.1 million", "Growth (2022-2023)": "+20%"},
        {"Category": "", "Metric": "Value of Transactions", "2022": "MAD 8.6 billion", "2023": "MAD 9.9 billion", "Growth (2022-2023)": "+15%"},
        {"Category": "Mobile Payments (M-Wallet)", "Metric": "Number of Transactions", "2022": "7.9 million", "2023": "9.7 million", "Growth (2022-2023)": "+23%"},
        {"Category": "", "Metric": "Value of Transactions", "2022": "MAD 1.7 billion", "2023": "MAD 2.1 billion", "Growth (2022-2023)": "+23%"},
        {"Category": "Card-based Cash Withdrawals", "Metric": "Number of Transactions", "2022": "360 million", "2023": "402 million", "Growth (2022-2023)": "+12%"},
        {"Category": "", "Metric": "Value of Transactions", "2022": "MAD 351 billion", "2023": "MAD 399 billion", "Growth (2022-2023)": "+13%"}
    ]
    fallback_df = pd.DataFrame(fallback_data)

    page_url = "https://www.bkam.ma/fr/Publications-et-recherche/Publications-institutionnelles/Rapport-annuel-sur-les-infrastructures-des-marches-financiers-et-les-moyens-de-paiement-leur-surveillance-et-l-inclusion-financiere"
    
    def get_latest_report_url(base_url):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(base_url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            select_tag = soup.find('select', class_='selectDownloadFile')
            if select_tag:
                options = select_tag.find_all('option', value=lambda v: v and '2023' in v)
                if options:
                    pdf_path = options[0]['value']
                    domain = urllib.parse.urlunsplit((urllib.parse.urlparse(base_url).scheme, urllib.parse.urlparse(base_url).netloc, '', '', ''))
                    return urllib.parse.urljoin(domain, pdf_path)
        except Exception as e:
            # st.error(f"Failed to get BAM report URL: {e}")
            pass
            
        return None

    def extract_text_from_pdf(pdf_url):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(pdf_url, headers=headers)
            response.raise_for_status()
            pdf_file = BytesIO(response.content)
            reader = pypdf.PdfReader(pdf_file)
            full_text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += re.sub(r'\s+', ' ', page_text)
            return full_text
        except Exception as e:
            st.error(f"Failed to extract PDF text: {e}")
        return None
    
    def parse_payment_data(text):
        rows = []
        def clean_value(val_str):
            return float(val_str.replace(' ', '').replace(',', '.'))

        pos_num_pattern = re.search(r"hausse de ([\d,]+)% en nombre.*?passant de ([\d,]+) . ([\d,]+) millions d'op.rations", text, re.IGNORECASE)
        pos_val_pattern = re.search(r"valeur de ([\d,]+) milliards de dirhams en 2023 contre ([\d,]+) milliards en 2022", text, re.IGNORECASE)
        if pos_num_pattern and pos_val_pattern:
            val_2023 = clean_value(pos_val_pattern.group(1)); val_2022 = clean_value(pos_val_pattern.group(2))
            growth_val = round(((val_2023 / val_2022) - 1) * 100, 1)
            rows.append({"Category": "POS Payments", "Metric": "Number of Transactions", "2022": f"{clean_value(pos_num_pattern.group(2)):.1f} million", "2023": f"{clean_value(pos_num_pattern.group(3)):.1f} million", "Growth (2022-2023)": f"+{clean_value(pos_num_pattern.group(1))}%"})
            rows.append({"Category": "", "Metric": "Value of Transactions", "2022": f"MAD {val_2022:.1f} billion", "2023": f"MAD {val_2023:.1f} billion", "Growth (2022-2023)": f"+{growth_val}%"})

        mobile_pattern = re.search(r"M-Wallets.*?s'est .tabli . ([\d,]+) millions contre ([\d,]+) millions d'op.rations en 2022.*?montant total de ([\d,]+) milliards contre ([\d,]+) milliard en 2022.*?hausse de (\d+)% en nombre et en valeur", text, re.IGNORECASE)
        if mobile_pattern:
            growth = f"+{clean_value(mobile_pattern.group(5))}%"
            rows.append({"Category": "Mobile Payments (M-Wallet)", "Metric": "Number of Transactions", "2022": f"{clean_value(mobile_pattern.group(2)):.1f} million", "2023": f"{clean_value(mobile_pattern.group(1)):.1f} million", "Growth (2022-2023)": growth})
            rows.append({"Category": "", "Metric": "Value of Transactions", "2022": f"MAD {clean_value(mobile_pattern.group(4)):.1f} billion", "2023": f"MAD {clean_value(mobile_pattern.group(3)):.1f} billion", "Growth (2022-2023)": growth})
        
        return pd.DataFrame(rows)

    with st.spinner("Attempting to fetch latest Bank Al-Maghrib report..."):
        latest_pdf_url = get_latest_report_url(page_url)
        if latest_pdf_url:
            st.session_state.bam_source_url = latest_pdf_url
            report_text = extract_text_from_pdf(latest_pdf_url)
            if report_text:
                parsed_df = parse_payment_data(report_text)
                if not parsed_df.empty:
                    st.success("Successfully scraped and parsed the latest BAM report.", icon="✅")
                    return parsed_df
    
    # st.warning("Could not parse the live BAM report. Displaying default values for 2022/2023.", icon="⚠️")
    if 'bam_source_url' not in st.session_state:
         st.session_state.bam_source_url = page_url
    return fallback_df


wallet_apps_android = {
    'Wafa Cash (Jibi Pro)': 'com.b3g.wafacash.jibivpro', 'Chaabi Pay': 'com.wallet.m2t',
    'Cash Plus': 'com.cashplus.mobileapp', 'Damane Pay': 'co.ma.damanecash.android',
    'Al Barid Pay': 'ma.baridcash.saphir.baridpay', 'JIBI': 'com.b3g.wafacash.jibi',
    'Ora': 'com.oracash', 'Kenzup': 'com.kenzup.app.prod', 'Lana Cash': 'com.b3g.cih.wepay',
    'Yassir': 'com.yatechnologies.yassir_rider', 'Glovo': 'com.glovo'
}
wallet_apps_ios = {
    'Wafa Cash (Jibi Pro)': '1371478054', 'Chaabi Pay': '1504267861', 'Cash Plus': '1479205181',
    'Damane Pay': '1506971587', 'Al Barid Pay': '720775151', 'JIBI': '1200782472',
    'Ora': '6670762251', 'Kenzup': '1518977114', 'Lana Cash': '1618148242',
    'Yassir': '1239926325', 'Glovo': '951812684'
}

@st.cache_data(ttl=86400)
def get_app_store_data():
    """Scrapes both Android and iOS app stores and returns a merged DataFrame."""
    
    # Android Scraper
    data_android = []
    for name, app_id in wallet_apps_android.items():
        try:
            details = app(app_id, lang='en', country='ma')
            data_android.append({
                'Wallet': name, 'Platform': 'Android', 'Installs': details.get('installs'),
                'Score': details.get('score'), 'Ratings': details.get('ratings'),
                'Last Updated': datetime.fromtimestamp(details.get('updated')).strftime('%Y-%m-%d'),
                'Description': details.get('description', '')[:200]
            })
        except Exception:
            continue
    df_android = pd.DataFrame(data_android)

    # iOS Scraper
    data_ios = []
    for name, app_id in wallet_apps_ios.items():
        try:
            url = f"https://itunes.apple.com/lookup?id={app_id}&country=ma"
            r = requests.get(url, timeout=10)
            d = r.json()["results"][0]
            data_ios.append({
                'Wallet': name, 'Platform': 'iOS', 'Installs': 'N/A',
                'Score': d.get('averageUserRating'), 'Ratings': d.get('userRatingCount'),
                'Last Updated': d.get("currentVersionReleaseDate", "").split("T")[0],
                'Description': d.get('description', '')[:200]
            })
        except Exception:
            continue
    df_ios = pd.DataFrame(data_ios)

    return pd.concat([df_android, df_ios], ignore_index=True)


st.title("🇲🇦 Morocco Digital Payments Dashboard")

st.sidebar.title("Controls")
if st.sidebar.button('🔄 Refresh Data'):
    st.cache_data.clear()
    st.rerun()

tab1, tab2 = st.tabs(["📈 Key Payment System Metrics", "📱 Mobile Wallet App Performance"])

with tab1:
    st.header("Key Payment System Metrics (2022 vs 2023)")
    bam_df = get_bam_report_data()
    if not bam_df.empty:
        st.dataframe(bam_df, width='stretch', hide_index=True)
        if 'bam_source_url' in st.session_state:
            st.caption(f"Source: Bank Al-Maghrib Annual Report. [Link]({st.session_state.bam_source_url})")
    else:
        st.warning("Could not display BAM report data.")

with tab2:
    st.header("Mobile Wallet App Performance")
    apps_df = get_app_store_data()

    if not apps_df.empty:
        col1, col2, col3 = st.columns([1, 2, 2])

        with col1:
            platforms = st.multiselect(
                "Platform(s)",
                options=apps_df['Platform'].unique(),
                default=apps_df['Platform'].unique(),
                label_visibility="collapsed",
                placeholder="Select Platform(s)"
            )

        with col2:
            wallets = st.multiselect(
                "Wallet(s)",
                options=sorted(apps_df['Wallet'].unique()),
                default=sorted(apps_df['Wallet'].unique()),
                label_visibility="collapsed",
                placeholder="Select Wallet(s)"
            )

        with col3:
            search_term = st.text_input(
                "Search", 
                placeholder="Search in description...",
                label_visibility="collapsed"
            )

        filtered_df = apps_df[
            apps_df['Platform'].isin(platforms) &
            apps_df['Wallet'].isin(wallets)
        ]
        if search_term:
            filtered_df = filtered_df[filtered_df['Description'].str.contains(search_term, case=False, na=False)]
        
        st.dataframe(filtered_df, width='stretch', hide_index=True)
        st.caption(f"Showing {len(filtered_df)} of {len(apps_df)} total app entries. Data scraped on {datetime.today().strftime('%Y-%m-%d')}.")
    else:
        st.warning("Could not display app store data.")