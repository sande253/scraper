import os
import re
import json
import time
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urljoin
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
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )

        # ✅ Correct path for Hugging Face Spaces
        options.binary_location = "/usr/bin/chromium"
        options.add_experimental_option("excludeSwitches", ["enable-logging"])

        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    def close_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def get_trending_products(self):
        if not self.driver:
            self.driver = self.init_driver()

        url = f"{self.base_url}/trending"
        st.info(f"Getting trending products from {url}")

        self.driver.get(url)
        time.sleep(3)

        return self._extract_products()

    def _extract_products(self):
        products = []
        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        for item in soup.select("div[data-auto-id='product-card']"):
            try:
                name = item.select_one("[data-auto-id='product-card-title']").text.strip()
                price = item.select_one("[data-auto-id='product-price']").text.strip()
                url = item.find("a")["href"]
                if not url.startswith("http"):
                    url = urljoin(self.base_url, url)
                img = item.select_one("img")
                img_url = img["src"] if "src" in img.attrs else img.get("data-src", "")
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                product_id_match = re.search(r'/([A-Z0-9]{6})\.html', url)
                product_id = product_id_match.group(1) if product_id_match else ""

                products.append({
                    "name": name,
                    "price": price,
                    "url": url,
                    "image_url": img_url,
                    "product_id": product_id
                })
            except Exception as e:
                st.warning(f"Error reading product: {e}")

        return products

    def fetch_product_image(self, image_url):
        try:
            if not image_url:
                return None
            response = requests.get(image_url, stream=True, timeout=10)
            return Image.open(BytesIO(response.content)) if response.status_code == 200 else None
        except Exception as e:
            st.warning(f"Image error: {e}")
            return None


def main():
    st.set_page_config(page_title="Adidas Scraper 👟", layout="wide")
    st.title("Adidas Product Scraper")

    scraper = AdidasScraper(headless=True)

    if "products" not in st.session_state:
        st.session_state.products = []

    st.sidebar.header("Configuration")
    scraper.base_url = st.sidebar.text_input("Base URL", "https://www.adidas.com/us")

    st.header("Trending Adidas Products")
    if st.button("Get Trending Products"):
        with st.spinner("Fetching trending products..."):
            st.session_state.products = scraper.get_trending_products()
            if not st.session_state.products:
                st.error("No trending products found")

    if st.session_state.products:
        st.subheader(f"Found {len(st.session_state.products)} Products")
        cols = st.columns(3)
        for i, product in enumerate(st.session_state.products):
            with cols[i % 3]:
                st.markdown(f"### {product['name']}")
                img = scraper.fetch_product_image(product["image_url"])
                if img:
                    st.image(img, width=250)
                st.markdown(f"**Price:** {product['price']}")
                st.markdown(f"**Product ID:** {product['product_id']}")
                st.markdown(f"[View on Adidas]({product['url']})", unsafe_allow_html=True)
                st.divider()

    if st.sidebar.button("Close Browser"):
        scraper.close_driver()
        st.sidebar.success("Browser closed")


if __name__ == "__main__":
    main()
