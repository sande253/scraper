# fashion_scraper/items.py
import scrapy

class FashionItem(scrapy.Item):
    name = scrapy.Field()
    category = scrapy.Field()
    gender = scrapy.Field()
    price = scrapy.Field()
    image_url = scrapy.Field()
    image_path = scrapy.Field()