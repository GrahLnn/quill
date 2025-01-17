import json
import signal
import sys
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Queue
from typing import Callable, Dict, List, Optional, Union
from urllib.parse import urlsplit

from tqdm import tqdm

from src.service.helper import get, remove_none_values
from src.service.keyword_processer import KeywordProcesser
from src.service.media_processer import MediaProcessor
from src.service.translator import Translator

from ..base import BaseScraper, WorkerContext, create_queue_worker
from .download_media import download
from .html_generator import generate_html
from .parser import TwitterCellParser
from .tw_api import TwitterAPI
from .utils import rm_mention


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
        running_event: threading.Event,
        pbar: tqdm = None,
        next_queue: Optional[Queue] = None,
    ):
        self.queue = queue
        self.process_func = process_func
        self.num_threads = num_threads
        self.pbar = pbar
        self.running_event = running_event
        self.threads: List[threading.Thread] = []
        self.next_queue = next_queue

    def start(self):
        """Start worker threads."""
        for _ in range(self.num_threads):
            worker_func = create_queue_worker(
                queue=self.queue,
                process_func=self.process_func,
                running_event=self.running_event,
                pbar=self.pbar,
                next_queue=self.next_queue,
            )
            thread = threading.Thread(target=worker_func, daemon=True)
            thread.start()
            self.threads.append(thread)

    def stop(self):
        """Stop worker threads by sending sentinel and joining them."""
        for _ in self.threads:
            self.queue.put(None)
        for thread in self.threads:
            while thread.is_alive():
                thread.join(timeout=0.1)
        # self.pbar.close() if self.pbar is not None else None

    def force_stop(self):
        for thread in self.threads:
            thread.join(timeout=0)
        # self.pbar.close() if self.pbar is not None else None


