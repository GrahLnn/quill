from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from src.factory import ScraperFactory


def split_proxy_string(v: Optional[str]) -> Optional[List[str]]:
    if v is None:
        return None
    return v.split(",")


class Settings(BaseSettings):
    proxies: Optional[List[str]] = Field(default=None, validate_default=True)
    browser_path: Optional[str] = Field(default=None)
    headless: bool = True
    target_url: str = "https://x.com/GrahLnn/likes"

    @field_validator("proxies", mode="before")
    def validate_proxies(cls, v):
        return split_proxy_string(v)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


def main():
    # 加载环境变量配置
    settings = Settings()

    scraper = ScraperFactory.get_scraper(
        settings.target_url,
        browser_path=settings.browser_path,
        headless=settings.headless,
        proxies=settings.proxies,
    )
    results = scraper.scrape(settings.target_url)


if __name__ == "__main__":
    main()
