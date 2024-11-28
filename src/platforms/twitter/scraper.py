import logging
import sys
import threading
import time
from enum import Enum
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple

from alive_progress import alive_bar
from DrissionPage._elements.chromium_element import ChromiumElement
from DrissionPage._pages.mix_tab import MixTab
from tenacity import retry, stop_after_attempt
from tqdm import tqdm

from ..base import BaseScraper, WorkerContext, WorkerManager, create_queue_worker
from .media_extract import TweetMediaExtractor
from .parser import TwitterCellParser

logger = logging.getLogger(__name__)


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
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()],
        )
        self.quote = None
        self.additional_browser = None
        self.addition_worker_thread = None
        self.extract_worker_thread = None
        self.addition_cookie_used = False
        self.context = None
        self.tweets = []
        self.on_relocating = False

        self.parser = TwitterCellParser()
        self.extractor = TweetMediaExtractor()
        self.worker_manager = WorkerManager()
        self.addition_task_queue = Queue()
        self.extract_queue = Queue()
        self._running = threading.Event()
        self._running.set()

    def _start_workers(self):
        self._start_extract_worker()
        self._start_addition_worker()

    def _start_extract_worker(self):
        """Start worker thread for processing media content extraction.

        Creates and starts a daemon thread that continuously processes tasks from the queue
        to extract media content from tweets. The worker thread:
        - Monitors the extract queue with a 1-second timeout
        - Handles None as shutdown signal
        - Extracts media content for each tweet
        - Processes queue until explicit shutdown
        """

        def process_media(task):
            media_info = self.extractor.extract(task)
            if self._running.is_set():
                task.update(media_info)

        worker_func = create_queue_worker(
            queue=self.extract_queue,
            process_func=process_media,
            running_event=self._running,
            desc="Extracting media content",
        )

        self.extract_worker_thread = threading.Thread(target=worker_func, daemon=True)
        self.extract_worker_thread.start()
        self.worker_manager.register(self.extract_worker_thread, self.extract_queue)

    def _start_addition_worker(self):
        """Start worker thread for processing additional content fetching.

        Creates and starts a daemon thread that continuously processes tasks from the queue
        to fetch additional content for tweets. The worker thread:
        - Monitors the task queue with a 1-second timeout
        - Handles None as shutdown signal
        - Fetches additional content for each task
        - Updates original tweet data with fetched content

        Note:
            - Uses daemon thread to allow clean program exit
            - Implements timeout to prevent permanent blocking
            - Continues silently on empty queue
            - Task queue is processed until explicit shutdown signal
        """

        def process_additional(task):
            additional = self._fetch_additional_content(task)

            if self._running.is_set():
                task.update(additional)
                self.extract_queue.put(task)

        worker_func = create_queue_worker(
            queue=self.addition_task_queue,
            process_func=process_additional,
            running_event=self._running,
            desc="Fetching additional content",
        )

        self.addition_worker_thread = threading.Thread(target=worker_func, daemon=True)
        self.addition_worker_thread.start()
        self.worker_manager.register(
            self.addition_worker_thread, self.addition_task_queue
        )

    def scrape(self, url: str, limit: Optional[int] = 100) -> List[Dict]:
        """Scrape tweets from the given URL.

        Args:
            url: Twitter timeline URL to scrape
            limit: Maximum number of tweets to scrape (None for no limit)

        Returns:
            List of dictionaries containing tweet data
        """
        tweet_count = 0
        pbar = None
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
                    data.update({TweetFields.QUOTE.value: self.quote})
                    data.update({TweetFields.CONTEXT.value: self.context})
                    self.addition_task_queue.put(data)
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
            print(f"Scraped {tweet_count} tweets\n")
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
        with open("error_cur.html", "w", encoding="utf-8") as f:
            f.write(current_ele.html)
        with open("error_next.html", "w", encoding="utf-8") as f:
            f.write(n_ele.html)
        print("Failed to get valid tweet or no more tweets")
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
        self._rm_interference_ele(n_ele, self.page)
        self._rm_quoted_tweet(n_ele, self.page)

        return n_ele

    def _rm_interference_ele(self, element, tab):
        """Remove interference elements that may affect tweet parsing.

        Removes verification icons and attribution elements that could interfere
        with clean tweet content extraction.

        Args:
            element: Tweet element to clean
            tab: Browser tab instance for element removal
        """
        self._rm_verify_icon(element, tab)
        self._rm_attribution(element, tab)
        self._rm_context(element, tab)
        self._rm_context_announcement(element, tab)
        self._rm_username_divlink(element, tab)

    def _rm_username_divlink(self, element, tab: MixTab):
        """Remove username link from tweet element.

        Args:
            element: Tweet element to clean
            tab: Browser tab instance for element removal

        Note:
            - Will skip if element is a progressbar to avoid errors
            - Only removes username links from User-Name elements
        """
        if username_ele := element.ele("@data-testid=User-Name", timeout=0):
            if divlink_eles := self.parser._div_link_elements(username_ele):
                [tab.remove_ele(e) for e in divlink_eles]

    def _rm_quoted_tweet(self, element: ChromiumElement, tab: MixTab):
        """Remove quoted tweet element from tweet element.

        Args:
            element: Tweet element to clean
            tab: Browser tab instance for element removal

        Note:
            - Will skip if element is a progressbar to avoid errors
            - Sets self.quote to True if quoted tweet is found and removed
            - Sets self.quote to None if no quoted tweet is found
        """
        if quoted_ele := self.parser._div_link_element(element):
            self.quote = True
            tab.remove_ele(quoted_ele)
        else:
            self.quote = None

    def _rm_verify_icon(self, element: ChromiumElement, tab: MixTab):
        """Remove verification icon from tweet element.

        Args:
            element: Tweet element containing the verification icon
            tab: Browser tab instance for element removal
        """
        verify_ele = element.ele("@data-testid=icon-verified", timeout=0)
        if verify_ele:
            tab.remove_ele(verify_ele.parent())

    def _rm_context(self, element: ChromiumElement, tab: MixTab):
        """Remove context label from tweet element."""
        context_ele = element.ele("@data-testid=birdwatch-pivot", timeout=0)
        if context_ele:
            tab.remove_ele(context_ele)

    def _rm_context_announcement(self, element: ChromiumElement, tab: MixTab):
        """Remove context announcement label from tweet element."""
        context_announcement_ele = element.ele(
            "text:Context is written by people who use X, and appears when rated helpful by others.",
            timeout=0,
        )
        if context_announcement_ele:
            self.context = True
            tab.remove_ele(context_announcement_ele.parent("@dir=ltr"))
        self.context = None

    def _rm_attribution(self, element: ChromiumElement, tab: MixTab):
        """Remove attribution label from tweet element.

        Args:
            element: Tweet element containing the attribution
            tab: Browser tab instance for element removal
        """
        attribution_ele = element.ele("@aria-label:Attributed to", timeout=0)
        if attribution_ele:
            tab.remove_ele(attribution_ele.parent())

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

    def _get_tweet_content(self, page: MixTab) -> Any:
        """Get the main tweet content element from the timeline.

        Finds and returns the first valid tweet cell element from the page's timeline.

        Args:
            page: Browser page instance containing the tweet

        Returns:
            Element: The tweet content element if found, None otherwise
        """
        return self._get_next_valid_cell(
            page.ele("@aria-label^Timeline"), is_first=True
        )

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
            logger.info(
                f"All attempts failed, retrying {retry_count + 1}/{MAX_RETRIES}\n"
            )
            return self._get_cell(page, url, retry_count + 1)

        raise Exception(
            f"Failed to get cell after {MAX_RETRIES} complete retries, url: {url}\n"
        )

    def _get_quoted_element(self, tweet_cell: ChromiumElement, page: MixTab, url: str):
        """Get quoted tweet element with retry logic.

        Args:
            tweet_cell: Tweet cell element containing quote
            page: Browser page instance
            url: Tweet URL for retry attempts

        Returns:
            Element: Quoted tweet element if found, None otherwise
        """
        # 首次尝试
        if quoted_ele := self.parser._div_link_element(tweet_cell):
            return quoted_ele, page

        # 刷新重试
        page.refresh()
        tweet_cell, page = self._get_cell(page, url)
        if tweet_cell:
            if quoted_ele := self.parser._div_link_element(tweet_cell):
                return quoted_ele, page

        # 重置浏览器重试(带cookie)
        page = self._reset_browser(url, with_cookies=True)
        tweet_cell, page = self._get_cell(page, url)
        if tweet_cell:
            if quoted_ele := self.parser._div_link_element(tweet_cell):
                return quoted_ele, page

        return None, page

    def _fetch_additional_content(self, data: dict) -> Dict:
        """Fetch additional tweet content including full text and quoted tweets.

        Creates a new browser instance if needed and fetches the complete tweet content
        and any quoted tweets referenced in the original tweet.

        Args:
            data: Dictionary containing tweet data with fields:
                - url: Tweet URL to fetch
                - content_uncomplete: Flag indicating if content is truncated
                - quoted_tweet: Flag indicating if tweet has quotation

        Returns:
            dict: Additional content with fields:
                - content: Full tweet text (if original was truncated)
                - content_uncomplete: Set to None after fetching full content
                - quoted_tweet: Quoted tweet data including id and content

        Note:
            Uses a separate browser instance to avoid interfering with main scraping.
        """
        if not data.get(TweetFields.CONTENT_UNCOMPLETE.value) and not data.get(
            TweetFields.QUOTE.value
        ):
            return data

        result = data.copy()
        if not self.additional_browser:
            self.additional_browser, page = self.browser_manager.init_browser(
                "additional", load_cookies=False
            )
        else:
            page = self.browser_manager.get_page("additional")

        tweet_id = data.get("id")
        tweet_url = f"https://x.com/i/status/{tweet_id}"
        page.get(tweet_url)

        tweet_cell, page = self._get_cell(page, tweet_url)

        # 获取完整内容
        if data.get(TweetFields.CONTENT_UNCOMPLETE.value):
            result.update(self.parser._extract_content(tweet_cell))
            result.update(
                {
                    TweetFields.CONTENT_UNCOMPLETE.value: None,
                }
            )
        self._rm_interference_ele(tweet_cell, page)
        # 获取引用推文
        if data.get(TweetFields.QUOTE.value):
            quoted_ele, page = self._get_quoted_element(tweet_cell, page, tweet_url)
            if quoted_ele:
                quoted_ele.ele("@role=presentation", timeout=0).click()
                quoted_cell, page = self._get_cell(page, page.url)
                self._rm_interference_ele(quoted_cell, page)
                result[TweetFields.QUOTE.value] = {}
                result[TweetFields.QUOTE.value].update(
                    self.parser._extract_content(quoted_cell)
                )
                result[TweetFields.QUOTE.value].update(
                    self.parser._check_videos(quoted_cell)
                )
                result[TweetFields.QUOTE.value].update(
                    {
                        "id": page.url.split("/")[-1],
                    }
                )

        return result

    def close(self):
        try:
            if t := self.addition_worker_thread:
                self.addition_task_queue.put(None)
                self._wait_for_thread(t)

            if t := self.extract_worker_thread:
                self.extract_queue.put(None)
                self._wait_for_thread(t)

            self.addition_worker_thread = None
            self.extract_worker_thread = None
            # self.browser_manager.close_all_browsers()
        except KeyboardInterrupt:
            self.force_close()

    def force_close(self):
        self._running.clear()
        if t := self.addition_worker_thread:
            t.join(timeout=0)
        if t := self.extract_worker_thread:
            t.join(timeout=0)
        # self.browser_manager.close_all_browsers()

    def _wait_for_thread(self, thread: threading.Thread, timeout=0.1):
        while thread.is_alive():
            try:
                thread.join(timeout=timeout)
            except KeyboardInterrupt:
                self.force_close()
                raise
