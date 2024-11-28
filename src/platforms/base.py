import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
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
    ):
        self.browser_path = browser_path
        self.headless = headless
        self.cookies_path = Path(cookies_path)
        self.save_path = save_path or Path("data")
        self.parser: Optional[P] = None
        self.browser_manager = BrowserManager(browser_path, headless, cookies_path)
        self.browser: Optional[Chromium] = None
        self.page = None
        self._init_scraper()

    def _init_scraper(self):
        self.browser, self.page = self.browser_manager.init_browser(headless=False)

    @abstractmethod
    def scrape(self, url: str) -> List[T]:
        pass

    def close(self):
        self.browser_manager.close_all_browsers()


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
        count = 0
        pbar = None
        try:
            with tqdm(desc=desc) as pbar:
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
                        break
        finally:
            if cleanup_func:
                cleanup_func()
            print(f"{desc} {count} tasks")

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