class WorkerManager:
    """Manages multiple Worker instances."""

    def __init__(self):
        self.workers: List[Worker] = []

    def add_worker(
        self,
        queue: Queue,
        process_func: Callable[[Dict], None],
        num_threads: int,
        running_event: threading.Event,
        pbar: tqdm = None,
        next_queue: Optional[Queue] = None,
    ):
        """Add a new worker to the manager."""
        worker = Worker(
            queue, process_func, num_threads, running_event, pbar, next_queue=next_queue
        )
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

        self.parser = TwitterCellParser()
        self.twitter_api = TwitterAPI(proxies=self.proxies, endpoint=self.endpoint)

        self.worker_manager = WorkerManager()
        self.media_data_queue = Queue()
        self.media_desc_queue = Queue()
        self.translate_queue = Queue()
        self.keyword_queue = Queue()
        self.conversation_queue = Queue()

        self.media_desc_cache = {}
        self.pbars: List[tqdm] = []

        self._running = threading.Event()
        self._running.set()
        # clean_all_uploaded_files()

    def _regist_pbar(self, desc: str) -> tqdm:
        pbar = tqdm(desc=desc, position=len(self.pbars))
        self.pbars.append(pbar)
        return pbar

    def _start_workers(self):
        """Initialize and start all worker threads."""

        self.worker_manager.add_worker(
            queue=self.conversation_queue,
            process_func=self._add_reply,
            num_threads=20,
            pbar=self._regist_pbar("Get full reply"),
            running_event=self._running,
            next_queue=self.media_data_queue,
        )

        # Start media download workers
        self.worker_manager.add_worker(
            queue=self.media_data_queue,
            process_func=self._download_media,
            num_threads=20,
            pbar=self._regist_pbar("Download media"),
            running_event=self._running,
            next_queue=self.media_desc_queue,
        )

        # Start media description workers
        self.worker_manager.add_worker(
            queue=self.media_desc_queue,
            process_func=self._describe_media,
            num_threads=20,
            pbar=self._regist_pbar("Describe media"),
            running_event=self._running,
            next_queue=self.translate_queue,
        )

        # Start translation workers
        self.worker_manager.add_worker(
            queue=self.translate_queue,
            process_func=self._translate_content,
            num_threads=1,
            pbar=self._regist_pbar("Translate content"),
            running_event=self._running,
            next_queue=self.keyword_queue,
        )

        # Start keywords workers
        # self.worker_manager.add_worker(
        #     queue=self.keyword_queue,
        #     process_func=self._add_keywords,
        #     num_threads=20,
        #     pbar=self._regist_pbar("Add keywords"),
        #     running_event=self._running,
        # )

        # Start all workers
        self.worker_manager.start_all()

    def _add_keywords(self, task: Dict):
        if task.get("keywords"):
            return
        main_content = get(task, "content.text") or ""
        quote_content = get(task, "quote.content.text") or ""
        main_media_desces = [
            get(desc, "description") or "" for desc in get(task, "media") or []
        ] or ""
        quote_media_desces = [
            get(desc, "description") or "" for desc in get(task, "quote.media") or []
        ] or ""

        if main_content or quote_content or main_media_desces or quote_media_desces:
            kp = KeywordProcesser()
            try:
                result = kp.get_keywords(
                    f"{main_content}\n{quote_content}",
                    f"{main_media_desces}\n{quote_media_desces}",
                ).split(",")
                task["keywords"] = [k.strip().strip('"').strip("'") for k in result]
            except Exception:
                pass

    def _add_reply(self, task: Dict):
        if "replies" in task:
            return
        api = TwitterAPI(use_pool=True)
        task["replies"] = api._get_reply(task["rest_id"]).unwrap()
        rm_mention(task)

    def _download_media(self, task: Dict):
        """Download media associated with a tweet."""
        save_folder = self.save_path / self.data_folder / "media"
        thumb_folder = save_folder / "thumb"
        avatar_folder = save_folder / "avatar"

        def download_avatar(author_info):
            """Download avatar for the author."""
            if not get(author_info, "avatar.path"):
                author_info["avatar"]["path"] = download(
                    get(author_info, "avatar.url"), avatar_folder
                )

        def download_media_items(medias, save_folder, thumb_folder):
            """Download media items and their thumbnails."""
            for media in medias:
                if not media.get("path"):
                    media["path"] = download(media.get("url"), save_folder)
                if (
                    media.get("thumb")
                    and not media.get("thumb_path")
                    and media.get("path") != "media unavailable"
                ):
                    media["thumb_path"] = download(media.get("thumb"), thumb_folder)

        def download_tweet_media(task: Dict[str, Union[Dict, List[Dict]]]):
            # Download avatar for the main author
            author_info = task.get("author")
            download_avatar(author_info)

            # Download main media items
            if medias := task.get("media"):
                download_media_items(medias, save_folder, thumb_folder)

            # Handle quoted tweet
            if (quote := task.get("quote")) and quote.get(
                "rest_id"
            ) != "tweet_unavailable":
                quote_author_info = quote.get("author")
                download_avatar(quote_author_info)

                if quote_medias := quote.get("media"):
                    download_media_items(quote_medias, save_folder, thumb_folder)

        download_tweet_media(task)
        if replies := task.get("replies"):
            for reply in replies:
                if conversation := reply.get("conversation"):
                    [download_tweet_media(item) for item in conversation]

    def _describe_media(self, task: Dict):
        """Describe media associated with a tweet."""

        def process_medias(medias: List[Dict]):
            for media in medias:
                if not media.get("description") and (
                    media.get("duration_millis") <= 5 * 60 * 1000
                    if media.get("type") == "video"
                    else True
                ):
                    if (path := media.get("path")) != "media unavailable":
                        if path in self.media_desc_cache:
                            media["description"] = self.media_desc_cache[path]
                        else:
                            processor = MediaProcessor()
                            if res := processor.describe(path):
                                media["description"] = res.unwrap()
                            else:
                                media["description"] = "failed/gemini"

        # 处理主任务的媒体
        if medias := task.get("media"):
            process_medias(medias)

        # 处理引用任务的媒体
        if quote := task.get("quote"):
            if medias := quote.get("media"):
                process_medias(medias)

    def _translate_content(self, task: Dict):
        """Translate the content of a tweet."""

        def translate_text(text: str, context: str, lang: str):
            translator = Translator(source_lang=lang)
            return translator.translate(text, context).value_or(None)

        def handle_tweet(tweet: Dict, extra_context: str = ""):
            """
            处理单条推文的内容和引用内容（quote），
            如果还没有translation字段，则进行翻译并赋值。
            """
            for prefix in ("content", "quote.content"):
                text = get(tweet, f"{prefix}.text") or ""
                if text and not get(tweet, f"{prefix}.translation"):
                    # 对应 media 或 quote.media
                    media_key = prefix.replace("content", "media")
                    media_desc = str(
                        [
                            get(m, "description") or ""
                            for m in get(tweet, media_key) or []
                        ]
                        or ""
                    )
                    lang = get(tweet, f"{prefix}.lang")

                    translation = translate_text(text, media_desc + extra_context, lang)
                    get(tweet, prefix)["translation"] = translation

        # 构建主推文及其引用的上下文
        main_text = get(task, "content.text") or ""
        quote_text = get(task, "quote.content.text") or ""
        main_media = str(
            [get(m, "description") or "" for m in get(task, "media") or []] or ""
        )
        quote_media = str(
            [get(m, "description") or "" for m in get(task, "quote.media") or []] or ""
        )
        main_context = (
            f"<main_tweet>{main_text}{main_media}{quote_text}{quote_media}</main_tweet>"
        )

        # 先翻译主推文
        handle_tweet(task)

        # 如果有评论（replies），遍历其中的对话
        if replies := get(task, "replies"):
            for reply in replies:
                if conversation := get(reply, "conversation"):
                    for i, item in enumerate(conversation):
                        # 取该条推文（item）之前的所有对话内容，作为历史上下文
                        history_texts = [
                            get(c, "content.text") or "" for c in conversation[:i]
                        ] or []
                        history_context = f"<conversation_history>{history_texts}</conversation_history>"
                        handle_tweet(item, main_context + history_context)

    def scrape(self, url: str) -> List[Dict]:
        """Scrape tweets from the given URL.

        Args:
            url: Twitter timeline URL to scrape

        Returns:
            List of dictionaries containing tweet data
        """
        # WARNING: url method will not be used
        parsed_url = urlsplit(url)
        self.data_folder = (parsed_url.netloc + parsed_url.path).replace("/", ".")
        (self.save_path / self.data_folder).mkdir(exist_ok=True)
        saved_data = self._saved_data(self.data_folder)
        saved_ids = [d["rest_id"] for d in saved_data]
        next_queue = self.conversation_queue
        pbar = self._regist_pbar("Get likes")

        try:
            with WorkerContext() as ctx:
                self._start_workers()

                bottom_cursor = ""
                match_count = 0
                while ctx._running.is_set():
                    if match_count > 10:
                        break
                    data = self.twitter_api._likes_chunk(bottom_cursor).unwrap()
                    bottom_cursor = get(data, "cursor_bottom")
                    if not get(data, "tweets"):
                        break
                    tweets_chunk = get(data, "tweets")
                    for entry in tweets_chunk:
                        if entry.get("rest_id") in saved_ids:
                            match_count += 1
                            continue
                        pbar.update(1)
                        next_queue.put(entry)
                        self.tweets.append(entry)
            for data in saved_data:
                pbar.update(1)
                next_queue.put(data)

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
                "item": self.twitter_api._get_self_name() + ".Likes",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            },
            "results": [tweet for tweet in tweets if tweet.get("rest_id") != "ad"],
        }
        full_data = remove_none_values(full_data).unwrap()
        self._save_data_block_interrupt(
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

    def _save_data_block_interrupt(self, folder: str, data: dict):
        """写入文件时先屏蔽KeyboardInterrupt，避免中途被打断写坏文件。"""
        final_path = self.save_path / folder / "scraped_data.json"

        # 1. 记录原来的信号处理器
        original_handler = signal.getsignal(signal.SIGINT)

        # 2. 替换成一个空的处理器，先忽略 Ctrl + C
        signal.signal(signal.SIGINT, lambda signum, frame: None)

        try:
            with open(final_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.flush()
                # 根据需要可加上 fsync

        finally:
            # 3. 恢复原来的处理器
            signal.signal(signal.SIGINT, original_handler)

    def close(self):
        """Gracefully close the scraper, stopping all workers and closing browsers."""
        try:
            self.worker_manager.stop_all()
            [pbar.close() for pbar in self.pbars]
        except KeyboardInterrupt:
            self.force_close()

    def force_close(self):
        """Forcefully close the scraper, stopping all workers immediately."""
        self._running.clear()
        self.worker_manager.force_stop_all()
        # self.browser_manager.close_all_browsers()
        [pbar.close() for pbar in self.pbars]
