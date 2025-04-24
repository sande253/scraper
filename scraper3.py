import os
import re
import json
import time
import argparse
import requests
import pandas as pd
from urllib.parse import urljoin, quote_plus
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from tqdm import tqdm
import threading


class AdidasScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.base_url = input("Enter the base URL for search (e.g., https://www.adidas.com/us): ").strip()
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
        
        print(f"Searching for '{query}' at {url}")
        
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
        print(f"Getting trending products from {url}")
        
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
        
        print(f"Getting details for product at {product_url}")
        
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
        print("Scrolling to load all products...")
        
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
            print(f"Found {len(json_products)} products from JSON data")
            products.extend(json_products)
        
        # Method 2: Try to extract products from HTML structure
        html_products = self._extract_from_html(soup)
        if html_products:
            print(f"Found {len(html_products)} products from HTML")
            products.extend(html_products)
        
        # Method 3: Try to extract products using JavaScript
        js_products = self._extract_with_js()
        if js_products:
            print(f"Found {len(js_products)} products from JavaScript")
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
        
        print(f"Found {len(unique_products)} unique products")
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
                    print(f"Error extracting JSON data: {e}")
        
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
                print(f"Error extracting product from HTML: {e}")
        
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
            print(f"Error extracting products with JavaScript: {e}")
            return []
    
    def download_images(self, products, max_images=5):
        """Download product images"""
        print(f"Downloading product images...")
        images_dir = os.path.join(self.output_dir, "images")
        
        # Create progress bar
        progress = tqdm(total=min(len(products), max_images), desc="Downloading Images")
        
        downloaded_count = 0
        for product in products:
            # Skip if we've reached the maximum number of images
            if downloaded_count >= max_images:
                break
            
            # Get image URL
            image_url = product.get('image_url', '')
            
            # If no image URL in the product data, try to get from product details
            if not image_url and 'url' in product and product['url']:
                try:
                    details = self.get_product_details(product['url'])
                    if details['image_urls']:
                        image_url = details['image_urls'][0]
                except:
                    pass
            
            # Skip if no image URL
            if not image_url:
                continue
            
            # Create filename
            product_id = product.get('product_id', '')
            name_slug = re.sub(r'[^\w\-]', '_', product.get('name', 'product'))[:30]
            
            if product_id:
                filename = f"{product_id}_{name_slug}.jpg"
            else:
                filename = f"{name_slug}_{downloaded_count}.jpg"
            
            file_path = os.path.join(images_dir, filename)
            
            # Download image
            try:
                response = requests.get(image_url, stream=True, timeout=10)
                if response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                    
                    # Add image path to product
                    product['image_path'] = file_path
                    downloaded_count += 1
                    progress.update(1)
            except Exception as e:
                print(f"Error downloading image {image_url}: {e}")
        
        progress.close()
        print(f"Downloaded {downloaded_count} images")
    
    def export_to_csv(self, products, filename="adidas_products.csv"):
        """Export products to CSV file"""
        if not products:
            print("No products to export")
            return
        
        file_path = os.path.join(self.output_dir, filename)
        
        # Convert to DataFrame
        df = pd.DataFrame(products)
        
        # Save to CSV
        df.to_csv(file_path, index=False)
        print(f"Exported {len(products)} products to {file_path}")
    
    def export_to_html(self, products, filename="adidas_products.html"):
        """Export products to HTML file with images"""
        if not products:
            print("No products to export")
            return
        
        file_path = os.path.join(self.output_dir, filename)
        
        # Create HTML content
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Adidas Products</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                h1 { text-align: center; color: #333; }
                .products { display: flex; flex-wrap: wrap; justify-content: center; }
                .product { 
                    border: 1px solid #ddd; 
                    margin: 10px; 
                    padding: 15px; 
                    width: 280px;
                    border-radius: 8px;
                    transition: transform 0.3s;
                }
                .product:hover { transform: scale(1.03); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
                .product img { width: 250px; height: 250px; object-fit: contain; display: block; margin: 0 auto; }
                .product h2 { font-size: 16px; margin: 10px 0; height: 48px; overflow: hidden; }
                .product .price { font-weight: bold; color: #333; font-size: 18px; }
                .product a { display: block; text-align: center; background: #000; color: white; text-decoration: none; padding: 8px; margin-top: 10px; border-radius: 4px; }
                .product a:hover { background: #333; }
            </style>
        </head>
        <body>
            <h1>Adidas Products</h1>
            <div class="products">
        """
        
        # Add each product
        for product in products:
            name = product.get('name', 'Unknown Product')
            price = product.get('price', 'Price not available')
            url = product.get('url', '#')
            
            # Get image path or URL
            image_src = ''
            if 'image_path' in product:
                # Use relative path for images
                image_path = product['image_path']
                if os.path.exists(image_path):
                    rel_path = os.path.relpath(image_path, os.path.dirname(file_path))
                    image_src = rel_path.replace('\\', '/')
            
            if not image_src and 'image_url' in product:
                image_src = product['image_url']
            
            # If no image, use placeholder
            if not image_src:
                image_src = "https://via.placeholder.com/250"
            
            html_content += f"""
            <div class="product">
                <img src="{image_src}" alt="{name}">
                <h2>{name}</h2>
                <div class="price">{price}</div>
                <a href="{url}" target="_blank">View Product</a>
            </div>
            """
        
        html_content += """
            </div>
        </body>
        </html>
        """
        
        # Write HTML file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Exported products to HTML: {file_path}")


class AdidasAgent:
    def __init__(self):
        self.scraper = AdidasScraper(headless=True)
        self.commands = {
            'search': self.search_command,
            'trending': self.trending_command,
            'details': self.details_command,
            'help': self.help_command,
            'exit': self.exit_command
        }
    
    def start_interactive(self):
        """Start interactive mode"""
        print("\n" + "="*50)
        print("Welcome to the Adidas Product Search Agent!")
        print("="*50)
        print("Type 'help' to see available commands")
        print("="*50 + "\n")
        
        running = True
        while running:
            try:
                command = input("\nEnter command: ").strip().lower()
                
                if not command:
                    continue
                
                # Split command and arguments
                parts = command.split(' ', 1)
                cmd = parts[0]
                args = parts[1] if len(parts) > 1 else ""
                
                # Execute command if it exists
                if cmd in self.commands:
                    running = self.commands[cmd](args)
                else:
                    print(f"Unknown command: {cmd}")
                    print("Type 'help' to see available commands")
            except KeyboardInterrupt:
                print("\nExiting...")
                running = False
            except Exception as e:
                print(f"Error: {e}")
        
        # Clean up
        self.scraper.close_driver()
        print("\nThanks for using the Adidas Product Search Agent!")
    
    def search_command(self, args):
        """Handle search command"""
        if not args:
            print("Usage: search <query> [--category <category>]")
            return True
        
        # Parse category if specified
        category = None
        if "--category" in args:
            query_parts = args.split("--category")
            query = query_parts[0].strip()
            category = query_parts[1].strip()
        else:
            query = args
        
        print(f"Searching for '{query}'{' in category ' + category if category else ''}...")
        
        # Perform search
        products = self.scraper.search_products(query, category)
        
        if products:
            # Download images
            self.scraper.download_images(products)
            
            # Export results
            self.scraper.export_to_csv(products)
            self.scraper.export_to_html(products)
            
            # Display results summary
            self._display_results_summary(products)
        else:
            print("No products found")
        
        return True
    
    def trending_command(self, args):
        """Handle trending command"""
        print("Getting trending products...")
        
        # Get trending products
        products = self.scraper.get_trending_products()
        
        if products:
            # Download images
            self.scraper.download_images(products)
            
            # Export results
            self.scraper.export_to_csv(products, "adidas_trending.csv")
            self.scraper.export_to_html(products, "adidas_trending.html")
            
            # Display results summary
            self._display_results_summary(products)
        else:
            print("No trending products found")
        
        return True
    
    def details_command(self, args):
        """Handle details command"""
        if not args:
            print("Usage: details <product_url>")
            return True
        
        print(f"Getting details for product: {args}")
        
        # Get product details
        details = self.scraper.get_product_details(args)
        
        if details:
            # Display product details
            print("\nProduct Details:")
            print(f"Name: {details['name']}")
            print(f"Price: {details['price']}")
            print(f"ID: {details['product_id']}")
            print(f"Description: {details['description'][:100]}..." if len(details['description']) > 100 else details['description'])
            print(f"URL: {details['url']}")
            print(f"Images: {len(details['image_urls'])} found")
            
            # Extract additional details like gender and type (e.g., shirt, pants)
            gender = details.get('gender', 'Not specified')
            product_type = details.get('type', 'Not specified')
            print(f"Gender: {gender}")
            print(f"Type: {product_type}")
            
            # Download images
            if details['image_urls']:
                print("Downloading images...")
                for i, img_url in enumerate(details['image_urls'][:5]):
                    try:
                        filename = f"{details['product_id']}_{i}.jpg" if details['product_id'] else f"product_{i}.jpg"
                        file_path = os.path.join(self.scraper.output_dir, "images", filename)
                        
                        response = requests.get(img_url, stream=True, timeout=10)
                        if response.status_code == 200:
                            with open(file_path, 'wb') as f:
                                for chunk in response.iter_content(1024):
                                    f.write(chunk)
                            print(f"Downloaded image to {file_path}")
                    except Exception as e:
                        print(f"Error downloading image: {e}")
            
            # Save details to file
            details_file = os.path.join(self.scraper.output_dir, "product_details.json")
            with open(details_file, 'w', encoding='utf-8') as f:
                json.dump(details, f, indent=2)
            print(f"Details saved to {details_file}")
        else:
            print("Failed to get product details")
        
        return True
    
    def help_command(self, args):
        """Display help information"""
        print("\nAvailable Commands:")
        print("  search <query> [--category <category>] - Search for products")
        print("  trending - Get trending products")
        print("  details <product_url> - Get detailed information for a specific product")
        print("  help - Display this help message")
        print("  exit - Exit the program")
        print("\nExamples:")
        print("  search adidas superstar")
        print("  search running shoes --category men")
        print("  trending")
        print("  details https://www.adidas.com/us/superstar-shoes/EG4958.html")
        return True
    
    def exit_command(self, args):
        """Exit the program"""
        return False
    
    def _display_results_summary(self, products):
        """Display a summary of the search results"""
        if not products:
            return
        
        print(f"\nFound {len(products)} products:")
        
        # Display top 5 products
        for i, product in enumerate(products[:5], 1):
            name = product.get('name', 'Unknown Product')
            price = product.get('price', 'Price not available')
            url = product.get('url', 'URL not available')
            
            print(f"{i}. {name} - {price}")
            print(f"   URL: {url}")
        
        if len(products) > 5:
            print(f"...and {len(products) - 5} more")
        
        print(f"\nResults have been saved to the '{self.scraper.output_dir}' directory")
        print(f"- CSV: {os.path.join(self.scraper.output_dir, 'adidas_products.csv')}")
        print(f"- HTML: {os.path.join(self.scraper.output_dir, 'adidas_products.html')}")
        print(f"- Images: {os.path.join(self.scraper.output_dir, 'images')}")


def main():
    parser = argparse.ArgumentParser(description='Adidas Product Search Agent')
    parser.add_argument('--search', help='Search for products')
    parser.add_argument('--category', help='Product category for search')
    parser.add_argument('--trending', action='store_true', help='Get trending products')
    parser.add_argument('--details', help='Get details for a specific product URL')
    parser.add_argument('--interactive', action='store_true', help='Start interactive mode')
    
    args = parser.parse_args()
    
    agent = AdidasAgent()
    
    # Check if any arguments provided
    if args.search or args.trending or args.details or args.interactive:
        # Process command line arguments
        if args.search:
            query = args.search
            category = args.category
            print(f"Searching for '{query}'{' in category ' + category if category else ''}...")
            products = agent.scraper.search_products(query, category)
            
            if products:
                agent.scraper.download_images(products)
                agent.scraper.export_to_csv(products)
                agent.scraper.export_to_html(products)
                agent._display_results_summary(products)
        
        elif args.trending:
            print("Getting trending products...")
            products = agent.scraper.get_trending_products()
            
            if products:
                agent.scraper.download_images(products)
                agent.scraper.export_to_csv(products, "adidas_trending.csv")
                agent.scraper.export_to_html(products, "adidas_trending.html")
                agent._display_results_summary(products)
            else:
                print("No trending products found")
        
        elif args.details:
            print(f"Getting details for product: {args.details}")
            details = agent.scraper.get_product_details(args.details)
            
            if details:
                print("\nProduct Details:")
                print(f"Name: {details['name']}")
                print(f"Price: {details['price']}")
                print(f"ID: {details['product_id']}")
                print(f"Description: {details['description'][:100]}..." if len(details['description']) > 100 else details['description'])
                print(f"URL: {details['url']}")
                print(f"Images: {len(details['image_urls'])} found")
                
                # Save details to file
                details_file = os.path.join(agent.scraper.output_dir, "product_details.json")
                with open(details_file, 'w', encoding='utf-8') as f:
                    json.dump(details, f, indent=2)
                print(f"Details saved to {details_file}")
            else:
                print("Failed to get product details")
        
        elif args.interactive:
            agent.start_interactive()
    else:
        # If no arguments provided, show help
        parser.print_help()


if __name__ == "__main__":
    
    main()
    
    
