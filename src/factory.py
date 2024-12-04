from typing import Optional

from .platforms.base import BaseScraper
from .platforms.twitter.scraper import TwitterScraper


class ScraperFactory:
    _scrapers = {
        "twitter.com": TwitterScraper,
        "x.com": TwitterScraper,
    }

    @classmethod
    def get_scraper(cls, url: str, **kwargs) -> Optional[BaseScraper]:
        """Get the appropriate scraper instance based on the URL.

        Args:
            url (str): The target URL to be scraped
            browser_path (str, optional): The path to the browser executable, default is None, and will automatically detect Chrome.
            headless (bool, optional): Whether to run the browser in headless mode
            proxies (list, optional): A list of proxy servers, default is an empty list
            cookies_path (str, optional): The path to the cookies file, default is "config/cookies.txt"
            save_path (str, optional): The path to save the scraped data, default is "output"

        Returns:
            Optional[BaseScraper]: A scraper instance if a matching domain is found,
                                 None otherwise

        Example:
        ```python
            scraper = ScraperFactory.get_scraper("https://twitter.com/user")
            if scraper:
                content = scraper.scrape()
        ```
        """
        for domain, scraper_class in cls._scrapers.items():
            if domain in url:
                return scraper_class(**kwargs)
        return None
