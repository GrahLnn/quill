import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
import traceback
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from DrissionPage import Chromium
from tqdm import tqdm

from .browser_manager import BrowserManager

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
        proxies: List[str] = [],  # List of proxy servers
        endpoint: Optional[str] = None,  # Endpoint URL
    ):
        self.browser_path = browser_path
        self.headless = headless
        self.cookies_path = Path(cookies_path)
        self.save_path = save_path or Path("output")
        self.parser: Optional[P] = None
        self.browser_manager = BrowserManager(browser_path, headless, cookies_path)
        self.browser: Optional[Chromium] = None
        self.page = None
        self.proxies = proxies + [None]
        self.endpoint = endpoint
        self._init_scraper()
        self.save_path.mkdir(exist_ok=True)

    def _init_scraper(self):
        self.browser, self.page = self.browser_manager.init_browser()

    @abstractmethod
    def scrape(self, url: str) -> List[T]:
        pass

    def close(self):
        self.browser_manager.close_all_browsers()


class BaseParser(ABC, Generic[T]):
    @abstractmethod
    def parse(self, element: Any) -> T:
        pass


def create_queue_worker(
    queue: Queue,
    process_func: Callable,
    running_event: threading.Event,
    desc: str = "Processing",
    cleanup_func: Optional[Callable] = None,
    timeout: float = 0.1,
    pbar=None,
):
    def worker():
        count = 0
        try:
            nonlocal pbar
            if pbar is None:
                pbar = tqdm(desc=desc)

            while running_event.is_set():
                try:
                    task = queue.get(timeout=timeout)
                    if task is None or not running_event.is_set():
                        break

                    process_func(task)
                    pbar.update(1)
                    count += 1
                    queue.task_done()
                except Empty:
                    continue
                except Exception as e:
                    logging.error(f"Error processing task: {e}")
                    traceback.print_exception(type(e), e, e.__traceback__)
                    continue

        finally:
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
