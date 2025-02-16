from typing import List, Optional

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

from src.factory import ScraperFactory
from src.service.utils import split_keys


class Settings(BaseSettings):
    proxies: Optional[List[str]] = Field(default=None, validate_default=True)
    browser_path: Optional[str] = Field(default=None)
    endpoint: Optional[str] = Field(default=None)
    headless: bool = True
    target_url: str = "https://x.com/GrahLnn/likes"

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        extra_sources=[],
    )

    @field_validator("proxies", mode="before")
    def validate_proxies(cls, v):
        return split_keys(v)


def main():
    # 加载环境变量配置
    settings = Settings()

    scraper = ScraperFactory.get_scraper(
        settings.target_url,
        browser_path=settings.browser_path,
        headless=settings.headless,
        proxies=settings.proxies,
        endpoint=settings.endpoint,
    )
    results = scraper.scrape(settings.target_url)


if __name__ == "__main__":
    main()
