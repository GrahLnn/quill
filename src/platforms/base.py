import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from DrissionPage import Chromium, ChromiumOptions
from tqdm import tqdm

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Generic type for data models
P = TypeVar("P")  # Generic type for parsers


@dataclass
class BaseContent:
    """Base content model for storing scraped data"""

    id: str  # Unique identifier
    url: str  # Source URL
    platform: str  # Platform identifier

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class BaseScraper(ABC, Generic[T, P]):
    """Base scraper class providing core web scraping functionality

    Generic Types:
        T: Content type to be scraped
        P: Parser type to be used
    """

    def __init__(
        self,
        browser_path: Optional[str] = None,  # Path to browser executable
        headless: bool = True,  # Run browser in headless mode
        cookies_path: Optional[str] = r"config/cookies.txt",  # Path to cookies file
        save_path: Optional[Path] = None,  # Path to save scraped data
    ):
        self.browser_path = browser_path
        self.headless = headless
        self.cookies_path = Path(cookies_path)
        self.save_path = save_path or Path("data")
        self.parser: Optional[P] = None
        self.browser: Chromium = None
        self.page: Optional[Chromium] = None
        self._init_scraper()

    def _init_scraper(self):
        self.browser = self.create_browser()
        self.page = self.browser.latest_tab

        if self.cookies_path:
            self.load_cookies(self.page)

    def create_browser(self):
        co = ChromiumOptions().auto_port()
        if self.browser_path:
            co = co.set_browser_path(self.browser_path)
        if self.headless:
            co = co.headless()
            co.set_argument("--no-sandbox")  # 禁用沙箱
            co.no_imgs(True)  # 禁止加载图片
            co.set_argument("--disable-extensions")  # 禁用扩展

            # 优化内存使用
            co.set_argument("--disable-features=site-per-process")
            co.set_argument("--disable-features=TranslateUI")
            co.set_argument("--disable-features=IsolateOrigins")
            co.set_argument("--disable-site-isolation-trials")

            # 限制JavaScript内存使用
            co.set_pref("webkit.webprefs.javascript_enabled", True)
            co.set_pref("webkit.webprefs.dom_paste_enabled", False)

        # 设置浏览器语言为英文
        co.set_argument("--lang=en-US")
        co.set_pref("intl.accept_languages", "en-US")

        return Chromium(co)

    def create_browser_head(self):
        co = ChromiumOptions().auto_port()
        if self.browser_path:
            co = co.set_browser_path(self.browser_path)

        # 设置浏览器语言为英文
        co.set_argument("--lang=en-US")
        co.set_pref("intl.accept_languages", "en-US")

        return Chromium(co)

    def load_cookies(self, page: Chromium):
        if self.cookies_path:
            page.set.cookies(self._load_cookies())

    @abstractmethod
    def scrape(self, url: str) -> List[T]:
        pass

    def close(self):
        self.browser.quit()

    def _load_cookies(self) -> List[Dict]:
        """Load cookies from file, supporting both Netscape and JSON formats"""
        if not self.cookies_path:
            logger.warning("No cookies path specified")
            return []

        try:
            if self.cookies_path.suffix == ".json":
                return self._load_json_cookies()
            else:
                return self._load_netscape_cookies()
        except Exception as e:
            logger.error(f"Failed to load cookies from {self.cookies_path}: {e}")
            return []

    def _load_netscape_cookies(self) -> List[Dict]:
        cookies = []
        try:
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
                                "expires": float(fields[4])
                                if fields[4].isdigit()
                                else 0,
                                "secure": "TRUE" in fields[3],
                                "httpOnly": False,
                                "sameSite": "Lax",
                            }
                            cookies.append(cookie)
            return cookies
        except Exception as e:
            logger.error(f"Error parsing Netscape cookies: {e}")
            return []

    def _load_json_cookies(self) -> List[Dict]:
        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error parsing JSON cookies: {e}")
            return []


class BaseParser(ABC, Generic[T]):
    @abstractmethod
    def parse(self, element: Any) -> T:
        pass


class WorkerManager:
    """Manages worker threads and their associated queues"""

    def __init__(self):
        self.workers = []  # [(thread, queue), ...]

    def register(self, thread, queue):
        """Register a worker thread and its queue"""
        self.workers.append((thread, queue))

    def stop_all(self, timeout=2):
        """Stop all worker threads with stronger termination guarantee"""
        # 先发送停止信号
        for _, queue in self.workers:
            while True:
                try:
                    queue.put_nowait(None)
                    break
                except queue.Full:
                    # 如果队列满,先清空再重试
                    try:
                        queue.get_nowait()
                    except queue.Empty:
                        pass

        # 确保所有线程结束
        end_time = time.time() + timeout
        for thread, _ in self.workers:
            if thread and thread.is_alive():
                remaining = max(0.1, end_time - time.time())  # 至少等待0.1秒
                thread.join(timeout=remaining)
                if thread.is_alive():
                    logger.warning(
                        f"Worker thread {thread.name} did not terminate properly"
                    )

    def clear_queues(self):
        """Clear all queues"""
        for _, queue in self.workers:
            while not queue.empty():
                queue.get_nowait()


def create_queue_worker(
    queue: Queue,
    process_func: Callable,
    running_event: threading.Event,
    desc: str = "Processing",
    cleanup_func: Optional[Callable] = None,
    timeout: float = 0.1,
):
    def worker():
        pbar = None
        try:
            pbar = tqdm(desc=desc)
            while running_event.is_set():
                try:
                    task = queue.get(timeout=timeout)
                    if task is None or not running_event.is_set():
                        break

                    process_func(task)
                    pbar.update(1)

                    queue.task_done()
                except Empty:
                    continue
        finally:
            if pbar:
                pbar.close()
            if cleanup_func:
                cleanup_func()

    return worker


class WorkerContext:
    def __init__(self):
        self.workers = []
        self._running = threading.Event()
        self._running.set()

    def register(self, thread, queue):
        self.workers.append((thread, queue))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._running.clear()

        # 停止所有worker
        for _, queue in self.workers:
            queue.put_nowait(None)

        # 等待worker结束
        for thread, _ in self.workers:
            thread.join()

        # 清理队列
        for _, queue in self.workers:
            while not queue.empty():
                queue.get_nowait()
