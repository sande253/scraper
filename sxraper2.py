from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
import time

# Setup headless browser
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(options=options)

# Start at Zara Woman clothing section
start_url = "https://www.zara.com/us/en/woman-new-in-l1180.html"
driver.get(start_url)
time.sleep(5)  # wait for JS to load

# Scroll to load all products
SCROLL_PAUSE_TIME = 2
last_height = driver.execute_script("return document.body.scrollHeight")
for _ in range(5):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(SCROLL_PAUSE_TIME)
    new_height = driver.execute_script("return document.body.scrollHeight")
    if new_height == last_height:
        break
    last_height = new_height

soup = BeautifulSoup(driver.page_source, "html.parser")

# Find product containers
products = []
items = soup.select("a.product-link")

for item in items:
    try:
        link = "https://www.zara.com/us/en/man-new-in-l711.html" + item.get("href")
        title = item.select_one("div.product-name").text.strip()
        price = item.select_one("span.price-current__amount").text.strip()
        image_tag = item.select_one("img")
        image = image_tag.get("src") or image_tag.get("data-src") or ""
        # Optionally filter categories (if needed)
        if any(x in title.lower() for x in ["dress", "shirt", "pants", "jacket", "coat", "jeans", "blazer", "top", "skirt"]):
            category = "Woman"
            products.append({
                "Title": title,
                "Price": price,
                "Link": link,
                "Image": image,
                "Category": category
            })
    except Exception as e:
        print(f"Error parsing item: {e}")
driver.quit()
# Save to DataFrame and CSV
df = pd.DataFrame(products)
df.to_csv("zara_clothes.csv", index=False)
print("✅ Scraped and saved to zara_clothes.csv")
print(df.head())
