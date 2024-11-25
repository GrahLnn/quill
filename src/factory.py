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
            **kwargs: Additional keyword arguments to pass to the scraper constructor

        Returns:
            Optional[BaseScraper]: A scraper instance if a matching domain is found,
                                 None otherwise

        Example:
            >>> scraper = ScraperFactory.get_scraper("https://twitter.com/user")
            >>> if scraper:
            >>>     content = scraper.scrape()
        """
        for domain, scraper_class in cls._scrapers.items():
            if domain in url:
                return scraper_class(**kwargs)
        return None
