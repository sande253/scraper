# fashion_scraper/settings.py
import random

BOT_NAME = "fashion_scraper"
SPIDER_MODULES = ["fashion_scraper.spiders"]
NEWSPIDER_MODULE = "fashion_scraper.spiders"

# Anti-bot settings
USER_AGENT_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:117.0) Gecko/20100101 Firefox/117.0",
]
USER_AGENT = random.choice(USER_AGENT_LIST)
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 90,
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": 110,
    "scrapy_playwright.middleware.PlaywrightMiddleware": 800,
}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 120000
PLAYWRIGHTstruk = False  # Set to True for production
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": False}  # Visible for debugging
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]

# Proxy support (optional, configure with your proxy service)
# HTTP_PROXY = "http://your-proxy:port"

# Output to CSV
FEEDS = {
    "fashion_data.csv": {
        "format": "csv",
        "encoding": "utf8",
        "store_empty": False,
        "item_export_kwargs": {
            "export_empty_fields": True,
        },
    },
}

# Crawling settings
ROBOTSTXT_OBEY = False  # Check legality
CONCURRENT_REQUESTS = 16
DOWNLOAD_DELAY = random.uniform(1.5, 3)