import asyncio
import sys

# Fix for asyncio event loop on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import pandas as pd
import time
import random
import re
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse
import logging
import plotly.express as px

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Fashion Scraper Pro", layout="wide")

# Sidebar for configuration
with st.sidebar:
    st.title("⚙️ Scraper Settings")
    
    headless = st.checkbox("Run in headless mode", value=True, 
                           help="Headless mode runs without showing the browser window")
    
    wait_time = st.slider("Page load wait time (seconds)", 2, 10, 4, 
                          help="How long to wait for dynamic content to load")
    
    user_agent = st.text_input("Custom User Agent (optional)", 
                               value="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
                               help="Using a common user agent can help avoid being blocked")
    
    pagination = st.checkbox("Enable pagination", value=False,
                             help="Scrape multiple pages if available")
    
    max_pages = st.number_input("Maximum pages to scrape", 1, 20, 3, 
                                help="Limit the number of pages to avoid long scraping sessions")
    
    st.subheader("Site Profiles")
    site_profile = st.selectbox("Select a site profile (optional)", 
                               ["Auto-detect", "Generic", "Shopify", "WooCommerce", "Magento", "Fashion Nova", "ASOS", "Zara"], 
                               help="Select a specific site profile for better results")
site_selectors = {
    "Generic": {
        "items": "article, .product, .product-card, .grid-item, li[id*='product'], div[class*='product'], [data-product-id]",
        "title": "h2, h3, h4, .product-title, .name, .title, [class*='product-name'], [class*='title']",
        "price": ".price, [class*='price'], .amount, .product-price, [data-price]",
        "regular_price": ".regular-price, .original-price, .compare-at-price, [class*='regular-price'], [class*='original-price']",
        "sale_price": ".sale-price, .special-price, [class*='sale-price'], [class*='special-price']",
        "image": "img",
        "link": "a",
        "description": ".description, [class*='description'], .excerpt, .summary, [class*='product-details']",
        "next_page": ".next, .pagination a:last-child, [class*='next'], a[rel='next'], a[aria-label*='Next']",
    },
    "Shopify": {
        "items": ".product-card, .grid__item, .product-item, [class*='product-card']",
        "title": ".product-card__title, .product-title, .product-item__title, h2, h3",
        "price": ".price, .product-price, [class*='price']",
        "regular_price": ".regular-price, .price__regular",
        "sale_price": ".sale-price, .price__sale",
        "image": "img",
        "link": "a",
        "description": ".description, .product-excerpt",
        "next_page": "a.pagination__next, .next a",
    },
    "WooCommerce": {
        "items": "li.product, .product-type-simple, .product-type-variable, .type-product",
        "title": "h2.woocommerce-loop-product__title, .product-title, h3",
        "price": ".price, .woocommerce-Price-amount",
        "regular_price": ".regular-price, del .woocommerce-Price-amount",
        "sale_price": ".sale-price, ins .woocommerce-Price-amount",
        "image": "img.wp-post-image, img.attachment-woocommerce_thumbnail",
        "link": "a.woocommerce-LoopProduct-link",
        "description": ".short-description, .woocommerce-product-details__short-description",
        "next_page": ".next.page-numbers",
    },
    "Magento": {
        "items": "li.item.product.product-item, .product-item, .product-items > li",
        "title": ".product-item-name, .product-name, a.product-item-link",
        "price": ".price, .price-container .price, [data-price-type='finalPrice']",
        "regular_price": "[data-price-type='oldPrice'], .old-price .price",
        "sale_price": "[data-price-type='finalPrice'], .special-price .price",
        "image": "img.product-image-photo",
        "link": "a.product-item-photo, a.product-item-link",
        "description": ".product-item-description, .description",
        "next_page": ".pages-item-next a",
    },
    "Fashion Nova": {
        "items": ".product-grid-item, .grid-item, [class*='product-item']",
        "title": ".product-name, .product-title, .name, h3",
        "price": ".price, .product-price",
        "regular_price": ".regular-price, .compare-at-price",
        "sale_price": ".special-price, .price--sale",
        "image": "img.product-featured-img, .product-image img",
        "link": "a.product-grid-item__link, a",
        "description": ".product-description",
        "next_page": ".pagination__next, .pagination-next",
    },
    "ASOS": {
        "items": "article[data-auto-id='productTile'], [data-test-id='product-card']",
        "title": "[data-auto-id='productTileDescription'], h2, .product-title",
        "price": "[data-auto-id='productTilePrice'], .current-price, [data-test-id='price']",
        "regular_price": ".previous-price, .was-price",
        "sale_price": ".current-price, .now-price",
        "image": "img",
        "link": "a[data-auto-id='productTileLink'], a",
        "description": ".product-description, .product-info",
        "next_page": "[data-auto-id='loadMoreProducts'], .pagination-next",
    },
    "Zara": {
        "items": ".product-item, .product, article[class*='product']",
        "title": ".product-info .name, .item-name, h3.product-info-item-name",
        "price": ".price, .product-info-price",
        "regular_price": ".original-price, .line-through",
        "sale_price": ".sale-price, .price-current",
        "image": "img.product-media, .media-image img",
        "link": "a.item, a.link",
        "description": ".description, .product-info-description",
        "next_page": ".next-page, .zds-button--pagination-next",
    },
}

def detect_site_type(page):
    """Try to detect the site platform based on page content"""
    page_content = page.content()
    
    if "shopify" in page_content.lower():
        return "Shopify"
    elif "woocommerce" in page_content.lower():
        return "WooCommerce"
    elif "magento" in page_content.lower():
        return "Magento"
    elif "fashionnova" in page.url.lower():
        return "Fashion Nova"
    elif "asos" in page.url.lower():
        return "ASOS"
    elif "zara" in page.url.lower():
        return "Zara"
    else:
        return "Generic"

def extract_currency_amount(price_text):
    """Extract currency and amount from price text"""
    if not price_text or price_text == "N/A":
        return {"currency": "", "amount": ""}
    
    # Try to extract currency symbol and amount
    currency_match = re.search(r'[$€£¥₹]|[A-Z]{3}', price_text)
    currency = currency_match.group(0) if currency_match else ""
    
    # Extract numeric value
    amount_match = re.search(r'[\d,.]+', price_text)
    amount = amount_match.group(0) if amount_match else ""
    
    return {"currency": currency, "amount": amount}

def clean_text(text):
    """Clean and normalize text"""
    if not text:
        return "N/A"
    # Remove extra whitespace, newlines, tabs
    cleaned = re.sub(r'\s+', ' ', text).strip()
    return cleaned

