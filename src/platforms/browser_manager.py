from pathlib import Path
from typing import Optional
import json
from typing import Dict, List


from DrissionPage import Chromium, ChromiumOptions
from fake_useragent import UserAgent


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
        self.pages: Dict[str, Chromium] = {}  # 存储多个页面实例
        self.ua = UserAgent()

    def create_browser(self, headless: Optional[bool] = None) -> Chromium:
        """Create a new browser instance with the specified configuration"""
        co = ChromiumOptions().auto_port()

        if self.browser_path:
            if "msedge.exe" in self.browser_path:
                raise ValueError("Microsoft Edge is not supported")
            co = co.set_browser_path(self.browser_path)

        if headless if headless is not None else self.headless:
            co = co.headless()

            # 优化内存使用
            co.set_argument("--disable-features=site-per-process")
            co.set_argument("--disable-features=TranslateUI")
            co.set_argument("--disable-features=IsolateOrigins")
            co.set_argument("--disable-site-isolation-trials")

            # 限制JavaScript内存使用
            co.set_pref("webkit.webprefs.javascript_enabled", True)
            co.set_pref("webkit.webprefs.dom_paste_enabled", False)

        co.no_imgs(True).mute(True)
        co.set_argument("--disable-extensions")
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
        """Initialize a new browser instance with the given name"""
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

    def _read_cookies(self):
        """Load cookies from file, supporting both Netscape and JSON formats"""
        if not self.cookies_path:
            return []

        try:
            if self.cookies_path.suffix == ".json":
                return self._read_json_cookies()
            else:
                return self._read_netscape_cookies()
        except Exception as e:
            return []

    def _read_json_cookies(self) -> List[Dict]:
        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return []

    def _read_netscape_cookies(self) -> List[Dict]:
        cookies = []
        with open(self.cookies_path, "r", encoding="utf-8") as f:
            for line in f:
                # 跳过注释和空行
                if line.strip() and not line.startswith("#"):
                    fields = line.strip().split("\t")
                    if len(fields) >= 7:
                        cookie = {
                            "domain": fields[0],
                            "name": fields[5],
                            "value": fields[6],
                            "path": fields[2],
                            "expires": float(fields[4]) if fields[4].isdigit() else 0,
                            "secure": "TRUE" in fields[3],
                            "httpOnly": False,
                            "sameSite": "Lax",
                        }
                        cookies.append(cookie)
        return cookies

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
