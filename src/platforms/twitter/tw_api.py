import json
import logging
import os
import random
import threading
import time
import traceback
from functools import reduce
from typing import Any, Dict, List, Union
from urllib.parse import urlparse
import html

import httpx
from fake_useragent import UserAgent
from tenacity import (
    RetryCallState,
    retry,
    stop_after_attempt,
)

from ..utils import get_cookie_value, read_netscape_cookies

# 禁用 httpx 的日志输出
logging.getLogger("httpx").setLevel(logging.CRITICAL)

AUTH_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"


UA = UserAgent()


def print_error_stack(retry_state: RetryCallState):
    """在最终失败时打印堆栈"""
    print("Maximum retry attempts reached. Printing stack trace...")
    exc = retry_state.outcome.exception()  # 获取异常对象
    if exc:
        traceback.print_exception(type(exc), exc, exc.__traceback__)


def reset_guest_token(retry_state: RetryCallState):
    """在重试前重置 guest_token"""
    instance: TwitterAPI = retry_state.args[0]  # 获取类实例 (self)
    instance._guest_token = None


class TwitterAPI:
    def __init__(self, proxies: List[Dict[str, str]] = [None], endpoint: str = None):
        self.proxies = proxies
        self.guest_token_url = "https://api.twitter.com/1.1/guest/activate.json"
        self.guest_tweet_detail_url = (
            "https://x.com/i/api/graphql/0hWvDhmW8YQ-S_ib3azIrw/TweetResultByRestId"
        )

        self.auth_tweet_detail_url = (
            "https://x.com/i/api/graphql/B9_KmbkLhXt6jRwGjJrweg/TweetDetail"
        )
        self._guest_token = None
        self._last_proxies = []
        self._last_proxies_lock = threading.Lock()
        self.endpoint = endpoint

        # print(f"{self.proxies=}, {self.endpoint=}")

    def _choose_proxy(self):
        return random.choice(self.proxies) or None

    def _get_guest_token(self) -> str:
        """Get a guest token either from custom endpoint or Twitter's API."""
        if self._guest_token is not None:
            return self._guest_token

        if self.endpoint:
            self._guest_token = self._get_token_from_endpoint()
        else:
            self._guest_token = self._get_token_direct()

        return self._guest_token

    def _get_token_from_endpoint(self) -> str:
        """Get guest token from custom endpoint with infinite retries."""
        while True:
            try:
                response = httpx.post(self.endpoint)
                response.raise_for_status()
                return response.json()["guest_token"]
            except Exception:
                time.sleep(60)

    def _get_token_direct(self, max_retries: int = 3) -> str:
        """Get guest token from Twitter API with limited retries."""
        last_error = None
        retries = max_retries

        while retries > 0:
            try:
                with httpx.Client() as client:
                    response = client.post(
                        self.guest_token_url,
                        headers={"authorization": f"Bearer {AUTH_TOKEN}"},
                    )
                    response.raise_for_status()
                    return response.json()["guest_token"]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    time.sleep(60)
                    continue
                last_error = e
            except Exception as e:
                last_error = e
                time.sleep(3)
            retries -= 1

        raise last_error or Exception("Failed to get guest token from Twitter API")

    def _get_guest_headers(self) -> Dict[str, str]:
        """获取访客请求头"""
        return {
            "authorization": f"Bearer {AUTH_TOKEN}",
            "x-guest-token": self._get_guest_token(),
        }

    def _get_auth_headers(self, cookies: list) -> Dict[str, str]:
        """获取认证请求头"""
        return {
            "authorization": f"Bearer {AUTH_TOKEN}",
            "x-csrf-token": get_cookie_value(cookies, "ct0"),
            "cookie": ";".join(
                [
                    f"kdt={get_cookie_value(cookies, 'kdt')}",
                    f"twid={get_cookie_value(cookies, 'twid')}",
                    f"ct0={get_cookie_value(cookies, 'ct0')}",
                    f"auth_token={get_cookie_value(cookies, 'auth_token')}",
                ]
            ),
        }

    def _get_guest_params(self, tweet_id: str) -> Dict[str, str]:
        """获取访客请求参数"""
        return {
            "variables": json.dumps(
                {
                    "tweetId": tweet_id,
                    "referrer": "home",
                    "with_rux_injections": False,
                    "includePromotedContent": False,
                    "withCommunity": False,
                    "withQuickPromoteEligibilityTweetFields": False,
                    "withBirdwatchNotes": False,
                    "withVoice": False,
                    "withV2Timeline": False,
                }
            ),
            "features": json.dumps(
                {
                    "rweb_lists_timeline_redesign_enabled": True,
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": True,
                    "creator_subscriptions_tweet_preview_api_enabled": True,
                    "responsive_web_graphql_timeline_navigation_enabled": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "tweetypie_unmention_optimization_enabled": True,
                    "responsive_web_edit_tweet_api_enabled": True,
                    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                    "view_counts_everywhere_api_enabled": True,
                    "longform_notetweets_consumption_enabled": True,
                    "responsive_web_twitter_article_tweet_consumption_enabled": False,
                    "tweet_awards_web_tipping_enabled": False,
                    "freedom_of_speech_not_reach_fetch_enabled": True,
                    "standardized_nudges_misinfo": True,
                    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                    "longform_notetweets_rich_text_read_enabled": True,
                    "longform_notetweets_inline_media_enabled": True,
                    "responsive_web_media_download_video_enabled": False,
                    "responsive_web_enhance_cards_enabled": False,
                }
            ),
        }

    def _get_auth_params(self, tweet_id: str) -> Dict[str, str]:
        """获取认证请求参数"""
        return {
            "variables": json.dumps(
                {
                    "focalTweetId": tweet_id,
                    "referrer": "tweet",
                    "with_rux_injections": False,
                    "includePromotedContent": False,
                    "withCommunity": True,
                    "withQuickPromoteEligibilityTweetFields": True,
                    "withBirdwatchNotes": True,
                    "withVoice": True,
                    "withV2Timeline": True,
                }
            ),
            "features": json.dumps(
                {
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": True,
                    "creator_subscriptions_tweet_preview_api_enabled": True,
                    "responsive_web_graphql_timeline_navigation_enabled": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "c9s_tweet_anatomy_moderator_badge_enabled": True,
                    "tweetypie_unmention_optimization_enabled": True,
                    "responsive_web_edit_tweet_api_enabled": True,
                    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                    "view_counts_everywhere_api_enabled": True,
                    "longform_notetweets_consumption_enabled": True,
                    "responsive_web_twitter_article_tweet_consumption_enabled": True,
                    "tweet_awards_web_tipping_enabled": False,
                    "freedom_of_speech_not_reach_fetch_enabled": True,
                    "standardized_nudges_misinfo": True,
                    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                    "rweb_video_timestamps_enabled": True,
                    "longform_notetweets_rich_text_read_enabled": True,
                    "longform_notetweets_inline_media_enabled": True,
                    "responsive_web_media_download_video_enabled": False,
                    "responsive_web_enhance_cards_enabled": False,
                }
            ),
        }

    @retry(
        stop=stop_after_attempt(3),
        before=reset_guest_token,
        retry_error_callback=print_error_stack,
    )
    # @snoop
    def get_tweet_details(self, tweet_id: str) -> Dict[str, Any]:
        """获取推文详情"""
        # 首先尝试访客访问
        headers = self._get_guest_headers()
        params = self._get_guest_params(tweet_id)

        with httpx.Client(proxy=self._choose_proxy()) as client:
            response = client.get(
                self.guest_tweet_detail_url,
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            response_data = response.json()

        # 如果需要登录，使用认证访问
        if get(response_data, "data.tweetResult.result.reason") == "NsfwLoggedOut":
            cookies = read_netscape_cookies("config/cookies.txt")
            if not cookies:
                raise ValueError("Authentication required but no cookies available")

            headers = self._get_auth_headers(cookies)
            params = self._get_auth_params(tweet_id)

            while True:
                try:
                    with httpx.Client(proxy=self._choose_proxy()) as client:
                        response = client.get(
                            self.auth_tweet_detail_url,
                            headers=headers,
                            params=params,
                        )
                        response.raise_for_status()
                        response_data = response.json()
                        break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        time.sleep(60)
                    continue
                except httpx.ReadTimeout:
                    continue
                except Exception:
                    continue

            result = get(
                response_data,
                "data.threaded_conversation_with_injections_v2.instructions.0.entries.0.content.itemContent.tweet_results.result.tweet",
            ) or get(
                response_data,
                "data.threaded_conversation_with_injections_v2.instructions.0.entries.0.content.itemContent.tweet_results.result",
            )
            extract_info = self._filter(result)
        elif (
            get(response_data, "data.tweetResult.result.__typename")
            == "TweetUnavailable"
        ):
            extract_info = {
                "type": "unavailable",
                "reason": get(response_data, "data.tweetResult.result.reason"),
            }
        elif get(response_data, "data.tweetResult") == {}:
            extract_info = {
                "type": "None",
                "reason": "Empty data",
            }
        else:
            result = get(response_data, "data.tweetResult.result.tweet") or get(
                response_data, "data.tweetResult.result"
            )
            try:
                extract_info = self._filter(result)
            except Exception as e:
                with open(f"error_{tweet_id}.json", "w", encoding="utf-8") as f:
                    json.dump(response_data, f, ensure_ascii=False, indent=4)
                raise e

        # with open(f"{tweet_id}.json", "w", encoding="utf-8") as f:
        #     json.dump(response_data, f, ensure_ascii=False, indent=4)

        return extract_info

    def _best_quality_image(self, url: str) -> str:
        parsed = urlparse(url)
        basename = os.path.basename(parsed.path)
        # Get the path component and extract the asset name
        asset_name = basename.split(".")[0]
        # Get the file extension
        extension = basename.split(".")[-1]
        return f"https://pbs.twimg.com/media/{asset_name}?format={extension}&name=4096x4096"

    def _format_content(self, data: Dict[str, Any]):
        # Get the base text content
        text_content = get(data, "note_tweet.note_tweet_results.result.text") or get(
            data, "legacy.full_text"
        )

        # Collect all URL replacements in a single map
        url_replacements = {
            # quoted status permalink
            ("legacy.quoted_status_permalink.url", ""): "",
            # Add media URLs
            ("legacy.entities.media", "url"): "",
            # Add regular URLs
            ("legacy.entities.urls", "url"): "expanded_url",
            # Add note tweet URLs
            (
                "note_tweet.note_tweet_results.result.entity_set.urls",
                "url",
            ): "expanded_url",
        }

        # Collect all URLs and their replacements
        replacements = []
        expanded_urls = []

        for (path, url_key), expanded_key in url_replacements.items():
            if urls := get(data, path):
                # Handle single URL case (like quoted_status_permalink)
                if isinstance(urls, str):
                    replacements.append({"url": urls, "expanded_url": ""})
                # Handle list of URLs
                else:
                    for url in urls:
                        url_val = url.get(url_key) if url_key else url
                        expanded_val = url.get(expanded_key) if expanded_key else ""
                        replacements.append(
                            {"url": url_val, "expanded_url": expanded_val}
                        )
                        if expanded_val:  # Collect non-empty expanded URLs
                            expanded_urls.append(expanded_val)

        # Single reduce operation to replace all URLs
        content = reduce(
            lambda text, url_dict: text.replace(
                url_dict["url"], url_dict["expanded_url"]
            ),
            replacements,
            text_content,
        )
        return {
            "text": html.unescape(content).strip(),
            "expanded_urls": expanded_urls,
        }

    def _filter(self, data: Union[Dict[str, Any], List[Any]]):
        media = (
            [
                {
                    "type": t,
                    "url": (
                        max(
                            get(e, "video_info.variants") or [],
                            key=lambda x: int(x.get("bitrate", 0) or 0),
                        ).get("url")
                    ),
                    "aspect_ratio": get(e, "video_info.aspect_ratio"),
                    "thumb": get(e, "media_url_https"),
                }
                if (t := get(e, "type")) in ["video", "animated_gif"]
                else {
                    "type": t,
                    "url": self._best_quality_image(get(e, "media_url_https")),
                }
                for e in m
            ]
            if (m := get(data, "legacy.entities.media"))
            else None
        )
        info = {
            "rest_id": get(data, "rest_id"),
            "name": get(data, "core.user_results.result.legacy.name"),
            "screen_name": get(data, "core.user_results.result.legacy.screen_name"),
            "created_at": get(data, "legacy.created_at"),
            "content": self._format_content(data),
            "lang": get(data, "legacy.lang"),
            "media": media,
            "card": {
                "title": next(
                    (
                        get(b, "value.string_value")
                        for b in get(c, "legacy.binding_values")
                        if b.get("key") == "title"
                    ),
                    None,
                ),
                "url": get(c, "rest_id"),
            }
            if (c := get(data, "card"))
            else None,
            "quote": {
                "rest_id": get(d, "rest_id"),
                "name": get(d, "core.user_results.result.legacy.name"),
                "screen_name": get(d, "core.user_results.result.legacy.screen_name"),
                "created_at": get(d, "legacy.created_at"),
                "content": self._format_content(d),
                "lang": get(d, "legacy.lang"),
                "media": (
                    [
                        {
                            "type": t,
                            "url": (
                                max(
                                    get(e, "video_info.variants") or [],
                                    key=lambda x: int(x.get("bitrate", 0) or 0),
                                ).get("url")
                            ),
                            "aspect_ratio": get(e, "video_info.aspect_ratio"),
                            "thumb": get(e, "media_url_https"),
                        }
                        if (t := get(e, "type")) in ["video", "animated_gif"]
                        else {
                            "type": t,
                            "url": self._best_quality_image(get(e, "media_url_https")),
                        }
                        for e in m
                    ]
                    if (m := get(d, "legacy.entities.media"))
                    else None
                ),
            }
            if (
                d := (
                    get(data, "quoted_status_result.result.tweet")
                    or get(data, "quoted_status_result.result")
                )
            )
            else None,
        }

        return info


def get(data, path: str):
    """从嵌套数据中根据路径获取字段值"""
    keys = path.split(".")
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list):
            try:
                index = int(key)
                data = data[index] if abs(index) < len(data) else None
            except ValueError:
                return None
        else:
            return None
    return data