def extract_colors(text):
    """Try to identify color information in product text"""
    if not text or text == "N/A":
        return []
    
    common_colors = [
        "black", "white", "red", "blue", "green", "yellow", "purple", "pink", 
        "orange", "brown", "grey", "gray", "navy", "beige", "gold", "silver",
        "tan", "olive", "teal", "maroon", "ivory", "khaki"
    ]
    
    found_colors = []
    text_lower = text.lower()
    
    for color in common_colors:
        if color in text_lower:
            found_colors.append(color)
            
    return found_colors

def scrape_fashion_site(url, selectors, wait_time, user_agent, headless=True):
    with sync_playwright() as p:
        browser_args = []
        if user_agent:
            browser_args.append(f'--user-agent={user_agent}')
        
        browser = p.chromium.launch(headless=headless, args=browser_args)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        logger.info(f"Navigating to {url}")
        page.goto(url, timeout=60000)
        
        # Add some randomization to wait times to seem more human-like
        jittered_wait = wait_time + random.uniform(0, 1)
        page.wait_for_timeout(int(jittered_wait * 1000))
        
        # If site profile is auto-detect, try to detect the site type
        if site_profile == "Auto-detect":
            detected_type = detect_site_type(page)
            current_selectors = site_selectors[detected_type]
            st.info(f"Detected site type: {detected_type}")
        else:
            current_selectors = selectors
        
        all_data = []
        current_url = url
        pages_scraped = 0
        
        while True:
            pages_scraped += 1
            logger.info(f"Scraping page {pages_scraped}: {current_url}")
            
            # Let the page fully load
            page.wait_for_timeout(int(jittered_wait * 1000))
            
            # Handle cookie banners or popups that might interfere
            try:
                for selector in [".cookie-banner button", "#cookie-accept", ".popup-close", ".modal-close"]:
                    close_buttons = page.query_selector_all(selector)
                    for button in close_buttons:
                        button.click()
                        page.wait_for_timeout(500)
            except Exception:
                pass
            
            # Scroll down the page to load lazy-loaded images
            page.evaluate("""
                () => {
                    window.scrollTo(0, 0);
                    let totalHeight = 0;
                    let distance = 300;
                    let timer = setInterval(() => {
                        let scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        
                        if(totalHeight >= scrollHeight){
                            clearInterval(timer);
                        }
                    }, 100);
                }
            """)
            
            page.wait_for_timeout(1000)
            
            # Try to get product blocks
            items = page.query_selector_all(current_selectors["items"])
            
            if not items:
                # If no items found with main selector, try alternative selectors
                fallback_selectors = [
                    "div[id*='product'], li[class*='product']",
                    "[data-product], [data-product-id]",
                    ".item, .grid-item, .collection-item"
                ]
                
                for selector in fallback_selectors:
                    items = page.query_selector_all(selector)
                    if items:
                        break
                        
            page_data = []
            for item in items:
                try:
                    # Title extraction
                    title_el = item.query_selector(current_selectors["title"])
                    title = clean_text(title_el.inner_text() if title_el else "N/A")
                    
                    # Price extraction - try to get sale and regular price
                    price_el = item.query_selector(current_selectors["price"])
                    price_text = clean_text(price_el.inner_text() if price_el else "N/A")
                    
                    regular_price_el = item.query_selector(current_selectors["regular_price"])
                    regular_price = clean_text(regular_price_el.inner_text() if regular_price_el else price_text)
                    
                    sale_price_el = item.query_selector(current_selectors["sale_price"])
                    sale_price = clean_text(sale_price_el.inner_text() if sale_price_el else "")
                    
                    if not sale_price and regular_price != price_text:
                        sale_price = price_text
                    
                    # Image extraction
                    img_el = item.query_selector(current_selectors["image"])
                    img_src = ""
                    if img_el:
                        # Try different attributes that might contain the image URL
                        for attr in ["src", "data-src", "srcset", "data-srcset"]:
                            img_src = img_el.get_attribute(attr)
                            if img_src:
                                # If srcset, extract the first URL
                                if "srcset" in attr:
                                    img_src = img_src.split(",")[0].strip().split(" ")[0]
                                break
                    
                    img_url = urljoin(url, img_src) if img_src else "N/A"
                    
                    # Product link extraction
                    link_el = item.query_selector(current_selectors["link"])
                    product_url = urljoin(url, link_el.get_attribute("href")) if link_el else "N/A"
                    
                    # Description extraction
                    desc_el = item.query_selector(current_selectors["description"])
                    description = clean_text(desc_el.inner_text() if desc_el else "N/A")
                    
                    # Try to extract colors
                    colors = extract_colors(f"{title} {description}")
                    
                    # Extract currency and amount
                    price_details = extract_currency_amount(price_text)
                    
                    # Get site domain for reference
                    domain = urlparse(url).netloc
                    
                    product_data = {
                        "Title": title,
                        "Price": price_text,
                        "Regular Price": regular_price,
                        "Sale Price": sale_price,
                        "Currency": price_details["currency"],
                        "Price Amount": price_details["amount"],
                        "Image URL": img_url,
                        "Product URL": product_url,
                        "Description": description,
                        "Colors": ", ".join(colors) if colors else "N/A",
                        "Source Site": domain
                    }
                    
                    page_data.append(product_data)
                except Exception as e:
                    logger.error(f"Error extracting product data: {e}")
                    continue
            
            all_data.extend(page_data)
            
            # Check for pagination
            if pagination and pages_scraped < max_pages:
                next_page_link = page.query_selector(current_selectors["next_page"])
                if next_page_link:
                    next_page_url = next_page_link.get_attribute("href")
                    if next_page_url:
                        current_url = urljoin(url, next_page_url)
                        logger.info(f"Found next page: {current_url}")
                        page.goto(current_url, timeout=60000)
                        # Add randomized delay between page navigations
                        page.wait_for_timeout(int((wait_time + random.uniform(1, 2)) * 1000))
                        continue
            
            # If no pagination or reached max pages, break the loop
            break
        
        browser.close()
        return all_data

# Create tabs for different features
tab1, tab2, tab3 = st.tabs(["Scraper", "Results Analysis", "Help"])

