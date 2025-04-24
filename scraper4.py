import os
import re
import json
import time
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urljoin, quote_plus
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from io import BytesIO
from PIL import Image


class AdidasScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.base_url = None
        self.output_dir = "products"
        
        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # Create images directory if it doesn't exist
        img_dir = os.path.join(self.output_dir, "images")
        if not os.path.exists(img_dir):
            os.makedirs(img_dir)
    
    def init_driver(self):
        """Initialize and return a Chrome webdriver"""
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-web-security")
        
        # Add user-agent to avoid bot detection
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        
        # Disable logging
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    
    def close_driver(self):
        """Close the webdriver if it exists"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def search_products(self, query, category=None):
        """Search for products based on user query and optional category"""
        if not self.driver:
            self.driver = self.init_driver()
        
        # Construct search URL
        if category:
            url = f"{self.base_url}/{category}/search/?q={quote_plus(query)}"
        else:
            url = f"{self.base_url}/search?q={quote_plus(query)}"
        
        st.info(f"Searching for '{query}' at {url}")
        
        # Navigate to search page
        self.driver.get(url)
        time.sleep(3)  # Initial wait for page load
        
        # Scroll to load lazy content
        self._scroll_page()
        
        # Extract products
        return self._extract_products()
    
    def get_trending_products(self):
        """Get trending products from Adidas"""
        if not self.driver:
            self.driver = self.init_driver()
        
        url = f"{self.base_url}/trending"
        st.info(f"Getting trending products from {url}")
        
        # Navigate to trending page
        self.driver.get(url)
        time.sleep(3)  # Initial wait for page load
        
        # Scroll to load lazy content
        self._scroll_page()
        
        # Extract products
        return self._extract_products()
    
    def get_product_details(self, product_url):
        """Get detailed information for a specific product"""
        if not self.driver:
            self.driver = self.init_driver()
        
        # Make sure URL is absolute
        if not product_url.startswith('http'):
            product_url = urljoin(self.base_url, product_url)
        
        st.info(f"Getting details for product at {product_url}")
        
        # Navigate to product page
        self.driver.get(product_url)
        time.sleep(3)  # Wait for page load
        
        # Extract product details
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        
        # Extract product images
        image_urls = []
        for img in soup.select('img[data-auto-id="image"]'):
            if 'src' in img.attrs:
                image_url = img['src']
                if image_url.startswith('//'):
                    image_url = 'https:' + image_url
                image_urls.append(image_url)
        
        # If no images found with the selector, try a different approach
        if not image_urls:
            for img in soup.select('img[srcset]'):
                if 'src' in img.attrs:
                    image_url = img['src']
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url
                    image_urls.append(image_url)
        
        # Extract product name
        name = ""
        name_elem = soup.select_one('[data-auto-id="product-title"], .product-title, h1')
        if name_elem:
            name = name_elem.text.strip()
        
        # Extract product price
        price = ""
        price_elem = soup.select_one('[data-auto-id="product-price"], .product-price, .price')
        if price_elem:
            price = price_elem.text.strip()
        
        # Extract product description
        description = ""
        desc_elem = soup.select_one('[data-auto-id="product-description"], .product-description')
        if desc_elem:
            description = desc_elem.text.strip()
        
        # Extract product SKU/ID
        product_id = ""
        id_elem = soup.select_one('[data-auto-id="product-identification"]')
        if id_elem:
            id_match = re.search(r'[A-Z0-9]{6}', id_elem.text)
            if id_match:
                product_id = id_match.group(0)
        
        if not product_id:
            # Try to extract from URL
            id_match = re.search(r'/([A-Z0-9]{6})\.html', product_url)
            if id_match:
                product_id = id_match.group(1)
        
        return {
            "name": name,
            "price": price,
            "description": description,
            "product_id": product_id,
            "url": product_url,
            "image_urls": image_urls
        }
    
    def _scroll_page(self):
        """Scroll the page to load lazy content"""
        with st.status("Scrolling to load all products..."):
            # Get initial page height
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            
            # Scroll down incrementally and wait for content to load
            for i in range(5):
                # Scroll down
                self.driver.execute_script(f"window.scrollTo(0, {(i+1) * 1000});")
                time.sleep(1)  # Wait for content to load
                
                # Get new page height
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                
                # Break if no more content is loading
                if new_height == last_height:
                    break
                
                last_height = new_height
            
            # Scroll back to top
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
    
    def _extract_products(self):
        """Extract product information from the current page"""
        products = []
        
        # Save page source and screenshot for potential debugging
        page_source = self.driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Method 1: Try to extract products using JSON data in script tags
        json_products = self._extract_from_json(soup)
        if json_products:
            st.success(f"Found {len(json_products)} products from JSON data")
            products.extend(json_products)
        
        # Method 2: Try to extract products from HTML structure
        html_products = self._extract_from_html(soup)
        if html_products:
            st.success(f"Found {len(html_products)} products from HTML")
            products.extend(html_products)
        
        # Method 3: Try to extract products using JavaScript
        js_products = self._extract_with_js()
        if js_products:
            st.success(f"Found {len(js_products)} products from JavaScript")
            products.extend(js_products)
        
        # Deduplicate products
        unique_products = []
        seen_urls = set()
        
        for product in products:
            url = product.get('url', '')
            name = product.get('name', '')
            
            # Create a unique identifier based on URL or name
            identifier = url if url else name
            
            if identifier and identifier not in seen_urls:
                seen_urls.add(identifier)
                unique_products.append(product)
        
        st.success(f"Found {len(unique_products)} unique products")
        return unique_products
    
    def _extract_from_json(self, soup):
        """Extract product info from JSON data in script tags"""
        products = []
        script_tags = soup.find_all('script')
        
        for script in script_tags:
            if not script.string:
                continue
                
            if any(marker in script.string for marker in ['window.ENV', 'window.__INITIAL_STATE__', 'productData']):
                try:
                    # Try to find JSON data with product information
                    json_match = re.search(r'\{.*?"products".*?\}', script.string)
                    if json_match:
                        data = json.loads(json_match.group(0))
                        
                        if isinstance(data, dict) and 'products' in data:
                            products_data = data['products']
                            for product in products_data:
                                try:
                                    product_id = product.get('productId', '')
                                    url = f"{self.base_url}/{product_id}.html"
                                    
                                    products.append({
                                        'name': product.get('displayName', product.get('name', '')),
                                        'price': f"${product.get('price', '')}",
                                        'url': url,
                                        'image_url': product.get('image', {}).get('src', ''),
                                        'product_id': product_id
                                    })
                                except:
                                    continue
                except Exception as e:
                    st.warning(f"Error extracting JSON data: {e}")
        
        return products
    
    def _extract_from_html(self, soup):
        """Extract product info from HTML structure"""
        products = []
        
        # Try different selectors for product cards
        selectors = [
            "div[data-auto-id='glass-product-card']",
            "div[data-auto-id='product-card']",
            "div.glass-product-card",
            "div.gl-product-card",
            "li.product-item"
        ]
        
        for selector in selectors:
            product_elements = soup.select(selector)
            if product_elements:
                break
        
        # If no products found with specific selectors, try a broader approach
        if not product_elements:
            product_grid = soup.select_one("div.product-grid, section.product-grid")
            if product_grid:
                product_elements = product_grid.select("div")
        
        # Process each product element
        for element in product_elements:
            try:
                # Extract product name
                name_elem = element.select_one('h2, h3, .name, .title, [data-auto-id="product-card-title"]')
                name = name_elem.text.strip() if name_elem else ""
                
                # Extract product price
                price_elem = element.select_one('.price, .gl-price, [data-auto-id="product-price"]')
                price = price_elem.text.strip() if price_elem else ""
                
                # Extract product URL
                link_elem = element.select_one('a')
                url = link_elem['href'] if link_elem and 'href' in link_elem.attrs else ""
                
                # Make URL absolute if it's relative
                if url and not url.startswith('http'):
                    url = urljoin(self.base_url, url)
                
                # Extract product image
                img_elem = element.select_one('img')
                image_url = ""
                if img_elem:
                    if 'src' in img_elem.attrs:
                        image_url = img_elem['src']
                    elif 'data-src' in img_elem.attrs:
                        image_url = img_elem['data-src']
                    elif 'srcset' in img_elem.attrs:
                        srcset = img_elem['srcset']
                        src_match = re.search(r'(https?://[^\s]+)', srcset)
                        if src_match:
                            image_url = src_match.group(1)
                
                # Make image URL absolute if it's relative
                if image_url and image_url.startswith('//'):
                    image_url = 'https:' + image_url
                
                # Extract product ID from URL
                product_id = ""
                id_match = re.search(r'/([A-Z0-9]{6})\.html', url)
                if id_match:
                    product_id = id_match.group(1)
                
                # Add product only if we have at least a name or URL
                if name or url:
                    products.append({
                        'name': name,
                        'price': price,
                        'url': url,
                        'image_url': image_url,
                        'product_id': product_id
                    })
            except Exception as e:
                st.warning(f"Error extracting product from HTML: {e}")
        
        return products
    
    def _extract_with_js(self):
        """Extract product info using JavaScript execution"""
        try:
            # Use JavaScript to extract product information
            products_data = self.driver.execute_script("""
                const products = [];
                document.querySelectorAll('[data-auto-id="product-card"], .gl-product-card, .glass-product-card, .product-item').forEach(card => {
                    try {
                        const nameEl = card.querySelector('[data-auto-id="product-card-title"], .name, h2, h3');
                        const priceEl = card.querySelector('[data-auto-id="product-price"], .price');
                        const linkEl = card.querySelector('a');
                        const imgEl = card.querySelector('img');
                        
                        const name = nameEl ? nameEl.textContent.trim() : '';
                        const price = priceEl ? priceEl.textContent.trim() : '';
                        const url = linkEl ? linkEl.href : '';
                        const imgUrl = imgEl ? (imgEl.src || imgEl.dataset.src || '') : '';
                        
                        // Extract product ID from URL
                        let productId = '';
                        const idMatch = url.match(/\/([A-Z0-9]{6})\.html/);
                        if (idMatch) {
                            productId = idMatch[1];
                        }
                        
                        if (name || url) {
                            products.push({
                                name,
                                price,
                                url,
                                imgUrl,
                                productId
                            });
                        }
                    } catch (e) {
                        // Skip this product if there's an error
                    }
                });
                return products;
            """)
            
            # Format results
            products = []
            for item in products_data:
                products.append({
                    'name': item.get('name', ''),
                    'price': item.get('price', ''),
                    'url': item.get('url', ''),
                    'image_url': item.get('imgUrl', ''),
                    'product_id': item.get('productId', '')
                })
            
            return products
        except Exception as e:
            st.warning(f"Error extracting products with JavaScript: {e}")
            return []
    
    def fetch_product_image(self, image_url):
        """Fetch product image and return as PIL Image"""
        try:
            if not image_url:
                return None
                
            response = requests.get(image_url, stream=True, timeout=10)
            if response.status_code == 200:
                return Image.open(BytesIO(response.content))
            return None
        except Exception as e:
            st.warning(f"Error fetching image: {e}")
            return None


# Streamlit app
def main():
    st.set_page_config(
        page_title="Adidas Product Scraper",
        page_icon="👟",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("Adidas Product Scraper")
    st.markdown("Search for products and explore trending items")
    
    # Initialize scraper
    scraper = AdidasScraper(headless=True)
    
    # Session state for products
    if 'products' not in st.session_state:
        st.session_state.products = []
    if 'product_details' not in st.session_state:
        st.session_state.product_details = None
    
    # Sidebar - Base URL
    st.sidebar.header("Configuration")
    scraper.base_url = st.sidebar.text_input(
        "Base URL",
        value="https://www.adidas.com/us",
        help="Enter the base URL for The website"
    )
    
    # Sidebar - Actions
    st.sidebar.header("Actions")
    action = st.sidebar.radio(
        "Select Action",
        ["Search Products", "Trending Products", "Product Details"]
    )
    
    # Main content based on selected action
    if action == "Search Products":
        st.header("Search  Products")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            search_query = st.text_input("Search Query", placeholder="e.g., Ultra Boost")
        
        with col2:
            category = st.text_input("Category (Optional)", placeholder="e.g., men")
        
        if st.button("Search", type="primary"):
            if search_query:
                with st.spinner(f"Searching for '{search_query}'..."):
                    st.session_state.products = scraper.search_products(search_query, category)
                    if not st.session_state.products:
                        st.error("No products found")
            else:
                st.warning("Please enter a search query")
    
    elif action == "Trending Products":
        st.header("Trending Products")
        
        if st.button("Get Trending Products", type="primary"):
            with st.spinner("Getting trending products..."):
                st.session_state.products = scraper.get_trending_products()
                if not st.session_state.products:
                    st.error("No trending products found")
    
    elif action == "Product Details":
        st.header("Get Product Details")
        
        product_url = st.text_input("Product URL", placeholder="e.g., https://www.adidas.com/us/ultraboost-shoes/FY9318.html")
        
        if st.button("Get Details", type="primary"):
            if product_url:
                with st.spinner("Getting product details..."):
                    st.session_state.product_details = scraper.get_product_details(product_url)
                    if not st.session_state.product_details:
                        st.error("Failed to get product details")
            else:
                st.warning("Please enter a product URL")
    
    # Display products if available
    if st.session_state.products:
        st.header(f"Found {len(st.session_state.products)} Products")
        
        # Display products in a grid
        cols = st.columns(3)
        
        for i, product in enumerate(st.session_state.products):
            col = cols[i % 3]
            
            with col:
                st.subheader(product.get('name', 'Unknown Product'))
                
                # Get and display image
                image_url = product.get('image_url', '')
                if image_url:
                    img = scraper.fetch_product_image(image_url)
                    if img:
                        st.image(img, width=250)
                    else:
                        st.info("Image not available")
                
                st.markdown(f"**Price:** {product.get('price', 'N/A')}")
                st.markdown(f"**Product ID:** {product.get('product_id', 'N/A')}")
                
                # Button to view product on Adidas website
                if product.get('url'):
                    st.markdown(f"[View on Adidas]({product.get('url')})")
                
                # Button to show details
                if st.button("Show Details", key=f"btn_details_{i}"):
                    with st.spinner("Getting product details..."):
                        product_details = scraper.get_product_details(product.get('url', ''))
                        if product_details:
                            st.session_state.product_details = product_details
                        else:
                            st.error("Failed to get product details")
                
                st.divider()
        
        # Export options
        st.header("Export Options")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Export to CSV"):
                # Convert to DataFrame
                df = pd.DataFrame(st.session_state.products)
                
                # Create download button
                st.download_button(
                    label="Download CSV",
                    data=df.to_csv(index=False).encode('utf-8'),
                    file_name="adidas_products.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("Export to JSON"):
                # Prepare JSON data
                json_data = json.dumps(st.session_state.products, indent=2)
                
                # Create download button
                st.download_button(
                    label="Download JSON",
                    data=json_data,
                    file_name="adidas_products.json",
                    mime="application/json"
                )
    
    # Display product details if available
    if st.session_state.product_details:
        st.header("Product Details")
        
        details = st.session_state.product_details
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            # Display first image
            if details['image_urls']:
                img = scraper.fetch_product_image(details['image_urls'][0])
                if img:
                    st.image(img, width=300)
        
        with col2:
            st.subheader(details['name'])
            st.markdown(f"**Price:** {details['price']}")
            st.markdown(f"**Product ID:** {details['product_id']}")
            st.markdown(f"**URL:** [{details['url']}]({details['url']})")
            st.markdown("**Description:**")
            st.markdown(details['description'])
        
        # Display all images in a grid
        if len(details['image_urls']) > 1:
            st.subheader("All Product Images")
            
            image_cols = st.columns(min(len(details['image_urls']), 4))
            
            for i, img_url in enumerate(details['image_urls']):
                col = image_cols[i % min(len(details['image_urls']), 4)]
                
                with col:
                    img = scraper.fetch_product_image(img_url)
                    if img:
                        st.image(img, width=200)
    
    # Close driver when app is done
    if st.sidebar.button("Close Browser"):
        scraper.close_driver()
        st.sidebar.success("Browser closed")


if __name__ == "__main__":
    main()
    
