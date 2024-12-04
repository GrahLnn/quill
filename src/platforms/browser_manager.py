import json
from pathlib import Path
from typing import Dict, List, Optional

from DrissionPage import Chromium, ChromiumOptions
from DrissionPage._pages.mix_tab import MixTab
from fake_useragent import UserAgent

from .utils import read_netscape_cookies


class BrowserManager:
    """Manages multiple browser instances and their configurations"""

    def __init__(
        self,
        browser_path: Optional[str] = None,
        headless: bool = True,
        cookies_path: Optional[str] = r"config/cookies.txt",
    ):
        self.browser_path = browser_path
        self.headless = headless
        self.cookies_path = Path(cookies_path) if cookies_path else None
        self.browsers: Dict[str, Chromium] = {}  # 存储多个浏览器实例
        self.pages: Dict[str, MixTab] = {}  # 存储多个页面实例
        self.ua = UserAgent()
        self.assistive_cookies = []

    def create_browser(self, headless: Optional[bool] = None) -> Chromium:
        """Create a new browser instance with the specified configuration"""
        co = ChromiumOptions().auto_port()

        if self.browser_path:
            if "msedge.exe" in self.browser_path:
                raise ValueError("Microsoft Edge is not supported")
            co = co.set_browser_path(self.browser_path)

        if headless if headless is not None else self.headless:
            co = co.headless()

        co.mute(True)
        # co.set_argument("--disable-extensions")
        co.set_user_agent(self.ua.chrome)
        # 禁止所有弹出窗口
        co.set_pref("profile.default_content_settings.popups", "0")
        # 隐藏是否保存密码的提示
        co.set_pref("credentials_enable_service", False)

        # 设置浏览器语言为英文
        co.set_argument("--lang=en-US")
        co.set_pref("intl.accept_languages", "en-US")

        browser = Chromium(co)
        return browser

    def init_browser(
        self,
        instance_name: str = "default",
        headless: Optional[bool] = None,
        load_cookies: bool = True,
    ):
        """Initialize a new browser instance with the given name
        if no headless is provided, will use self.headless
        """
        if instance_name in self.browsers:
            raise ValueError(f"Browser instance '{instance_name}' already exists")

        browser = self.create_browser(headless)
        self.browsers[instance_name] = browser
        self.pages[instance_name] = browser.latest_tab

        if self.cookies_path and load_cookies:
            self.load_cookies(self.pages[instance_name])

        return self.browsers[instance_name], self.pages[instance_name]

    def get_browser(self, instance_name: str = "default") -> Optional[Chromium]:
        """Get a browser instance by name"""
        return self.browsers.get(instance_name)

    def get_page(self, instance_name: str = "default") -> Optional[Chromium]:
        """Get a page instance by name"""
        return self.pages.get(instance_name)

    def load_cookies(self, page: Chromium):
        if self.cookies_path:
            page.set.cookies(self._read_cookies())

    def _read_cookies(self, which_cookie="main"):
        """Load cookies from file, supporting both Netscape and JSON formats"""
        if not self.cookies_path:
            return []

        try:
            if self.cookies_path.suffix == ".json":
                return self._read_json_cookies()
            else:
                return read_netscape_cookies(self.cookies_path)
        except Exception:
            return []

    def _read_json_cookies(self) -> List[Dict]:
        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def close_browser(self, instance_name: str = "default"):
        """Close a specific browser instance"""
        if instance_name in self.browsers:
            self.browsers[instance_name].quit()
            del self.browsers[instance_name]
            del self.pages[instance_name]

    def close_all_browsers(self):
        """Close all browser instances"""
        for instance_name in list(self.browsers.keys()):
            self.close_browser(instance_name)