with tab1:
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔍 Scrape", key="scrape_button", type="primary"):
            if url:
                with st.spinner("Scraping website... This may take a minute"):
                    try:
                        # Use the selected site profile selectors
                        current_selectors = site_selectors[site_profile] if site_profile != "Auto-detect" else site_selectors["Generic"]
                        
                        data = scrape_fashion_site(url, current_selectors, wait_time, user_agent, headless)
                        
                        if data:
                            st.session_state['scraped_data'] = data
                            st.success(f"✅ Successfully scraped {len(data)} products!")
                        else:
                            st.warning("No product data found on this page. Try adjusting the scraper settings or selecting a different site profile.")
                    except Exception as e:
                        st.error(f"Error: {e}")
                        st.info("Try adjusting the wait time, checking the URL, or selecting a specific site profile.")
            else:
                st.warning("Please enter a URL.")
    
    with col2:
        st.write("Try these example URLs:")
        example_urls = {
            "Example Fashion Site": "https://www.example-fashion-site.com/collections/new-arrivals",
            "Demo Shop": "https://demo.shopify.com/collections/all",
        }
        
        for name, example_url in example_urls.items():
            if st.button(name):
                st.session_state['url'] = example_url
                st.experimental_rerun()
    
    if 'scraped_data' in st.session_state:
        data = st.session_state['scraped_data']
        df = pd.DataFrame(data)
        
        st.subheader("Scraped Products")
        
        # Display product grid
        cols = st.columns(3)
        for i, row in enumerate(data[:12]):  # Show first 12 products in grid
            col_idx = i % 3
            with cols[col_idx]:
                st.image(row["Image URL"] if row["Image URL"] != "N/A" else "https://via.placeholder.com/150", width=150)
                st.markdown(f"**{row['Title']}**")
                st.write(f"Price: {row['Price']}")
                if row["Product URL"] != "N/A":
                    st.markdown(f"[View Product]({row['Product URL']})")
                st.divider()
        
        # Show full dataframe and download options
        with st.expander("View all products data", expanded=False):
            st.dataframe(df, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                csv = df.to_csv(index=False)
                st.download_button("📥 Download CSV", csv, "fashion_data.csv", "text/csv")
            with col2:
                excel_buffer = pd.ExcelWriter("fashion_data.xlsx", engine="xlsxwriter")
                df.to_excel(excel_buffer, index=False)
                excel_buffer.close()
                st.download_button("📥 Download Excel", open("fashion_data.xlsx", "rb"), "fashion_data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab2:
    if 'scraped_data' in st.session_state:
        st.subheader("Data Analysis")
        data = st.session_state['scraped_data']
        df = pd.DataFrame(data)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Price statistics
            st.write("#### Price Analysis")
            
            # Extract numeric prices for analysis
            numeric_prices = []
            for p in df["Price"]:
                if p != "N/A":
                    # Extract numbers from the price string
                    num = re.search(r'[\d,.]+', p)
                    if num:
                        price_val = num.group(0).replace(',', '')
                        try:
                            numeric_prices.append(float(price_val))
                        except ValueError:
                            pass
            
            if numeric_prices:
                avg_price = sum(numeric_prices) / len(numeric_prices)
                st.write(f"Average Price: {avg_price:.2f}")
                st.write(f"Lowest Price: {min(numeric_prices):.2f}")
                st.write(f"Highest Price: {max(numeric_prices):.2f}")
            else:
                st.write("Could not extract numeric prices for analysis")
        
        with col2:
            # Color analysis
            st.write("#### Color Analysis")
            colors_list = []
            for colors in df["Colors"]:
                if colors != "N/A":
                    colors_list.extend([c.strip() for c in colors.split(",")])
            
            if colors_list:
                color_counts = {}
                for color in colors_list:
                    color_counts[color] = color_counts.get(color, 0) + 1
                
                # Display most common colors
                sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
                for color, count in sorted_colors[:5]:
                    st.write(f"{color}: {count} products")
            else:
                st.write("No color data available")
        
        # Word frequency in titles
        st.write("#### Common Keywords in Product Titles")
        all_titles = " ".join([title for title in df["Title"] if title != "N/A"])
        
        # Simple word frequency analysis
        words = re.findall(r'\b[a-zA-Z]{3,}\b', all_titles.lower())
        stopwords = ["the", "and", "for", "with", "this", "that", "you", "not", "from"]
        words = [word for word in words if word not in stopwords]
        
        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        
        # Display top words
        col1, col2, col3 = st.columns(3)
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        
        for i, (col, word_group) in enumerate(zip([col1, col2, col3], [sorted_words[:5], sorted_words[5:10], sorted_words[10:15]])):
            with col:
                for word, count in word_group:
                    st.write(f"{word}: {count}")

with tab3:
    st.subheader("Help & Tips")
    st.write("""
    ### How to use the Fashion Scraper:
    
    1. **Enter a URL** of a fashion website category or product listing page.
    2. **Configure the settings** in the sidebar:
       - Adjust the wait time if products aren't loading.
       - Select a site profile if results aren't accurate.
       - Enable pagination to scrape multiple pages.
    3. **Click Scrape** to start the process.
    
    ### Common issues:
    
    - **No products found**: Try increasing the wait time or selecting a specific site profile.
    - **Images not loading**: Some sites use lazy loading - try increasing the wait time.
    - **Getting blocked**: Try using a different user agent or reduce scraping speed.
    
    ### Supported websites:
    
    The scraper works best with common e-commerce platforms like Shopify, WooCommerce, and Magento.
    It also has specific profiles for popular fashion sites.
    
    ### Notes:
    
    - Be respectful of websites' terms of service.
    - Avoid excessive scraping that might impact site performance.
    - Consider using the scraper during off-peak hours.
    """)
    try:
        import json
        from datetime import datetime

        def load_history():
            try:
                with open("scrape_history.json", "r") as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return []

        site_type = "Generic"  # Replace with actual logic to determine site type
        products_count = 0  # Replace with actual count of scraped products

        history = load_history()
        history.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "url": url,
            "site_type": site_type,
            "products_count": products_count
        })
        with open("scrape_history.json", "w") as f:
            json.dump(history, f)
    except Exception as e:
        logger.error(f"Error saving history: {e}")

# Sidebar for configuration
with st.sidebar:
    st.title("⚙️ Scraper Settings")

    headless = st.checkbox("Run in headless mode", value=True,
                           help="Headless mode runs without showing the browser window",
                           key="headless_checkbox")

    wait_time = st.slider("Page load wait time (seconds)", 2, 10, 4,
                          help="How long to wait for dynamic content to load",
                          key="wait_time_slider")

    user_agent = st.text_input("Custom User Agent (optional)",
                               value="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
                               help="Using a common user agent can help avoid being blocked",
                               key="user_agent_input")

    pagination = st.checkbox("Enable pagination", value=False,
                              help="Scrape multiple pages if available",
                              key="pagination_checkbox")

    max_pages = st.number_input("Maximum pages to scrape", 1, 20, 3,
                                help="Limit the number of pages to avoid long scraping sessions",
                                key="max_pages_input")

    st.subheader("Site Profiles")
    site_profile = st.selectbox("Select a site profile (optional)",
                                ["Auto-detect", "Generic", "Shopify", "WooCommerce", "Magento", "Fashion Nova", "ASOS", "Zara"],
                                help="Select a specific site profile for better results",
                                key="site_profile_select")

    use_proxy = st.checkbox("Use proxy (advanced)", value=False,
                            help="Use a proxy server to avoid IP blocks",
                            key="proxy_checkbox")

    proxy_address = ""
    if use_proxy:
        proxy_address = st.text_input("Proxy Address (e.g., http://user:pass@ip:port)",
                                      help="Enter the proxy address in the format: http://user:pass@ip:port",
                                      key="proxy_input")

