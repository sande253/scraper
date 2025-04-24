import asyncio
import os
import pandas as pd
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urljoin
import time
import uuid

async def scrape_zara_data():
    # Configuration
    base_url = "https://www.zara.com/in/en/man-all-products-l7465.html?v1=2458839"  # Zara men's product page
    output_csv = "fashion_data.csv"
    image_folder = "images"
    max_items = 10  # Limit for demo; adjust as needed
    timeout = 60000  # Increased timeout to 60 seconds

    # Create image folder if it doesn't exist
    if not os.path.exists(image_folder):
        os.makedirs(image_folder)

    # Initialize data storage
    data = []

    async with async_playwright() as p:
        # Launch browser (headless=False for debugging, set to True for production)
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        try:
            # Navigate to the product listing page
            print(f"Navigating to {base_url}")
            await page.goto(base_url, wait_until="domcontentloaded")

            # Wait for network idle to ensure dynamic content loads
            await page.wait_for_load_state("networkidle", timeout=timeout)

            # Wait for product items to load (Zara's product grid selector)
            try:
                await page.wait_for_selector(".product-grid-product", timeout=timeout)
            except PlaywrightTimeoutError:
                print("Product grid not found. Dumping page content for debugging...")
                content = await page.content()
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(content)
                raise Exception("Failed to find product grid. Check debug_page.html for HTML structure.")

            # Scroll to load more items (handle lazy loading)
            for _ in range(5):  # Increased scrolls for Zara's lazy loading
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(3)  # Wait for lazy-loaded content
                print("Scrolled to load more products...")

            # Extract product items
            product_elements = await page.query_selector_all(".product-grid-product")
            print(f"Found {len(product_elements)} products")

            for i, product in enumerate(product_elements[:max_items]):
                try:
                    # Extract product details (Zara-specific selectors)
                    name_element = await product.query_selector(".product-grid-product-info__name h3")
                    name = await name_element.inner_text() if name_element else "Unknown"
                    name = name.strip()

                    # Category (infer from name or URL, Zara doesn't always have explicit tags)
                    category = "Unknown"
                    if "shirt" in name.lower():
                        category = "Shirts"
                    elif "pant" in name.lower() or "trouser" in name.lower():
                        category = "Pants"
                    elif "jacket" in name.lower():
                        category = "Jackets"

                    # Gender (inferred from URL or page context)
                    gender = "Men"  # Based on men's product page URL

                    # Price
                    price_element = await product.query_selector(".price__amount-current")
                    price = await price_element.inner_text() if price_element else "0.00"
                    price = price.replace("INR", "").replace(",", "").strip()

                    # Image URL
                    image_element = await product.query_selector("img.media-image__image")
                    image_url = await image_element.get_attribute("src") if image_element else ""
                    image_url = urljoin(base_url, image_url) if image_url else ""

                    # Download image
                    image_path = ""
                    if image_url:
                        try:
                            image_name = f"{uuid.uuid4()}.jpg"
                            image_path = os.path.join(image_folder, image_name)
                            response = requests.get(image_url, timeout=10)
                            if response.status_code == 200:
                                with open(image_path, "wb") as f:
                                    f.write(response.content)
                                print(f"Downloaded image: {image_name}")
                            else:
                                image_path = "Failed to download"
                        except Exception as e:
                            print(f"Error downloading image: {e}")
                            image_path = "Error"

                    # Store data
                    data.append({
                        "name": name,
                        "category": category,
                        "gender": gender,
                        "price": price,
                        "image_url": image_url,
                        "image_path": image_path
                    })

                    print(f"Scraped: {name} ({category}, {gender}, {price})")
                except Exception as e:
                    print(f"Error processing product {i+1}: {e}")
                
                # Rate limiting
                await asyncio.sleep(2)  # Increased delay for Zara's server

        except Exception as e:
            print(f"Error during scraping: {e}")
        finally:
            await browser.close()

    # Save to CSV
    if data:
        df = pd.DataFrame(data)
        df.to_csv(output_csv, index=False, encoding="utf-8")
        print(f"Data saved to {output_csv}")
    else:
        print("No data scraped. Check selectors or network issues.")

if __name__ == "__main__":
    asyncio.run(scrape_zara_data())