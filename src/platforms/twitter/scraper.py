import json
import sys
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Queue
from typing import Callable, Dict, List, Optional, Tuple

from urllib.parse import urlsplit
from returns.maybe import Nothing, Some
from DrissionPage._elements.chromium_element import ChromiumElement
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


class Worker:
    """Represents a worker that processes tasks from a queue."""

    def __init__(
        self,
        queue: Queue,
        process_func: Callable[[Dict], None],
        num_threads: int,
        pbar: tqdm,
        running_event: threading.Event,
    ):
        self.queue = queue
        self.process_func = process_func
        self.num_threads = num_threads
        self.pbar = pbar
        self.running_event = running_event
        self.threads: List[threading.Thread] = []

    def start(self):
        """Start worker threads."""
        for _ in range(self.num_threads):
            worker_func = create_queue_worker(
                queue=self.queue,
                process_func=self.process_func,
                running_event=self.running_event,
                pbar=self.pbar,
            )
            thread = threading.Thread(target=worker_func, daemon=True)
            thread.start()
            self.threads.append(thread)

    def stop(self):
        """Stop worker threads by sending sentinel and joining them."""
        for _ in self.threads:
            self.queue.put(None)
        for thread in self.threads:
            thread.join()

    def force_stop(self):
        for thread in self.threads:
            thread.join(timeout=0)


class WorkerManager:
    """Manages multiple Worker instances."""

    def __init__(self):
        self.workers: List[Worker] = []

    def add_worker(
        self,
        queue: Queue,
        process_func: Callable[[Dict], None],
        num_threads: int,
        pbar: tqdm,
        running_event: threading.Event,
    ):
        """Add a new worker to the manager."""
        worker = Worker(queue, process_func, num_threads, pbar, running_event)
        self.workers.append(worker)

    def start_all(self):
        """Start all workers."""
        for worker in self.workers:
            worker.start()

    def stop_all(self):
        """Stop all workers."""
        for worker in self.workers:
            worker.stop()

    def force_stop_all(self):
        for worker in self.workers:
            worker.force_stop()