# Main content
st.title("🧵 Advanced Fashion Scraper")
st.markdown("Scrape fashion products from various online stores")

url = st.text_input("Enter a product or category URL:", key="product_url_input")

site_selectors = {
    "Generic": {
        "items": "article, .product, .product-card, .grid-item, li[id*='product'], div[class*='product'], [data-product-id]",
        "title": "h2, h3, h4, .product-title, .name, .title, [class*='product-name'], [class*='title']",
        "price": ".price, [class*='price'], .amount, .product-price, [data-price]",
        "regular_price": ".regular-price, .original-price, .compare-at-price, [class*='regular-price'], [class*='original-price']",
        "sale_price": ".sale-price, .special-price, [class*='sale-price'], [class*='special-price']",
        "image": "img",
        "link": "a",
        "description": ".description, [class*='description'], .excerpt, .summary, [class*='product-details']",
        "next_page": ".next, .pagination a:last-child, [class*='next'], a[rel='next'], a[aria-label*='Next']",
    },
    "Shopify": {
        "items": ".product-card, .grid__item, .product-item, [class*='product-card']",
        "title": ".product-card__title, .product-title, .product-item__title, h2, h3",
        "price": ".price, .product-price, [class*='price']",
        "regular_price": ".regular-price, .price__regular",
        "sale_price": ".sale-price, .price__sale",
        "image": "img",
        "link": "a",
        "description": ".description, .product-excerpt",
        "next_page": "a.pagination__next, .next a",
    },
    "WooCommerce": {
        "items": "li.product, .product-type-simple, .product-type-variable, .type-product",
        "title": "h2.woocommerce-loop-product__title, .product-title, h3",
        "price": ".price, .woocommerce-Price-amount",
        "regular_price": ".regular-price, del .woocommerce-Price-amount",
        "sale_price": ".sale-price, ins .woocommerce-Price-amount",
        "image": "img.wp-post-image, img.attachment-woocommerce_thumbnail",
        "link": "a.woocommerce-LoopProduct-link",
        "description": ".short-description, .woocommerce-product-details__short-description",
        "next_page": ".next.page-numbers",
    },
    "Magento": {
        "items": "li.item.product.product-item, .product-item, .product-items > li",
        "title": ".product-item-name, .product-name, a.product-item-link",
        "price": ".price, .price-container .price, [data-price-type='finalPrice']",
        "regular_price": "[data-price-type='oldPrice'], .old-price .price",
        "sale_price": "[data-price-type='finalPrice'], .special-price .price",
        "image": "img.product-image-photo",
        "link": "a.product-item-photo, a.product-item-link",
        "description": ".product-item-description, .description",
        "next_page": ".pages-item-next a",
    },
    "Fashion Nova": {
        "items": ".product-grid-item, .grid-item, [class*='product-item']",
        "title": ".product-name, .product-title, .name, h3",
        "price": ".price, .product-price",
        "regular_price": ".regular-price, .compare-at-price",
        "sale_price": ".special-price, .price--sale",
        "image": "img.product-featured-img, .product-image img",
        "link": "a.product-grid-item__link, a",
        "description": ".product-description",
        "next_page": ".pagination__next, .pagination-next",
    },
    "ASOS": {
        "items": "article[data-auto-id='productTile'], [data-test-id='product-card']",
        "title": "[data-auto-id='productTileDescription'], h2, .product-title",
        "price": "[data-auto-id='productTilePrice'], .current-price, [data-test-id='price']",
        "regular_price": ".previous-price, .was-price",
        "sale_price": ".current-price, .now-price",
        "image": "img",
        "link": "a[data-auto-id='productTileLink'], a",
        "description": ".product-description, .product-info",
        "next_page": "[data-auto-id='loadMoreProducts'], .pagination-next",
    },
    "Zara": {
        "items": ".product-item, .product, article[class*='product']",
        "title": ".product-info .name, .item-name, h3.product-info-item-name",
        "price": ".price, .product-info-price",
        "regular_price": ".original-price, .line-through",
        "sale_price": ".sale-price, .price-current",
        "image": "img.product-media, .media-image img",
        "link": "a.item, a.link",
        "description": ".description, .product-info-description",
        "next_page": ".next-page, .zds-button--pagination-next",
    },
}

def detect_site_type(page):
    """Try to detect the site platform based on page content"""
    page_content = page.content()
    
    if "shopify" in page_content.lower():
        return "Shopify"
    elif "woocommerce" in page_content.lower():
        return "WooCommerce"
    elif "magento" in page_content.lower():
        return "Magento"
    elif "fashionnova" in page.url.lower():
        return "Fashion Nova"
    elif "asos" in page.url.lower():
        return "ASOS"
    elif "zara" in page.url.lower():
        return "Zara"
    else:
        return "Generic"

def extract_currency_amount(price_text):
    """Extract currency and amount from price text"""
    if not price_text or price_text == "N/A":
        return {"currency": "", "amount": ""}
    
    # Try to extract currency symbol and amount
    currency_match = re.search(r'[$€£¥₹]|[A-Z]{3}', price_text)
    currency = currency_match.group(0) if currency_match else ""
    
    # Extract numeric value
    amount_match = re.search(r'[\d,.]+', price_text)
    amount = amount_match.group(0) if amount_match else ""
    
    return {"currency": currency, "amount": amount}

def clean_text(text):
    """Clean and normalize text"""
    if not text:
        return "N/A"
    # Remove extra whitespace, newlines, tabs
    cleaned = re.sub(r'\s+', ' ', text).strip()
    return cleaned

def extract_colors(text):
    """Try to identify color information in product text"""
    if not text or text == "N/A":
        return []
    
    common_colors = [
        "black", "white", "red", "blue", "green", "yellow", "purple", "pink", 
        "orange", "brown", "grey", "gray", "navy", "beige", "gold", "silver",
        "tan", "olive", "teal", "maroon", "ivory", "khaki"
    ]
    
    found_colors = []
    text_lower = text.lower()
    
    for color in common_colors:
        if color in text_lower:
            found_colors.append(color)
            
    return found_colors

