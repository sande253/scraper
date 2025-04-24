import asyncio
import os
import pandas as pd
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urljoin
import time
import uuid
import random

async def scrape_asos_data():
    # Configuration
    base_url = "https://www.zara.com/in/en/man-all-products-l7465.html?v1=2458839"  # ASOS men's shirts
    output_csv = "fashion_data.csv"
    image_folder = "images"
    max_items = 10  # Limit for demo
    timeout = 120000  # 120 seconds timeout

    # Create image folder
    if not os.path.exists(image_folder):
        os.makedirs(image_folder)

    # Initialize data storage
    data = []

    async with async_playwright() as p:
        # Launch browser (headless=False for debugging)
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Random user-agent to avoid bot detection
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:117.0) Gecko/20100101 Firefox/117.0"
        ]
        await page.set_extra_http_headers({
            "User-Agent": random.choice(user_agents),
            "Accept-Language": "en-US,en;q=0.9"
        })

        # Set viewport to mimic real user
        await page.set_viewport_size({"width": 1280, "height": 720})

        # Intercept network requests for API data
        async def handle_response(response):
            if "api" in response.url.lower() and "product" in response.url.lower():
                try:
                    json_data = await response.json()
                    print(f"Intercepted API response: {json_data}")
                    # Parse API data for products
                    products = json_data.get("products", [])
                    for product in products[:max_items - len(data)]:
                        data.append({
                            "name": product.get("name", "Unknown"),
                            "category": "Shirts" if "shirt" in product.get("name", "").lower() else "Unknown",
                            "gender": "Men",
                            "price": str(product.get("price", {}).get("current", {}).get("value", 0.0)),
                            "image_url": f"https:{product.get('imageUrl', '')}",
                            "image_path": ""
                        })
                except Exception as e:
                    print(f"Failed to parse API response: {e}")

        # Attach response handler
        page.on("response", handle_response)

        try:
            # Navigate to the product listing page
            print(f"Navigating to {base_url}")
            await page.goto(base_url, wait_until="domcontentloaded")

            # Check for CAPTCHA or error pages
            captcha = await page.query_selector("text=/captcha|verify you are not a robot/i")
            if captcha:
                print("CAPTCHA detected. Manual intervention required.")
                await page.screenshot(path="captcha_screenshot.png")
                raise Exception("CAPTCHA encountered. Check captcha_screenshot.png.")

            # Wait for network idle
            await page.wait_for_load_state("networkidle", timeout=timeout)

            # Wait for products to render (try multiple selectors)
            await page.wait_for_function(
                "document.querySelectorAll('article, [data-auto-id=\"productTile\"], .product-card').length > 0",
                timeout=timeout
            )
            print("Product grid detected via JS")

            # Scroll to load more items
            for _ in range(5):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(3)
                print("Scrolled to load more products...")

            # Extract product items (DOM fallback)
            product_elements = await page.query_selector_all('article, [data-auto-id="productTile"], .product-card')
            print(f"Found {len(product_elements)} products in DOM")

            for i, product in enumerate(product_elements[:max_items - len(data)]):
                try:
                    # Extract product details
                    name_element = await product.query_selector('[data-auto-id="productTileDescription"], .product-card__title')
                    name = await name_element.inner_text() if name_element else "Unknown"
                    name = name.strip()

                    # Category
                    category = "Shirts"
                    if "pant" in name.lower() or "trouser" in name.lower():
                        category = "Pants"
                    elif "jacket" in name.lower():
                        category = "Jackets"

                    # Gender
                    gender = "Men"

                    # Price
                    price_element = await product.query_selector('[data-auto-id="productTilePrice"], .product-card__price')
                    price = await price_element.inner_text() if price_element else "0.00"
                    price = price.replace("£", "").replace("$", "").replace(",", "").strip()

                    # Image URL
                    image_element = await product.query_selector("img")
                    image_url = None
                    if image_element:
                        image_url = await image_element.get_attribute("data-src") or await image_element.get_attribute("src")
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

                    # Store data (only if not already added via API)
                    if not any(d["name"] == name for d in data):
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
                
                # Random delay
                await asyncio.sleep(random.uniform(1.5, 3))

        except PlaywrightTimeoutError:
            print("Timeout waiting for products. Attempting to dump page content...")
            try:
                # Retry HTML dump after delay
                await asyncio.sleep(5)
                html_content = await page.evaluate("document.documentElement.outerHTML")
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                print("Page content dumped to debug_page.html")
            except Exception as e:
                print(f"Failed to dump HTML: {e}")
                # Take screenshot as fallback
                await page.screenshot(path="debug_screenshot.png")
                print("Screenshot saved to debug_screenshot.png")
            raise Exception("Timeout occurred. Check debug_page.html or debug_screenshot.png.")
        except Exception as e:
            print(f"Error during scraping: {e}")
            await page.screenshot(path="error_screenshot.png")
            print("Screenshot saved to error_screenshot.png")
        finally:
            await browser.close()

    # Download images for API-scraped data
    for item in data:
        if item["image_path"] == "" and item["image_url"]:
            try:
                image_name = f"{uuid.uuid4()}.jpg"
                image_path = os.path.join(image_folder, image_name)
                response = requests.get(item["image_url"], timeout=10)
                if response.status_code == 200:
                    with open(image_path, "wb") as f:
                        f.write(response.content)
                    item["image_path"] = image_path
                    print(f"Downloaded API image: {image_name}")
                else:
                    item["image_path"] = "Failed to download"
            except Exception as e:
                print(f"Error downloading API image: {e}")
                item["image_path"] = "Error"

    # Save to CSV
    if data:
        df = pd.DataFrame(data)
        df.to_csv(output_csv, index=False, encoding="utf-8")
        print(f"Data saved to {output_csv}")
    else:
        print("No data scraped. Check selectors, CAPTCHA, or network issues.")

if __name__ == "__main__":
    asyncio.run(scrape_asos_data())