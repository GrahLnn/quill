import json
import sys
import threading
import time
import traceback
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from DrissionPage._elements.chromium_element import ChromiumElement
from returns.maybe import Some
from tenacity import retry, stop_after_attempt
from tqdm import tqdm

from src.service.media_processer import MediaProcessor
from src.service.models.gemini import clean_all_uploaded_files
from src.service.translator import Translator

from ..base import BaseScraper, WorkerContext, create_queue_worker
from .download_media import download
from .html_generator import generate_html
from .parser import TwitterCellParser
from .tw_api import TwitterAPI, get


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
        print("preparations in progress...")
        super().__init__(**kwargs)

        self.tweets = []
        self.on_relocating = False
        self.data_folder = ""

        self.pbars: List[tqdm] = []

        self.parser = TwitterCellParser()
        # self.worker_manager = WorkerManager()
        self.twitter_api = TwitterAPI(proxies=self.proxies, endpoint=self.endpoint)

        self.get_data_threads: List[threading.Thread] = []
        self.desc_media_threads: List[threading.Thread] = []
        self.media_data_threads: List[threading.Thread] = []
        self.translate_threads: List[threading.Thread] = []
        self.full_data_queue = Queue()
        self.media_data_queue = Queue()
        self.media_desc_queue = Queue()
        self.translate_queue = Queue()

        self._running = threading.Event()
        self._running.set()
        # clean_all_uploaded_files()

    def _start_workers(self):
        self._start_fulldata_worker()
        self._start_media_worker()
        self._start_desc_worker()
        self._start_translate_worker()

    def _regist_pbar(self, desc: str):
        pbar = tqdm(desc=desc)
        self.pbars.append(pbar)
        return pbar

    def _start_translate_worker(self):
        num_threads = 20
        pbar = self._regist_pbar("Translate content")

        def translate(task: Dict):
            if not get(task, "content.translation"):
                translator = Translator(source_lang=get(task, "content.lang"))
                result = translator.translate(get(task, "content.text"))
                if isinstance(result, Some):
                    task["content"]["translation"] = result.unwrap()
            self.media_desc_queue.put(task)

        for _ in range(num_threads):
            worker_func = create_queue_worker(
                queue=self.translate_queue,
                process_func=translate,
                running_event=self._running,
                pbar=pbar,
            )
            thread = threading.Thread(target=worker_func, daemon=True)
            thread.start()
            self.translate_threads.append(thread)

    def _start_desc_worker(self):
        num_threads = 20
        pbar = self._regist_pbar("Get media description")

        def describe_media(task: Dict):
            processor = MediaProcessor()
            try:
                if medias := task.get("media"):
                    for media in medias:
                        if not media.get("description") and (
                            media.get("duration_millis") <= 5 * 60 * 1000
                            if media.get("type") == "video"
                            else True
                        ):
                            if (path := media.get("path")) != "media unavailable":
                                if res := processor.describe(path):
                                    media["description"] = res.unwrap()
                                else:
                                    print(
                                        f"Failed to describe main media from {task.get('rest_id')}: {str(res)}"
                                    )

                if quote := task.get("quote"):
                    if medias := quote.get("media"):
                        for media in medias:
                            if not media.get("description") and (
                                media.get("duration_millis") <= 5 * 60 * 1000
                                if media.get("type") == "video"
                                else True
                            ):
                                if (path := media.get("path")) != "media unavailable":
                                    if res := processor.describe(path):
                                        media["description"] = res.unwrap()
                                    else:
                                        print(
                                            f"Failed to describe quote media from {task.get('rest_id')}: {str(res)}"
                                        )

            except Exception as e:
                print(f"Failed to describe media from {task.get('rest_id')}: {e}")
                traceback.print_exception(type(e), e, e.__traceback__)
                return

        # 创建并启动多个工作线程
        for _ in range(num_threads):
            worker_func = create_queue_worker(
                queue=self.media_desc_queue,
                process_func=describe_media,
                running_event=self._running,
                pbar=pbar,
            )

            # 启动线程
            thread = threading.Thread(target=worker_func, daemon=True)
            thread.start()
            self.desc_media_threads.append(thread)

    def _start_media_worker(self):
        num_threads = 20
        pbar = self._regist_pbar("Download media")

        def download_media(task: Dict):
            save_folder = self.save_path / self.data_folder / "media"
            thumb_folder = save_folder / "thumb"
            avatar_folder = save_folder / "avatar"
            author_info = task.get("author")
            # todo: Update the global avatar when the profile picture is updated.
            if not get(author_info, "avatar.path"):
                author_info["avatar"]["path"] = download(
                    get(author_info, "avatar.url"), avatar_folder
                )

            if medias := task.get("media"):
                for media in medias:
                    if not media.get("path"):
                        media["path"] = download(media.get("url"), save_folder)
                    if (
                        media.get("thumb")
                        and not media.get("thumb_path")
                        and media.get("path") != "media unavailable"
                    ):
                        media["thumb_path"] = download(media.get("thumb"), thumb_folder)
            if quote := task.get("quote"):
                author_info = quote.get("author")
                if not get(author_info, "avatar.path"):
                    author_info["avatar"]["path"] = download(
                        get(author_info, "avatar.url"), avatar_folder
                    )
                if medias := quote.get("media"):
                    for media in medias:
                        if not media.get("path"):
                            media["path"] = download(media.get("url"), save_folder)
                        if (
                            media.get("thumb")
                            and not media.get("thumb_path")
                            and media.get("path") != "media unavailable"
                        ):
                            media["thumb_path"] = download(
                                media.get("thumb"), thumb_folder
                            )

            # self.translate_queue.put(task)

        for _ in range(num_threads):
            worker_func = create_queue_worker(
                queue=self.media_data_queue,
                process_func=download_media,
                running_event=self._running,
                pbar=pbar,
            )
            thread = threading.Thread(target=worker_func, daemon=True)
            thread.start()
            self.media_data_threads.append(thread)

    def _start_fulldata_worker(self):
        num_threads = 20
        pbar = self._regist_pbar("Get tweet details")

        def process_data(task: Dict):
            if task.get("created_at"):
                self.media_data_queue.put(task)
                return
            info = self.twitter_api.get_tweet_details(task.get("rest_id"))
            task.update(info)
            if not task.get("rest_id") == "ad":
                self.media_data_queue.put(task)

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
            self.get_data_threads.append(thread)

    def scrape(self, url: str) -> List[Dict]:
        """Scrape tweets from the given URL.

        Args:
            url: Twitter timeline URL to scrape
            limit: Maximum number of tweets to scrape (None for no limit)

        Returns:
            List of dictionaries containing tweet data
        """

        parsed_url = urlsplit(url)
        self.data_folder = (parsed_url.netloc + parsed_url.path).replace("/", ".")
        (self.save_path / self.data_folder).mkdir(exist_ok=True)
        saved_data = self._saved_data(self.data_folder)
        saved_ids = [d["rest_id"] for d in saved_data]

        for data in saved_data:
            self.full_data_queue.put(data)

        try:
            with WorkerContext() as ctx:
                self.page.get(url)
                self._start_workers()
                timeline = self.page.ele("@aria-label^Timeline")

                current_cell = None

                pbar = tqdm(desc="Scraping")
                self.pbars.append(pbar)
                current_cell = self._get_next_valid_cell(timeline, is_first=True)
                match_count = 0
                while current_cell and ctx._running.is_set():
                    if match_count > 10:
                        break
                    data = self.parser.parse(current_cell)
                    if data["rest_id"] in saved_ids:
                        match_count += 1
                        current_cell = self._get_next_valid_cell(current_cell)
                        continue
                    match_count = 0
                    self.full_data_queue.put(data)
                    self.tweets.append(data)
                    current_cell = self._get_next_valid_cell(current_cell)
                    pbar.update(1)

        finally:
            if sys.exc_info()[0] is None:
                self.close()
            else:
                self.force_close()
        tweets: List[Dict] = self.tweets + saved_data
        # tweets.sort(
        #     key=lambda x: datetime.strptime(
        #         x.get("created_at", "Mon Jan 01 00:00:00 +0000 2000"),
        #         "%a %b %d %H:%M:%S +0000 %Y",
        #     ),
        #     reverse=True,
        # )
        full_data = {
            "metadata": {
                "url": url,
                "created_at": datetime.now().isoformat(),
            },
            "results": [tweet for tweet in tweets if tweet.get("rest_id") != "ad"],
        }
        self._save_data(
            self.data_folder,
            full_data,
        )
        # 生成HTML预览
        preview_path = self.save_path / self.data_folder / "gallery.html"
        generate_html(full_data, preview_path)
        return tweets

    def _saved_data(self, folder: str) -> List[Dict]:
        """Get previously saved tweet data"""
        path: Path = self.save_path / folder / "scraped_data.json"
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data: Dict = json.load(f)
        return data.get("results", [])

    def _save_data(self, folder: str, data: Dict):
        with open(
            self.save_path / folder / "scraped_data.json", "w", encoding="utf-8"
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

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

        if n_ele.ele(
            "text:A moderator hid this Post for breaking a Community rule. ", timeout=0
        ):
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

    def close(self):
        try:
            if threads := self.get_data_threads:
                # 为每个工作者线程发送一个停止信号
                for _ in threads:
                    self.full_data_queue.put(None)
                # 等待所有线程结束
                for thread in threads:
                    self._wait_for_thread(thread)

            if threads := self.media_data_threads:
                for _ in threads:
                    self.media_data_queue.put(None)
                for thread in threads:
                    self._wait_for_thread(thread)

            if threads := self.desc_media_threads:
                for _ in threads:
                    self.media_desc_queue.put(None)
                for thread in threads:
                    self._wait_for_thread(thread)

            if threads := self.translate_threads:
                for _ in threads:
                    self.translate_queue.put(None)
                for thread in threads:
                    self._wait_for_thread(thread)

            self.browser_manager.close_all_browsers()
        except KeyboardInterrupt:
            self.force_close()

        # 关闭所有进度条
        for pbar in self.pbars:
            pbar.close()

    def force_close(self):
        self._running.clear()

        if t := self.get_data_threads:
            for thread in t:
                thread.join(timeout=0)

        if t := self.media_data_threads:
            for thread in t:
                thread.join(timeout=0)

        if t := self.desc_media_threads:
            for thread in t:
                thread.join(timeout=0)

        if t := self.translate_threads:
            for thread in t:
                thread.join(timeout=0)

        self.browser_manager.close_all_browsers()
        # 关闭所有进度条
        for pbar in self.pbars:
            pbar.close()

    def _wait_for_thread(self, thread: threading.Thread, timeout=0.1):
        while thread.is_alive():
            try:
                thread.join(timeout=timeout)
            except KeyboardInterrupt:
                self.force_close()
                raise