def extract_sizes(text):
    """Try to identify size information in product text"""
    if not text or text == "N/A":
        return []
    
    # Common size patterns
    size_patterns = [
        r'\b(?:size|sizes?)\s*(?::|is|are)?\s*([XxSsLlMm0-9,\s/]+)',  # Size: S/M/L
        r'\b([XxSsLlMm]+)\b',  # S, M, L, XL, XXL
        r'\b(\d+(?:\.\d+)?)\s*(?:cm|inch|")\b'  # 32", 34cm
    ]
    
    found_sizes = []
    for pattern in size_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            for match in matches:
                # Clean up and add to results
                clean_size = match.strip().upper()
                if clean_size and clean_size not in found_sizes:
                    found_sizes.append(clean_size)
    
    return found_sizes

def extract_brand(text, title):
    """Try to identify brand information"""
    common_brand_indicators = [
        r'by\s+([A-Za-z0-9\s&]+)',
        r'brand:?\s*([A-Za-z0-9\s&]+)',
        r'from\s+([A-Za-z0-9\s&]+)'
    ]
    
    for pattern in common_brand_indicators:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    # If no brand found in description, try to extract from the first word of the title
    # as many product titles start with the brand name
    title_words = title.split()
    if title_words and len(title_words[0]) > 2:
        return title_words[0]
    
    return "N/A"

def scrape_fashion_site(url, selectors, wait_time, user_agent, headless=True, proxy=None):
    with sync_playwright() as p:
        browser_args = []
        if user_agent:
            browser_args.append(f'--user-agent={user_agent}')
        
        # Configure proxy if provided
        proxy_config = None
        if proxy:
            proxy_config = {"server": proxy}
        
        browser = p.chromium.launch(headless=headless, args=browser_args)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            proxy=proxy_config
        )
        page = context.new_page()
        
        # Set up request interception to avoid unnecessary resources
        page.route("**/*.{png,jpg,jpeg,gif,svg,pdf,mp4,webp}", lambda route: route.abort() if random.random() > 0.4 else route.continue_())
        
        logger.info(f"Navigating to {url}")
        try:
            page.goto(url, timeout=60000)
        except Exception as e:
            logger.error(f"Error navigating to URL: {e}")
            browser.close()
            return []
        
        # Add some randomization to wait times to seem more human-like
        jittered_wait = wait_time + random.uniform(0, 1)
        page.wait_for_timeout(int(jittered_wait * 1000))
        
        # If site profile is auto-detect, try to detect the site type
        if site_profile == "Auto-detect":
            detected_type = detect_site_type(page)
            current_selectors = site_selectors[detected_type]
            st.info(f"Detected site type: {detected_type}")
        else:
            current_selectors = selectors
        
        all_data = []
        current_url = url
        pages_scraped = 0
        detected_type = site_profile if site_profile != "Auto-detect" else detect_site_type(page)
        
        while True:
            pages_scraped += 1
            logger.info(f"Scraping page {pages_scraped}: {current_url}")
            
            # Let the page fully load
            page.wait_for_timeout(int(jittered_wait * 1000))
            
            # Handle cookie banners or popups that might interfere
            try:
                for selector in [".cookie-banner button", "#cookie-accept", ".popup-close", ".modal-close", 
                                "[class*='cookie'] button", "[class*='popup'] button", "[class*='modal'] button"]:
                    close_buttons = page.query_selector_all(selector)
                    for button in close_buttons:
                        button.click()
                        page.wait_for_timeout(500)
            except Exception:
                pass
            
            # Scroll down the page to load lazy-loaded images
            page.evaluate("""
                () => {
                    window.scrollTo(0, 0);
                    let totalHeight = 0;
                    let distance = 300;
                    let timer = setInterval(() => {
                        let scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        
                        if(totalHeight >= scrollHeight){
                            clearInterval(timer);
                        }
                    }, 100);
                }
            """)
            
            page.wait_for_timeout(1000)
            
            # Try to get product blocks
            items = page.query_selector_all(current_selectors["items"])
            
            if not items:
                # If no items found with main selector, try alternative selectors
                fallback_selectors = [
                    "div[id*='product'], li[class*='product']",
                    "[data-product], [data-product-id]",
                    ".item, .grid-item, .collection-item",
                    "article, .card, .product-card"
                ]
                
                for selector in fallback_selectors:
                    items = page.query_selector_all(selector)
                    if items:
                        break
                        
            page_data = []
            for item in items:
                try:
                    # Title extraction
                    title_el = item.query_selector(current_selectors["title"])
                    title = clean_text(title_el.inner_text() if title_el else "N/A")
                    
                    # Price extraction - try to get sale and regular price
                    price_el = item.query_selector(current_selectors["price"])
                    price_text = clean_text(price_el.inner_text() if price_el else "N/A")
                    
                    regular_price_el = item.query_selector(current_selectors["regular_price"])
                    regular_price = clean_text(regular_price_el.inner_text() if regular_price_el else price_text)
                    
                    sale_price_el = item.query_selector(current_selectors["sale_price"])
                    sale_price = clean_text(sale_price_el.inner_text() if sale_price_el else "")
                    
                    if not sale_price and regular_price != price_text:
                        sale_price = price_text
                    
                    # Image extraction
                    img_el = item.query_selector(current_selectors["image"])
                    img_src = ""
                    if img_el:
                        # Try different attributes that might contain the image URL
                        for attr in ["src", "data-src", "srcset", "data-srcset", "data-lazy-src"]:
                            img_src = img_el.get_attribute(attr)
                            if img_src:
                                # If srcset, extract the first URL
                                if "srcset" in attr:
                                    img_src = img_src.split(",")[0].strip().split(" ")[0]
                                break
                    
                    img_url = urljoin(url, img_src) if img_src else "N/A"
                    
                    # Product link extraction
                    link_el = item.query_selector(current_selectors["link"])
                    product_url = urljoin(url, link_el.get_attribute("href")) if link_el else "N/A"
                    
                    # Description extraction
                    desc_el = item.query_selector(current_selectors["description"])
                    description = clean_text(desc_el.inner_text() if desc_el else "N/A")
                    
                    # Try to extract colors, sizes, and brand
                    combined_text = f"{title} {description}"
                    colors = extract_colors(combined_text)
                    sizes = extract_sizes(combined_text)
                    brand = extract_brand(combined_text, title)
                    
                    # Extract currency and amount
                    price_details = extract_currency_amount(price_text)
                    
                    # Check if product is on sale
                    on_sale = bool(sale_price and sale_price != regular_price)
                    
                    # Get site domain for reference
                    domain = urlparse(url).netloc
                    
                    # Add timestamp for when this was scraped
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    product_data = {
                        "Title": title,
                        "Brand": brand,
                        "Price": price_text,
                        "Regular Price": regular_price,
                        "Sale Price": sale_price if on_sale else "N/A",
                        "On Sale": "Yes" if on_sale else "No",
                        "Currency": price_details["currency"],
                        "Price Amount": price_details["amount"],
                        "Image URL": img_url,
                        "Product URL": product_url,
                        "Description": description,
                        "Colors": ", ".join(colors) if colors else "N/A",
                        "Sizes": ", ".join(sizes) if sizes else "N/A",
                        "Source Site": domain,
                        "Platform": detected_type,
                        "Scraped Date": timestamp,
                        "Page Number": pages_scraped
                    }
                    
                    page_data.append(product_data)
                except Exception as e:
                    logger.error(f"Error extracting product data: {e}")
                    continue
            
            all_data.extend(page_data)
            
            # Check for pagination
            if pagination and pages_scraped < max_pages:
                next_page_link = page.query_selector(current_selectors["next_page"])
                if next_page_link:
                    next_page_url = next_page_link.get_attribute("href")
                    if next_page_url:
                        current_url = urljoin(url, next_page_url)
                        logger.info(f"Found next page: {current_url}")
                        page.goto(current_url, timeout=60000)
                        # Add randomized delay between page navigations
                        page.wait_for_timeout(int((wait_time + random.uniform(1, 2)) * 1000))
                        continue
            
            # If no pagination or reached max pages, break the loop
            break
        
        # Save scraping history
        if all_data:
            save_history(url, detected_type, len(all_data))
        
        browser.close()
        return all_data

