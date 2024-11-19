from src.platforms.twitter.scraper import TwitterScraper

scraper = TwitterScraper(
    browser_path=r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    headless=False,
)
scraper.locate("https://x.com/GrahLnn/likes", "1849521260843368945")
