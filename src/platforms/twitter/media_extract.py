from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential
from yt_dlp import YoutubeDL


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=15))
def process_single_media(media_info: Dict[str, Any]) -> Dict[str, Any]:
    urls = [item.get("url") for item in media_info.get("requested_formats", [])]
    if not urls and media_info.get("url"):
        urls = [media_info["url"]]

    return {
        "id": media_info.get("id"),
        "ext": media_info.get("ext"),
        "format_id": media_info.get("format_id"),
        "resolution": media_info.get("resolution"),
        "dynamic_range": media_info.get("dynamic_range"),
        "aspect_ratio": media_info.get("aspect_ratio"),
        "duration_string": media_info.get("duration_string"),
        "urls": urls,
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

    def get_tweet_media_info(self, tweet_id: str) -> Dict[str, Any]:
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

    def process_entries(self, entries: List[Dict], quoted_ids: List[str]) -> List[Dict]:
        """处理媒体条目列表,过滤掉引用推文中的媒体。

        Args:
            entries: 包含媒体信息的字典列表。
            quoted_ids: 需要被过滤掉的引用推文ID列表。

        Returns:
            处理后的媒体信息字典列表,每个字典包含id、格式、分辨率等信息。
        """
        filtered_entries = [
            entry for entry in entries if entry.get("id") not in quoted_ids
        ]
        return [process_single_media(entry) for entry in filtered_entries]

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
        if not (videos := item.get("videos", False)) and not isinstance(videos, bool):
            return item

        tweet_id = item["id"]
        quote = item.get("quote")

        try:
            videos_info = self.get_tweet_media_info(tweet_id)

            if not videos_info.get("entries"):
                item["videos"] = process_single_media(videos_info)
                return item

            quoted_ids = []
            if quote:
                try:
                    quote_media = self.get_tweet_media_info(quote.get("id"))
                    quoted_ids = (
                        [quote_media.get("id")]
                        if not quote_media.get("entries")
                        else [
                            entry.get("id") for entry in quote_media.get("entries", [])
                        ]
                    )
                except Exception:
                    pass
            videos_info = self.process_entries(
                videos_info.get("entries", []), quoted_ids
            )
            item["videos"] = videos_info
            return item

        except Exception as e:
            print(f"处理推文 {tweet_id} 时出错: {e}")
            return item