# Create tabs for different features
tab1, tab2, tab3, tab4 = st.tabs(["Scraper", "Results Analysis", "History", "Help"])

with tab1:
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔍 Scrape", key="scrape_button_tab1", type="primary"):
            if url:
                with st.spinner("Scraping website... This may take a minute"):
                    try:
                        # Use the selected site profile selectors
                        current_selectors = site_selectors[site_profile] if site_profile != "Auto-detect" else site_selectors["Generic"]
                        
                        # Handle proxy if enabled
                        proxy_str = proxy_address if use_proxy else None
                        
                        data = scrape_fashion_site(url, current_selectors, wait_time, user_agent, headless, proxy_str)
                        
                        if data:
                            st.session_state['scraped_data'] = data
                            st.session_state['last_scraped_url'] = url
                            st.success(f"✅ Successfully scraped {len(data)} products!")
                        else:
                            st.warning("No product data found on this page. Try adjusting the scraper settings or selecting a different site profile.")
                    except Exception as e:
                        st.error(f"Error: {e}")
                        st.info("Try adjusting the wait time, checking the URL, or selecting a specific site profile.")
            else:
                st.warning("Please enter a URL.")
    
    with col2:
        st.write("Try these example URLs:")
        example_urls = {
            "Example Fashion Site": "https://www.example-fashion-site.com/collections/new-arrivals",
            "Demo Shop": "https://demo.shopify.com/collections/all",
            "WordPress Demo": "https://woocommerce.com/products/storefront/",
        }
        
    for i, (name, example_url) in enumerate(example_urls.items()):
        if st.button(name, key=f"example_btn_{i}"):
            st.session_state['url'] = example_url
            st.experimental_rerun()
    
    if 'scraped_data' in st.session_state:
        data = st.session_state['scraped_data']
        df = pd.DataFrame(data)
        
        st.subheader("Scraped Products")
        
        # Search and filter options
        col1, col2, col3 = st.columns(3)
        with col1:
            search_term = st.text_input("Search products:", placeholder="Enter keywords...")
        with col2:
            if 'Brand' in df.columns and df['Brand'].nunique() > 1:
                brands = ['All'] + sorted(df['Brand'].unique().tolist())
                selected_brand = st.selectbox("Filter by brand:", brands)
        with col3:
            sort_by = st.selectbox("Sort by:", ["Default", "Price: Low to High", "Price: High to Low", "Title A-Z"])
        
        # Apply filters
        filtered_df = df.copy()
        
        if search_term:
            filtered_df = filtered_df[filtered_df['Title'].str.contains(search_term, case=False) | 
                                    filtered_df['Description'].str.contains(search_term, case=False)]
        
        if 'Brand' in df.columns and selected_brand != 'All':
            filtered_df = filtered_df[filtered_df['Brand'] == selected_brand]
        
        # Apply sorting
        if sort_by == "Price: Low to High":
            # Convert Price Amount to float for sorting
            filtered_df['Sort_Price'] = pd.to_numeric(filtered_df['Price Amount'].str.replace(',', ''), errors='coerce')
            filtered_df = filtered_df.sort_values('Sort_Price')
        elif sort_by == "Price: High to Low":
            filtered_df['Sort_Price'] = pd.to_numeric(filtered_df['Price Amount'].str.replace(',', ''), errors='coerce')
            filtered_df = filtered_df.sort_values('Sort_Price', ascending=False)
        elif sort_by == "Title A-Z":
            filtered_df = filtered_df.sort_values('Title')
        
        st.write(f"Showing {len(filtered_df)} of {len(df)} products")
        
        # Display product grid
        num_columns = 3
        rows = (len(filtered_df) + num_columns - 1) // num_columns  # Ceiling division
        
        # Limit display to first 24 products to avoid performance issues
        display_df = filtered_df.head(24)
        
        for i in range(min(rows, 8)):  # Maximum 8 rows (24 products)
            cols = st.columns(num_columns)
            for j in range(num_columns):
                idx = i * num_columns + j
                if idx < len(display_df):
                    row = display_df.iloc[idx]
                    with cols[j]:
                        # Display product card
                        st.image(row["Image URL"] if row["Image URL"] != "N/A" else "https://via.placeholder.com/150", width=150)
                        st.markdown(f"**{row['Title']}**")
                        
                        # Display brand if available
                        if 'Brand' in row and row['Brand'] != "N/A":
                            st.text(f"Brand: {row['Brand']}")
                            
                        # Display price with sale info if available
                        if row["On Sale"] == "Yes":
                            st.markdown(f"~~{row['Regular Price']}~~ **{row['Sale Price']}** 🔥")
                        else:
                            st.write(f"Price: {row['Price']}")
                            
                        # Display colors if available
                        if row["Colors"] != "N/A":
                            st.text(f"Colors: {row['Colors']}")
                            
                        if row["Product URL"] != "N/A":
                            st.markdown(f"[View Product]({row['Product URL']})")
                        st.divider()
        
        if len(filtered_df) > 24:
            st.info(f"Showing first 24 of {len(filtered_df)} products. Download the full data to see all products.")
        
        # Show full dataframe and download options
        with st.expander("View all products data", expanded=False):
            st.dataframe(filtered_df, use_container_width=True)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                csv = filtered_df.to_csv(index=False)
                st.download_button("📥 Download CSV", csv, "fashion_data.csv", "text/csv")
            with col2:
                # Create Excel file
                filename = "fashion_data.xlsx"
                filtered_df.to_excel(filename, index=False, engine="xlsxwriter")
                with open(filename, "rb") as f:
                    excel_data = f.read()
                st.download_button("📥 Download Excel", excel_data, filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            with col3:
                # Download as JSON
                json_str = filtered_df.to_json(orient="records")
                st.download_button("📥 Download JSON", json_str, "fashion_data.json", "application/json")

with tab2:
    if 'scraped_data' in st.session_state:
        st.subheader("Data Analysis")
        data = st.session_state['scraped_data']
        df = pd.DataFrame(data)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Price statistics
            st.write("#### Price Analysis")
            
            # Extract numeric prices for analysis
            numeric_prices = []
            for p in df["Price"]:
                if p != "N/A":
                    # Extract numbers from the price string
                    num = re.search(r'[\d,.]+', p)
                    if num:
                        price_val = num.group(0).replace(',', '')
                        try:
                            numeric_prices.append(float(price_val))
                        except ValueError:
                            pass
            
            if numeric_prices:
                avg_price = sum(numeric_prices) / len(numeric_prices)
                
                # Create a simple price distribution chart
                price_ranges = [0, 25, 50, 100, 200, 500, 1000, float('inf')]
                range_labels = ['$0-25', '$25-50', '$50-100', '$100-200', '$200-500', '$500-1000', '$1000+']
                
                price_distribution = [0] * len(range_labels)
                for price in numeric_prices:
                    for i, upper in enumerate(price_ranges[1:]):
                        if price < upper:
                            price_distribution[i] += 1
                            break
                
                price_dist_df = pd.DataFrame({
                    'Price Range': range_labels,
                    'Count': price_distribution
                })
                
                # Display stats
                st.write(f"Average Price: ${avg_price:.2f}")
                st.write(f"Lowest Price: ${min(numeric_prices):.2f}")
                st.write(f"Highest Price: ${max(numeric_prices):.2f}")
                
                # Display chart
                fig = px.bar(price_dist_df, x='Price Range', y='Count', title='Price Distribution')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("Could not extract numeric prices for analysis")
        
        with col2:
            # Color analysis
            st.write("#### Color Analysis")
            colors_list = []
            for colors in df["Colors"]:
                if colors != "N/A":
                    colors_list.extend([c.strip() for c in colors.split(",")])
            
            if colors_list:
                color_counts = {}
                for color in colors_list:
                     color_counts[color] = color_counts.get(color, 0) + 1
                
                # Create a color distribution chart
                color_df = pd.DataFrame({
                    'Color': list(color_counts.keys()),
                    'Count': list(color_counts.values())
                }).sort_values('Count', ascending=False).head(10)  # Show top 10 colors
                
                # Display color chart
                fig = px.bar(color_df, x='Color', y='Count', title='Most Common Colors')
                st.plotly_chart(fig, use_container_width=True)
                
                # Display top colors as text
                st.write("Top colors found:")
                for color, count in sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                    st.write(f"- {color.capitalize()}: {count} products")
            else:
                st.write("No color data available")
        
        # Brand analysis if available
        if 'Brand' in df.columns and df['Brand'].nunique() > 1 and not all(df['Brand'] == 'N/A'):
            st.write("#### Brand Analysis")
            
            # Count brands
            brand_counts = df['Brand'].value_counts().reset_index()
            brand_counts.columns = ['Brand', 'Count']
            brand_counts = brand_counts[brand_counts['Brand'] != 'N/A'].head(10)
            
            if not brand_counts.empty:
                # Display brand chart
                fig = px.pie(brand_counts, values='Count', names='Brand', title='Brand Distribution')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("No brand data available")
        
        # Word frequency in titles
        st.write("#### Common Keywords in Product Titles")
        all_titles = " ".join([title for title in df["Title"] if title != "N/A"])
        
        # Simple word frequency analysis
        words = re.findall(r'\b[a-zA-Z]{3,}\b', all_titles.lower())
        stopwords = ["the", "and", "for", "with", "this", "that", "you", "not", "from", "has", "are", "our", "your"]
        words = [word for word in words if word not in stopwords]
        
        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        
        # Create word cloud data
        word_df = pd.DataFrame({
            'Word': list(word_counts.keys()),
            'Count': list(word_counts.values())
        }).sort_values('Count', ascending=False).head(50)  # Top 50 words for word cloud
        
        # Display word cloud visualization
        if not word_df.empty:
            fig = px.treemap(word_df, 
                           path=['Word'], 
                           values='Count',
                           title='Product Title Word Cloud')
            fig.update_traces(textinfo="label+value")
            st.plotly_chart(fig, use_container_width=True)
        
        # Display top words as text
        col1, col2, col3 = st.columns(3)
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        
        for i, (col, word_group) in enumerate(zip([col1, col2, col3], [sorted_words[:10], sorted_words[10:20], sorted_words[20:30]])):
            with col:
                st.write(f"**Top words {i*10+1}-{i*10+10}**")
                for word, count in word_group:
                    st.write(f"- {word}: {count}")
        
        # Sale analysis
        if "On Sale" in df.columns:
            st.write("#### Sale Analysis")
            
            # Count products on sale vs. regular price
            sale_counts = df["On Sale"].value_counts().reset_index()
            sale_counts.columns = ['On Sale', 'Count']
            
            # Display sale distribution
            fig = px.pie(sale_counts, values='Count', names='On Sale', 
                        title='Products on Sale vs Regular Price',
                        color_discrete_map={'Yes': 'red', 'No': 'green'})
            st.plotly_chart(fig, use_container_width=True)
            
            # Calculate average discount if possible
            if "Regular Price" in df.columns and "Sale Price" in df.columns:
                try:
                    # Extract numeric values
                    df['Regular Price Num'] = df["Regular Price"].apply(
                        lambda x: float(re.search(r'[\d,.]+', x).group(0).replace(',', '')) if x != "N/A" and re.search(r'[\d,.]+', x) else None
                    )
                    df['Sale Price Num'] = df["Sale Price"].apply(
                        lambda x: float(re.search(r'[\d,.]+', x).group(0).replace(',', '')) if x != "N/A" and re.search(r'[\d,.]+', x) else None
                    )
                    
                    # Calculate discount and discount percentage
                    sale_items = df[df['On Sale'] == 'Yes'].copy()
                    sale_items = sale_items.dropna(subset=['Regular Price Num', 'Sale Price Num'])
                    
                    if len(sale_items) > 0:
                        sale_items['Discount'] = sale_items['Regular Price Num'] - sale_items['Sale Price Num']
                        sale_items['Discount Percentage'] = (sale_items['Discount'] / sale_items['Regular Price Num']) * 100
                        
                        avg_discount_pct = sale_items['Discount Percentage'].mean()
                        
                        st.write(f"Average discount: {avg_discount_pct:.1f}%")
                        st.write(f"Highest discount: {sale_items['Discount Percentage'].max():.1f}%")
                        st.write(f"Total items on sale: {len(sale_items)}")
                except Exception as e:
                    st.write("Could not calculate discount statistics")
                    st.write(f"Error: {e}")

with tab3:
    st.subheader("Scraping History")
    
    # Function to load history from file
    def load_history():
        try:
            with open("scrape_history.json", "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    # Function to save history to file
    def save_history(url, site_type, products_count):
        try:
            history = load_history()
            history.append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "url": url,
                "site_type": site_type,
                "products_count": products_count
            })
            with open("scrape_history.json", "w") as f:
                json.dump(history, f)
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    # Display history
    history = load_history()
    
    if history:
        history_df = pd.DataFrame(history)
        history_df = history_df.sort_values('date', ascending=False)
        
        # Display history table
        st.dataframe(history_df, use_container_width=True)
        
        # Add a button to clear history
        if st.button("Clear History"):
            try:
                with open("scrape_history.json", "w") as f:
                    json.dump([], f)
                st.success("History cleared!")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Failed to clear history: {e}")
    else:
        st.info("No scraping history available yet. Use the scraper tab to start collecting data.")
    
    # Add analytics based on history
    if history and len(history) > 1:
        st.subheader("Scraping Analytics")
        
        # Create analytics charts
        col1, col2 = st.columns(2)
        
        with col1:
            # Count of scrapes by site type
            site_counts = {}
            for entry in history:
                site_type = entry.get('site_type', 'Unknown')
                site_counts[site_type] = site_counts.get(site_type, 0) + 1
            
            site_df = pd.DataFrame({
                'Site Type': list(site_counts.keys()),
                'Count': list(site_counts.values())
            })
            
            fig = px.bar(site_df, x='Site Type', y='Count', title='Scrapes by Platform')
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Products scraped over time
            dates = []
            counts = []
            for entry in history:
                dates.append(entry.get('date', ''))
                counts.append(entry.get('products_count', 0))
            
            time_df = pd.DataFrame({
                'Date': dates,
                'Products': counts
            })
            
            fig = px.line(time_df, x='Date', y='Products', title='Products Scraped Over Time')
            st.plotly_chart(fig, use_container_width=True)
        
        # Summary statistics
        st.write(f"Total scraping sessions: {len(history)}")
        st.write(f"Total products scraped: {sum(counts)}")
        st.write(f"Average products per scrape: {sum(counts)/len(counts):.1f}")

