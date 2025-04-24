import scrapy
import json
import uuid
import os
import requests
from urllib.parse import urljoin
from fashion_scraper.items import FashionItem
from scrapy_playwright.page import PageMethod

class AsosSpider(scrapy.Spider):
    name = "asos"
    allowed_domains = ["asos.com"]
    start_urls = ["https://www.asos.com/men/shirts/cat/?ctaref=hp|mw|prime|cat|shirts"]
    image_folder = "images"
    max_items = 10  # Limit for demo
    collected_items = 0

    custom_settings = {
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 120000,
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": False},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not os.path.exists(self.image_folder):
            os.makedirs(self.image_folder)

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_load_state", "networkidle"),
                        PageMethod("wait_for_function", "document.querySelectorAll('[data-auto-id=\"productTile\"], article, .product-card').length > 0", timeout=120000),
                    ],
                },
                callback=self.parse,
                errback=self.errback,
            )

    async def parse(self, response):
        page = response.meta.get("playwright_page")
        if not page:
            self.logger.error("No Playwright page available")
            return

        # CAPTCHA check
        captcha = await page.query_selector("text=/captcha|verify you are not a robot/i")
        if captcha:
            self.logger.warning("CAPTCHA detected. Saving screenshot...")
            await page.screenshot(path="captcha_screenshot.png")
            await page.close()
            raise scrapy.exceptions.CloseSpider("CAPTCHA encountered. Check captcha_screenshot.png.")

        # API interception
        api_data = []
        async def handle_response(response):
            if "api" in response.url.lower() and "product" in response.url.lower():
                try:
                    json_data = await response.json()
                    self.logger.info(f"Intercepted API response: {json_data}")
                    api_data.extend(json_data.get("products", []) or json_data.get("items", []))
                except Exception as e:
                    self.logger.error(f"Failed to parse API response: {e}")

        await page.on("response", handle_response)

        # Scroll to load products
        for _ in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)
            self.logger.info("Scrolled to load more products...")

        # Process API data
        for product in api_data:
            if self.collected_items >= self.max_items:
                break
            item = FashionItem()
            item["name"] = product.get("name", "Unknown")
            item["category"] = "Shirts" if "shirt" in item["name"].lower() else "Unknown"
            if "pant" in item["name"].lower() or "trouser" in item["name"].lower():
                item["category"] = "Pants"
            elif "jacket" in item["name"].lower():
                item["category"] = "Jackets"
            item["gender"] = "Men"
            item["price"] = str(product.get("price", {}).get("current", {}).get("value", 0.0))
            item["image_url"] = f"https:{product.get('imageUrl', '')}"
            item["image_path"] = self.download_image(item["image_url"])
            self.collected_items += 1
            yield item

        # DOM scraping fallback
        if self.collected_items < self.max_items:
            selector = response.css('[data-auto-id="productTile"], article, .product-card')
            self.logger.info(f"Found {len(selector)} products in DOM")
            for product in selector:
                if self.collected_items >= self.max_items:
                    break
                item = FashionItem()
                item["name"] = product.css('[data-auto-id="productTileDescription"], .product-card__title::text').get(default="Unknown").strip()
                item["category"] = "Shirts"
                if "pant" in item["name"].lower() or "trouser" in item["name"].lower():
                    item["category"] = "Pants"
                elif "jacket" in item["name"].lower():
                    item["category"] = "Jackets"
                item["gender"] = "Men"
                item["price"] = product.css('[data-auto-id="productTilePrice"], .product-card__price::text').get(default="0.00").replace("£", "").replace("$", "").replace(",", "").strip()
                image_url = product.css("img::attr(data-src), img::attr(src)").get()
                item["image_url"] = urljoin(response.url, image_url) if image_url else ""
                item["image_path"] = self.download_image(item["image_url"])
                self.collected_items += 1
                yield item

        # Debug output
        try:
            html_content = await page.evaluate("document.documentElement.outerHTML")
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            self.logger.info("Page content dumped to debug_page.html")
        except Exception as e:
            self.logger.error(f"Failed to dump HTML: {e}")
            await page.screenshot(path="debug_screenshot.png")
            self.logger.info("Screenshot saved to debug_screenshot.png")

        await page.close()

    def download_image(self, image_url):
        if not image_url:
            return "No image URL"
        try:
            image_name = f"{uuid.uuid4()}.jpg"
            image_path = os.path.join(self.image_folder, image_name)
            response = requests.get(image_url, timeout=10)
            if response.status_code == 200:
                with open(image_path, "wb") as f:
                    f.write(response.content)
                self.logger.info(f"Downloaded image: {image_name}")
                return image_path
            return "Failed to download"
        except Exception as e:
            self.logger.error(f"Error downloading image: {e}")
            return "Error"

    async def errback(self, failure):
        self.logger.error(f"Request failed: {failure}")
        page = failure.request.meta.get("playwright_page")
        if page:
            await page.screenshot(path="error_screenshot.png")
            self.logger.info("Screenshot saved to error_screenshot.png")
            await page.close()