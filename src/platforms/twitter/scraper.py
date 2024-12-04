import sys
import threading
import time
from enum import Enum
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple

from DrissionPage._elements.chromium_element import ChromiumElement
from DrissionPage._pages.mix_tab import MixTab
from tenacity import retry, stop_after_attempt
from tqdm import tqdm

from ..base import BaseScraper, WorkerContext, WorkerManager, create_queue_worker
from .media_extract import TweetMediaExtractor
from .parser import TwitterCellParser
from .tw_api import TwitterAPI


class TweetFields(str, Enum):
    """Tweet data fields enum"""

    QUOTE = "quote"
    CONTEXT = "context"
    CONTENT_UNCOMPLETE = "content_uncomplete"
    CONTENT = "content"


class TwitterScraper(BaseScraper[Dict, TwitterCellParser]):
    """Twitter scraper implementation for extracting tweet data"""

    platform = "twitter"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.quote = None
        self.additional_browser = None
        self.addition_worker_thread = None
        self.extract_worker_thread = None
        self.get_data_threads: List[threading.Thread] = []
        self.addition_cookie_used = False
        self.context = None
        self.tweets = []
        self.on_relocating = False

        self.parser = TwitterCellParser()
        self.extractor = TweetMediaExtractor()
        self.worker_manager = WorkerManager()
        self.full_data_queue = Queue()
        self._running = threading.Event()
        self.twitter_api = TwitterAPI(proxies=self.proxies)
        self._running.set()

    def _start_workers(self):
        self._start_data_worker()

    def _start_data_worker(self):
        num_threads = 20

        def process_data(task):
            info = self.twitter_api.get_tweet_details(task.get("rest_id"))
            task.update(info)

        pbar = tqdm(desc="Get tweet details")
        # 创建并启动多个工作线程
        for _ in range(num_threads):
            worker_func = create_queue_worker(
                queue=self.full_data_queue,
                process_func=process_data,
                running_event=self._running,
                pbar=pbar,
            )

            # 启动线程
            thread = threading.Thread(target=worker_func, daemon=True)
            thread.start()
            self.worker_manager.register(thread, self.full_data_queue)
            self.get_data_threads.append(thread)

    def scrape(self, url: str) -> List[Dict]:
        """Scrape tweets from the given URL.

        Args:
            url: Twitter timeline URL to scrape
            limit: Maximum number of tweets to scrape (None for no limit)

        Returns:
            List of dictionaries containing tweet data
        """
        tweet_count = 0
        pbar = None
        print("init browser")
        try:
            with WorkerContext() as ctx:
                self.page.get(url)
                self._start_workers()
                timeline = self.page.ele("@aria-label^Timeline")
                saved_data = self._saved_data()
                current_cell = None

                def process_tweet(cell):
                    nonlocal tweet_count
                    data = self.parser.parse(cell)
                    self.full_data_queue.put(data)
                    self.tweets.append(data)
                    tweet_count += 1
                    return self._get_next_valid_cell(cell)

                pbar = tqdm(desc="Scraping")
                current_cell = self._get_next_valid_cell(timeline, is_first=True)

                while current_cell and ctx._running.is_set():
                    # if limit is not None and tweet_count >= limit:
                    #     break
                    current_cell = process_tweet(current_cell)
                    pbar.update(1)

        finally:
            if pbar is not None:
                pbar.close()
            if sys.exc_info()[0] is None:
                self.close()
            else:
                self.force_close()

        return self.tweets

    def _saved_data(self):
        """Get previously saved tweet data"""
        pass

    @retry(stop=stop_after_attempt(3))
    def _relocate(self, target_id) -> ChromiumElement:
        if self.on_relocating:
            raise

        self.page.refresh()
        timeline = self.page.ele("@aria-label^Timeline")
        pbar = tqdm(desc="found error, relocating tweet...")
        current_cell = self._get_next_valid_cell(timeline, is_first=True)
        self.on_relocating = True
        while True:
            data = self.parser._extract_metadata(current_cell)
            if data["id"] == target_id:
                print(f"Found: {data['url']}, quoted: {self.quote}")
                break
            pbar.update(1)
            current_cell = self._get_next_valid_cell(current_cell)
        return current_cell

    def _get_next_valid_cell(
        self, current_ele: ChromiumElement, is_first=False
    ) -> Optional[ChromiumElement]:
        """Get next valid tweet element with retry and scroll handling.

        Attempts to get the next valid tweet element using a combination of retry logic
        and scroll handling. Does not remove current cell to prevent memory leaks.

        Args:
            current_ele: Current tweet element
            is_first: Whether this is the first element being retrieved (default: False)
            bar: Progress bar instance for updates (default: None)

        Returns:
            Element: Next valid tweet element if found, None otherwise

        Note:
            Uses MAX_ATTEMPTS (150) total attempts with MAX_RETRIES (3) per element
            and SCROLL_INTERVAL (10) between scroll operations.
        """
        MAX_ATTEMPTS = 150
        MAX_RETRIES = 3

        try_count = 0

        for _ in range(MAX_ATTEMPTS):
            if try_count >= MAX_RETRIES:
                break
            try:
                n_ele = self._get_next_cell(current_ele, is_first)
                if n_ele and self._is_valid_tweet_element(n_ele):
                    return n_ele
            except Exception:
                current_ele = self._relocate(self.tweets[-1]["id"])
                continue
            should_continue, new_current_ele = self._handle_special_cases(
                n_ele, current_ele
            )
            if should_continue:
                current_ele = new_current_ele
                continue
            if self._should_rescroll(n_ele):
                current_ele = self._perform_rescroll(current_ele, try_count)
                try_count += 1
            time.sleep(0.2)
        self.page.stop_loading()

        return None

    def _is_valid_tweet_element(self, ele):
        """Check if element is a valid tweet element.

        Validates that the element has the correct data-testid attributes
        for a tweet cell, tweet content, and user name.

        Args:
            ele: Element to validate

        Returns:
            bool: True if element is a valid tweet, False otherwise
        """
        return bool(
            ele.attr("data-testid") == "cellInnerDiv"
            and ele.ele("@data-testid=tweet", timeout=0)
            and ele.ele("@data-testid=User-Name", timeout=0)
        )

    @retry(stop=stop_after_attempt(3))
    def _get_next_cell(self, current_ele: ChromiumElement, is_first) -> ChromiumElement:
        """Get next tweet cell element and handle quoted tweets.

        Retrieves the next tweet cell element, either as the first element or
        the next sibling. Also handles quoted tweet elements by removing them
        after saving their content.

        Args:
            current_ele: Current tweet element
            is_first: Whether this is the first element being retrieved

        Returns:
            Element: Next tweet cell element

        Note:
            Decorated with @retry to attempt the operation up to 3 times.
            Saves quoted tweet HTML to tmp/quoted_tweet.html for debugging.
        """
        if is_first:
            n_ele = current_ele.ele("@data-testid=cellInnerDiv")
        else:
            n_ele = current_ele.next()

        self._see(n_ele)

        return n_ele

    def _see(self, element: ChromiumElement):
        """Scroll element into viewport.

        Args:
            element: Element to scroll into view
        """
        element.scroll.to_see()

    def _handle_special_cases(
        self, n_ele: ChromiumElement, current_ele: ChromiumElement
    ) -> Tuple[bool, ChromiumElement]:
        """Handle special tweet cases and error conditions.

        Handles unavailable tweets and retry buttons, updating progress bar as needed.

        Args:
            n_ele: Next tweet element being checked
            current_ele: Current tweet element
            bar: Progress bar instance for updates

        Returns:
            tuple: (should_continue, new_current_element)
                - should_continue: Whether to continue processing
                - new_current_element: Element to use for next iteration
        """
        if n_ele.ele("text:This Post is unavailable.", timeout=0):
            return True, n_ele

        if retry_button := n_ele.ele("Retry", timeout=0):
            retry_button.click()
            time.sleep(0.5)
            return True, current_ele

        return False, current_ele

    def _should_rescroll(self, n_ele: ChromiumElement) -> bool:
        """Check if page needs rescrolling to load more content.

        Determines if element is empty and not showing a loading indicator.

        Args:
            n_ele: Element to check for content

        Returns:
            bool: True if rescroll is needed, False otherwise
        """
        try:
            has_progressbar = n_ele.ele("@role=progressbar", timeout=0)
            has_progressbar.wait.disabled_or_deleted()
        except Exception:
            has_progressbar = False

        return bool(not n_ele.text and not has_progressbar)

    def _perform_rescroll(self, current_ele: ChromiumElement, interval):
        """Perform bidirectional scrolling to trigger tweet content loading.

        Scrolls 10 elements up and down from the current element to ensure Twitter's
        infinite scroll loads tweets in both directions. This helps prevent gaps in
        the tweet timeline.

        Args:
            current_ele: The current tweet element to scroll around

        Returns:
            Element: The last tweet element scrolled to, which will be 10 elements
                    below the starting position
        """
        target_ele = current_ele
        count = 7 + (interval * 3)
        for i in range(-count, count):
            next_ele = target_ele.prev() if i < 0 else target_ele.next()
            self._see(next_ele)
            target_ele = next_ele
        return target_ele

    def _try_get_cell(self, page: MixTab):
        """Attempt to get the tweet cell element with timeout.

        Makes a single attempt to find the tweet cell element, with a 2 second timeout
        to avoid hanging on failed requests.

        Args:
            page: Browser page instance to search

        Returns:
            Element: Tweet cell element if found within timeout
            None: If element not found or timeout occurred
        """
        if tweet_cell := page.ele("@data-testid=cellInnerDiv", timeout=2):
            return tweet_cell
        return None

    def _reset_browser(self, url, with_cookies=False):
        """Reset the browser instance and navigate to URL.

        Creates a fresh browser instance using browser manager, optionally loads cookies,
        and navigates to the specified URL.

        Args:
            url: Target URL to navigate to
            with_cookies: Whether to load saved cookies (default: False)

        Returns:
            Page: New browser page instance at the target URL
        """
        if self.additional_browser:
            self.browser_manager.close_browser("additional")

        # 使用browser manager创建新的浏览器实例
        self.additional_browser, page = self.browser_manager.init_browser(
            "additional", load_cookies=with_cookies
        )

        page.get(url)
        return page

    def _get_cell(self, page, url, retry_count=0):
        """Get tweet cell element from the page.

        This method attempts to retrieve the tweet cell element while minimizing cookie usage
        to avoid rate limiting from Twitter.

        Args:
            page: Browser page instance
            url: Tweet URL to fetch

        Returns:
            tuple: (cell_element, page) where cell_element is the tweet cell if found,
                   None otherwise

        Note:
            Frequent requests with cookies may trigger Twitter's rate limiting mechanism.
        """
        MAX_RETRIES = 10
        if retry_count > 0:
            time.sleep((retry_count + 5) * 60)
        if self.addition_cookie_used:
            # 重置浏览器重试(不带cookie)
            page = self._reset_browser(url)
            self.addition_cookie_used = False
            if cell := self._try_get_cell(page):
                return cell, page

        # 尝试直接获取
        if cell := self._try_get_cell(page):
            return cell, page

        # 刷新重试
        page.refresh()
        if cell := self._try_get_cell(page):
            return cell, page

        # 重置浏览器重试(不带cookie)
        page = self._reset_browser(url)
        if cell := self._try_get_cell(page):
            return cell, page

        # 最后尝试带cookie的重置
        page = self._reset_browser(url, with_cookies=True)
        self.addition_cookie_used = True
        if cell := self._try_get_cell(page):
            return cell, page

        # 所有重试都失败
        if retry_count < MAX_RETRIES:
            print(f"All attempts failed, retrying {retry_count + 1}/{MAX_RETRIES}\n")
            return self._get_cell(page, url, retry_count + 1)

        raise Exception(
            f"Failed to get cell after {MAX_RETRIES} complete retries, url: {url}\n"
        )

    def close(self):
        try:
            if threads := self.get_data_threads:
                # 为每个工作者线程发送一个停止信号
                for _ in threads:
                    self.full_data_queue.put(None)
                # 等待所有线程结束
                for thread in threads:
                    self._wait_for_thread(thread)

            self.browser_manager.close_all_browsers()
        except KeyboardInterrupt:
            self.force_close()

    def force_close(self):
        self._running.clear()

        if t := self.get_data_threads:
            for thread in t:
                thread.join(timeout=0)
        self.browser_manager.close_all_browsers()

    def _wait_for_thread(self, thread: threading.Thread, timeout=0.1):
        while thread.is_alive():
            try:
                thread.join(timeout=timeout)
            except KeyboardInterrupt:
                self.force_close()
                raise