with tab4:
    st.subheader("Help & Tips")
    st.write("""
    ### How to use the Fashion Scraper:
    
    1. **Enter a URL** of a fashion website category or product listing page.
    2. **Configure the settings** in the sidebar:
       - Adjust the wait time if products aren't loading.
       - Select a site profile if results aren't accurate.
       - Enable pagination to scrape multiple pages.
       - Enable proxy if you're experiencing IP blocks.
    3. **Click Scrape** to start the process.
    
    ### Common issues and solutions:
    
    - **No products found**: Try increasing the wait time or selecting a specific site profile.
    - **Images not loading**: Some sites use lazy loading - try increasing the wait time.
    - **Getting blocked**: Try using a different user agent or enable the proxy option.
    - **Incomplete data**: Some websites structure their data differently - try a different site profile.
    
    ### Supported websites:
    
    The scraper works best with common e-commerce platforms like:
    - Shopify
    - WooCommerce
    - Magento
    
    It also has specific profiles for popular fashion sites like:
    - Fashion Nova
    - ASOS
    - Zara
    
    ### Ethical considerations:
    
    - Be respectful of websites' terms of service.
    - Avoid excessive scraping that might impact site performance.
    - Consider using the scraper during off-peak hours.
    - Use data for personal research only and respect copyright.
    
    ### Tips for better results:
    
    - Start with a specific category page rather than the homepage
    - Use longer wait times for image-heavy websites
    - Enable pagination for sites with many pages
    - Try different site profiles if the default doesn't work well
    - Use the analysis tab to get insights from your scraped data
    """)
    
    # FAQs as expandable sections
    st.subheader("Frequently Asked Questions")
    
    with st.expander("How do I find the right URL to scrape?"):
        st.write("""
        The best URLs to scrape are product category or collection pages. These typically look like:
        - `https://store.com/collections/dresses`
        - `https://store.com/product-category/mens`
        - `https://store.com/shop/shoes`
        
        Navigate to the category you're interested in on the shopping site, then copy the URL from your browser.
        """)
    
    with st.expander("Why am I getting blocked by some websites?"):
        st.write("""
        Some websites have anti-scraping measures. To reduce the chance of being blocked:
        
        1. Use a realistic user agent (already set by default)
        2. Enable the proxy option if available
        3. Increase the wait time to seem more like a human user
        4. Don't scrape too many pages in one session
        5. Avoid scraping the same site repeatedly in a short timeframe
        """)
    
    with st.expander("How can I export my data?"):
        st.write("""
        After scraping, you can export your data in several formats:
        
        1. Click on "View all products data" to expand the full data table
        2. Use one of the download buttons:
           - Download CSV - for use in Excel, Google Sheets, etc.
           - Download Excel - for direct use in Microsoft Excel
           - Download JSON - for use in programming and data analysis
        
        The files will be saved to your default downloads folder.
        """)
    
    with st.expander("Why are some fields showing 'N/A'?"):
        st.write("""
        'N/A' values appear when the scraper couldn't find certain information. This can happen because:
        
        1. The website doesn't include that information
        2. The information is structured differently than expected
        3. The data is loaded dynamically and wasn't captured
        
        Try selecting a different site profile or increasing the wait time to improve results.
        """)
    
    # Contact and feedback
    st.subheader("Contact & Feedback")
    st.write("""
    If you have suggestions for improving the scraper or want to report issues, please:
    
    - Submit an issue on our GitHub repository
    - Contact us at feedback@example.com
    - Join our Discord community for support
    
    We're constantly working to improve the tool based on user feedback!
    """)
    