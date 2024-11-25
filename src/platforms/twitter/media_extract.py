from typing import Any, Dict, List, Optional, Tuple
import traceback

from tenacity import retry, stop_after_attempt, wait_exponential
from yt_dlp import YoutubeDL


def process_single_media(media_info: Dict[str, Any]) -> Dict[str, Any]:
    all_formats = media_info.get("formats", [])
    http_formats = [item for item in all_formats if item.get("protocol") == "https"]

    # 获取tbr值最大的格式，如果没有tbr则默认为0
    best_format = max(
        http_formats,
        key=lambda x: float(x.get("tbr", 0)) if x.get("tbr") is not None else 0,
        default=None,
    )

    return {
        "url": best_format.get("url"),
        "ext": best_format.get("ext"),
        "resolution": best_format.get("resolution"),
        "dynamic_range": best_format.get("dynamic_range"),
        "aspect_ratio": best_format.get("aspect_ratio"),
    }


class TweetMediaExtractor:
    """从Twitter推文中提取媒体信息的工具类。

    该类提供了一系列方法用于从Twitter推文中提取和处理视频等媒体内容。
    使用yt-dlp作为底层媒体信息提取工具。
    """

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        # "cookiefile": "config/cookies.txt",
    }

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=15)
    )
    def _get_tweet_media_info(self, tweet_id: str) -> Dict[str, Any]:
        """获取指定推文ID的媒体信息。

        Args:
            tweet_id: 推文的唯一标识ID。

        Returns:
            包含媒体信息的字典,结构由yt-dlp的extract_info方法决定。

        Raises:
            Exception: 当媒体信息提取失败时抛出。
        """
        url = f"https://x.com/i/status/{tweet_id}"
        with YoutubeDL(self.ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def process_entries(
        self, entries: List[Dict], quoted_entries: List[Dict]
    ) -> Tuple[List[Dict], List[Dict]]:
        """处理媒体条目列表,返回非引用和引用的媒体。

        Args:
            entries: 包含媒体信息的字典列表。
            quoted_entries: 引用推文字典列表。

        Returns:
            返回一个元组，包含:
            - 非引用媒体的信息字典列表
            - 引用媒体的信息字典列表
            每个字典包含id、格式、分辨率等信息。
        """
        quoted_ids = [quote.get("id") for quote in quoted_entries]
        non_quoted = [entry for entry in entries if entry.get("id") not in quoted_ids]
        intersection = [entry for entry in entries if entry.get("id") in quoted_ids]

        return (
            [process_single_media(entry) for entry in non_quoted],
            [process_single_media(entry) for entry in intersection],
        )

    def extract(self, item: Dict[str, Any]) -> Optional[Dict]:
        """处理单条推文中的媒体内容。

        处理流程:
        1. 检查推文是否包含视频
        2. 获取推文的媒体信息
        3. 如果存在引用推文,获取并记录引用推文的媒体ID
        4. 过滤和处理媒体信息

        Args:
            item: 推文信息字典,必须包含id字段,可选包含videos和quote字段。

        直接修改原数据

        Raises:
            Exception: 当媒体信息提取或处理过程中发生错误时捕获并打印。
        """
        if (
            not (videos := item.get("videos", False))
            and not isinstance(videos, bool)
            or item.get("card", False)
        ):
            return item

        tweet_id = item["id"]
        quote: Dict = item.get("quote")

        try:
            videos_info = self._get_tweet_media_info(tweet_id)

            if not videos_info.get("entries"):
                item["videos"] = process_single_media(videos_info)
                return item

            quoted_entries = []
            if quote and quote.get("videos"):
                quote_media = self._get_tweet_media_info(quote.get("id"))
                quoted_entries = (
                    [quote_media]
                    if not quote_media.get("entries")
                    else [entry for entry in quote_media.get("entries", [])]
                )
            videos_info, q_videos_info = self.process_entries(
                videos_info.get("entries", []), quoted_entries
            )
            item["videos"] = videos_info
            if quote:
                item["quote"]["videos"] = q_videos_info or None
            return item

        except Exception as e:
            print(f"处理推文 {tweet_id} 时出错: {e}")
            print("详细错误信息:")
            traceback.print_exc()
            return item