class TwitterScraper(BaseScraper[Dict, TwitterCellParser]):
    """Twitter scraper implementation for extracting tweet data"""

    platform = "twitter"

    def __init__(self, **kwargs):
        print("preparations in progress...")
        super().__init__(**kwargs)

        self.tweets: List[Dict] = []
        self.on_relocating = False
        self.data_folder = ""

        self.pbars: List[tqdm] = []

        self.parser = TwitterCellParser()
        # self.worker_manager = WorkerManager()
        self.twitter_api = TwitterAPI(proxies=self.proxies, endpoint=self.endpoint)

        self.worker_manager = WorkerManager()
        self.full_data_queue = Queue()
        self.media_data_queue = Queue()
        self.media_desc_queue = Queue()
        self.translate_queue = Queue()

        self._running = threading.Event()
        self._running.set()
        # clean_all_uploaded_files()

    def _start_workers(self):
        """Initialize and start all worker threads."""
        # Start full data workers
        pbar_full = self._regist_pbar("Get tweet details")
        self.worker_manager.add_worker(
            queue=self.full_data_queue,
            process_func=self._process_full_data,
            num_threads=20,
            pbar=pbar_full,
            running_event=self._running,
        )

        # Start media download workers
        pbar_media = self._regist_pbar("Download media")
        self.worker_manager.add_worker(
            queue=self.media_data_queue,
            process_func=self._download_media,
            num_threads=20,
            pbar=pbar_media,
            running_event=self._running,
        )

        # Start translation workers
        pbar_translate = self._regist_pbar("Translate content")
        self.worker_manager.add_worker(
            queue=self.translate_queue,
            process_func=self._translate_content,
            num_threads=4,
            pbar=pbar_translate,
            running_event=self._running,
        )

        # Start media description workers
        pbar_desc = self._regist_pbar("Get media description")
        self.worker_manager.add_worker(
            queue=self.media_desc_queue,
            process_func=self._describe_media,
            num_threads=4,
            pbar=pbar_desc,
            running_event=self._running,
        )

        # Start all workers
        self.worker_manager.start_all()

    def _regist_pbar(self, desc: str) -> tqdm:
        """Register a new progress bar."""
        pbar = tqdm(desc=desc)
        self.pbars.append(pbar)
        return pbar

    def _process_full_data(self, task: Dict):
        """Process full tweet data."""
        if task.get("created_at"):
            self.media_data_queue.put(task)
            return
        info = self.twitter_api.get_tweet_details(task.get("rest_id"))
        task.update(info)
        if not task.get("rest_id") == "ad":
            self.media_data_queue.put(task)

    def _download_media(self, task: Dict):
        """Download media associated with a tweet."""
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
                        media["thumb_path"] = download(media.get("thumb"), thumb_folder)

        self.translate_queue.put(task)

    def _describe_media(self, task: Dict):
        """Describe media associated with a tweet."""
        if medias := task.get("media"):
            for media in medias:
                if not media.get("description") and (
                    media.get("duration_millis") <= 5 * 60 * 1000
                    if media.get("type") == "video"
                    else True
                ):
                    if (path := media.get("path")) != "media unavailable":
                        processor = MediaProcessor()
                        if res := processor.describe(path):
                            media["description"] = res.unwrap()
                        else:
                            media["description"] = "failed/gemini"

        if quote := task.get("quote"):
            if medias := quote.get("media"):
                for media in medias:
                    if not media.get("description") and (
                        media.get("duration_millis") <= 5 * 60 * 1000
                        if media.get("type") == "video"
                        else True
                    ):
                        if (path := media.get("path")) != "media unavailable":
                            processor = MediaProcessor()
                            if res := processor.describe(path):
                                media["description"] = res.unwrap()
                            else:
                                media["description"] = "failed/gemini"

    def _translate_content(self, task: Dict):
        """Translate the content of a tweet."""
        try:
            if not get(task, "content.translation"):
                translator = Translator(source_lang=get(task, "content.lang"))
                result = translator.translate(get(task, "content.text"))
                if isinstance(result, Some):
                    task["content"]["translation"] = result.unwrap()
                elif result is Nothing:
                    task["content"]["translation"] = None
            if quote := get(task, "quote"):
                if not get(quote, "content.translation"):
                    translator = Translator(source_lang=get(quote, "content.lang"))
                    result = translator.translate(get(quote, "content.text"))
                    if isinstance(result, Some):
                        quote["content"]["translation"] = result.unwrap()
                    elif result is Nothing:
                        quote["content"]["translation"] = None
        finally:
            self.media_desc_queue.put(task)

    def scrape(self, url: str) -> List[Dict]:
        """Scrape tweets from the given URL.

        Args:
            url: Twitter timeline URL to scrape

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
        """Save scraped data to a JSON file."""
        with open(
            self.save_path / folder / "scraped_data.json", "w", encoding="utf-8"
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    @retry(stop=stop_after_attempt(3))
    def _relocate(self, target_id) -> ChromiumElement:
        if self.on_relocating:
            raise RuntimeError("Already relocating")

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

        Args:
            current_ele: Current tweet element
            is_first: Whether this is the first element being retrieved

        Returns:
            Element: Next valid tweet element if found, None otherwise
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
                if self.tweets:
                    current_ele = self._relocate(self.tweets[-1]["id"])
                else:
                    current_ele = self._relocate(
                        "initial_id"
                    )  # Replace with a valid initial ID
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

    def _is_valid_tweet_element(self, ele: ChromiumElement) -> bool:
        """Check if element is a valid tweet element.

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
    def _get_next_cell(
        self, current_ele: ChromiumElement, is_first: bool
    ) -> ChromiumElement:
        """Get next tweet cell element and handle quoted tweets.

        Args:
            current_ele: Current tweet element
            is_first: Whether this is the first element being retrieved

        Returns:
            Element: Next tweet cell element
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

        Args:
            n_ele: Next tweet element being checked
            current_ele: Current tweet element

        Returns:
            tuple: (should_continue, new_current_element)
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

    def _perform_rescroll(
        self, current_ele: ChromiumElement, interval: int
    ) -> ChromiumElement:
        """Perform bidirectional scrolling to trigger tweet content loading.

        Args:
            current_ele: The current tweet element to scroll around
            interval: Current recursion interval

        Returns:
            Element: The last tweet element scrolled to
        """
        target_ele = current_ele
        count = 7 + (interval * 3)
        for i in range(-count, count):
            next_ele = target_ele.prev() if i < 0 else target_ele.next()
            self._see(next_ele)
            target_ele = next_ele
        return target_ele

    def close(self):
        """Gracefully close the scraper, stopping all workers and closing browsers."""
        try:
            self.worker_manager.stop_all()
            self.browser_manager.close_all_browsers()
        except KeyboardInterrupt:
            self.force_close()

        # Close all progress bars
        for pbar in self.pbars:
            pbar.close()

    def force_close(self):
        """Forcefully close the scraper, stopping all workers immediately."""
        self._running.clear()
        self.worker_manager.force_stop_all()
        self.browser_manager.close_all_browsers()
        # Close all progress bars
        for pbar in self.pbars:
            pbar.close()

    def _wait_for_thread(self, thread: threading.Thread, timeout: float = 0.1):
        """Wait for a thread to finish with a timeout.

        Args:
            thread: The thread to wait for
            timeout: Time to wait in seconds
        """
        while thread.is_alive():
            try:
                thread.join(timeout=timeout)
            except KeyboardInterrupt:
                self.force_close()
                raise
