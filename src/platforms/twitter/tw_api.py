import base64
import html
import json
import logging
import os
import random
import shutil
import sys
import threading
import time
import traceback
from functools import reduce
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import httpx
import snoop
from fake_useragent import UserAgent
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings
from returns.maybe import Maybe, Nothing, Some
from returns.result import Failure, Result, Success
from tenacity import (
    RetryCallState,
    retry,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm

from src.service.base import KeyManager
from src.service.helper import get

from ..utils import get_cookie_value, read_netscape_cookies

# 禁用 httpx 的日志输出
logging.getLogger("httpx").setLevel(logging.CRITICAL)

AUTH_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"


UA = UserAgent()


def print_error_stack(retry_state: RetryCallState):
    """在最终失败时打印堆栈"""
    print(
        f"Maximum retry attempts reached for {retry_state.args[1]}. Printing stack trace..."
    )
    exc = retry_state.outcome.exception()  # 获取异常对象
    if exc:
        traceback.print_exception(type(exc), exc, exc.__traceback__)


def reset_guest_token(retry_state: RetryCallState):
    """在重试前重置 guest_token"""
    instance: TwitterAPI = retry_state.args[0]  # 获取类实例 (self)
    instance._guest_token = None


class XSettings(BaseSettings):
    xpool: Optional[List[str]] = Field(default=[], validate_default=True)
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        extra_sources=[],
    )

    @field_validator("xpool", mode="before")
    def validate_xpool(cls, v):
        if v is None or not v:
            return []
        if isinstance(v, str):
            return v.split(",")
        return v


class TwitterAPI:
    def __init__(
        self,
        proxies: List[Dict[str, str]] = [None],
        endpoint: str = None,
        cookie_path: str = "config/cookies.txt",
        use_pool: bool = False,
    ):
        self.settings = XSettings()
        self.key_manager = KeyManager(rpm=15, cooldown_time=660)
        self.proxies = proxies
        self.guest_token_url = "https://api.twitter.com/1.1/guest/activate.json"
        self.guest_tweet_detail_url = (
            "https://x.com/i/api/graphql/0hWvDhmW8YQ-S_ib3azIrw/TweetResultByRestId"
        )

        self.auth_tweet_detail_url = (
            "https://x.com/i/api/graphql/B9_KmbkLhXt6jRwGjJrweg/TweetDetail"
        )
        self.auth_likes_url = "https://x.com/i/api/graphql/kgZtsNyE46T3JaEf2nF9vw/Likes"
        self.auth_user_info_url = (
            "https://x.com/i/api/graphql/i_0UQ54YrCyqLUvgGzXygA/UserByRestId"
        )
        self._guest_token = None
        self._last_proxies = []
        self.failed_cookies = []
        self._last_proxies_lock = threading.Lock()
        self.endpoint = endpoint
        self.cookie = read_netscape_cookies(cookie_path)
        self.use_pool = use_pool
        self.cookie_pool = self._read_cookie_pool()

        self.detail_call_count = 0
        self.max_call_count = self._random_limit()

        if self.use_pool:
            self.cookie = next(self.cookie_pool)

    def _random_limit(self):
        return random.randint(50, 150)

    def _choose_proxy(self):
        return random.choice(self.proxies) or None

    def parse_cookie_string(self, cookie_str) -> Maybe[Dict[str, Any]]:
        cookie_dict = {}
        pairs = cookie_str.split(";")
        for pair in pairs:
            pair = pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                if value in self.failed_cookies:
                    return Nothing
                cookie_dict[key.strip()] = value.strip()
        return Some(cookie_dict)

    def _read_cookie_pool(self):
        if not self.use_pool:
            return None

        pool = []
        for encoded_data in self.settings.xpool:
            decoded_data = base64.b64decode(encoded_data).decode("utf-8")
            self.parse_cookie_string(decoded_data).bind_optional(pool.append)

        return iter(pool)

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

    def _get_tweet_guest_params(self, tweet_id: str) -> Dict[str, str]:
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

    def _get_tweet_auth_params(self, tweet_id: str, cursor: str = "") -> Dict[str, str]:
        """获取认证请求参数"""
        return {
            "variables": json.dumps(
                {
                    **{
                        "focalTweetId": tweet_id,
                        "referrer": "me",
                        "with_rux_injections": False,
                        "includePromotedContent": False,
                        "withCommunity": True,
                        "withQuickPromoteEligibilityTweetFields": True,
                        "withBirdwatchNotes": True,
                        "withVoice": True,
                        "withV2Timeline": True,
                    },
                    **({"cursor": cursor} if cursor else {}),
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

    def _get_user_info_params(self, user_id: str) -> Dict[str, str]:
        return {
            "variables": json.dumps(
                {
                    "userId": user_id,
                    "withSafetyModeUserFields": True,
                }
            ),
            "features": json.dumps(
                {
                    "hidden_profile_likes_enabled": False,
                    "hidden_profile_subscriptions_enabled": False,
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": True,
                    "subscriptions_verification_info_verified_since_enabled": True,
                    "highlights_tweets_tab_ui_enabled": True,
                    "creator_subscriptions_tweet_preview_api_enabled": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "responsive_web_graphql_timeline_navigation_enabled": True,
                }
            ),
        }

    def _get_likes_auth_params(self, cursor: str = "") -> Dict[str, str]:
        return {
            "variables": json.dumps(
                {
                    **{
                        "userId": get_cookie_value(self.cookie, "twid").replace(
                            "u%3D", ""
                        ),
                        "count": 80,
                        "includePromotedContent": False,
                        "withClientEventToken": False,
                        "withBirdwatchNotes": False,
                        "withVoice": False,
                        "withV2Timeline": False,
                    },
                    **({"cursor": cursor} if cursor else {}),
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

    def _self_info(self) -> Result[Dict[str, Any], Exception]:
        headers = self._get_auth_headers(self.cookie)
        params = self._get_user_info_params(
            get_cookie_value(self.cookie, "twid").replace("u%3D", "")
        )
        with httpx.Client(proxy=self._choose_proxy()) as client:
            response = client.get(
                self.auth_user_info_url,
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            return Success(response.json())

    def _get_self_name(self) -> str:
        data = self._self_info().unwrap()
        return get(data, "data.user.result.legacy.name")

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(max=60),
        before=reset_guest_token,
        retry_error_callback=print_error_stack,
    )
    def _likes(self, cursor: str = "") -> Result[Dict[str, Any], Exception]:
        headers = self._get_auth_headers(self.cookie)
        params = self._get_likes_auth_params(cursor)
        with httpx.Client(proxy=self._choose_proxy()) as client:
            response = client.get(
                self.auth_likes_url,
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            return Success(response.json())

    def _likes_chunk(self, cursor: str = "") -> Result[Dict[str, Any], Exception]:
        data = self._likes(cursor).unwrap()
        entries = get(data, "data.user.result.timeline.timeline.instructions.0.entries")
        cursor_bottom = None
        tweets = []
        for entry in entries:
            if "cursor-bottom" in entry["entryId"]:
                cursor_bottom = get(entry, "content.value")
            else:
                tweet = get(
                    entry, "content.itemContent.tweet_results.result.tweet"
                ) or get(entry, "content.itemContent.tweet_results.result")
                if (
                    tweet
                    and get(tweet, "__typename") not in ["TweetTombstone"]
                    and "Advertisers" not in tweet.get("source")
                ):
                    tweets.append(self._filter(tweet))
        return Success({"cursor_bottom": cursor_bottom, "tweets": tweets})

    def get_all_likes(self) -> Result[Dict[str, Any], Exception]:
        if os.path.exists("cache/cache_likes.json"):
            with open("cache/cache_likes.json", "r", encoding="utf-8") as f:
                all_datas = json.load(f)
            bottom_cursor = get(all_datas[-1], "cursor_bottom")
            shutil.rmtree("cache", ignore_errors=True)
        else:
            all_datas = []
            bottom_cursor = ""
        pbar = tqdm(desc="Get all likes")
        while True:
            try:
                data = self._likes_chunk(bottom_cursor).unwrap()
                bottom_cursor = get(data, "cursor_bottom")
                if not get(data, "tweets"):
                    break
                pbar.update(len(get(data, "tweets")))
                all_datas.append(data)
            except Exception as e:
                os.mkdir("cache", exist_ok=True)
                with open("cache/cache_likes.json", "w", encoding="utf-8") as f:
                    json.dump(all_datas, f, ensure_ascii=False, indent=4)
                return Failure(e)
        return Success([tweet for data in all_datas for tweet in get(data, "tweets")])

    def _reply_chunk(
        self, id: str, cursor: str = ""
    ) -> Result[Dict[str, Any], Exception]:
        def tweet(data) -> Maybe[Dict[str, Any]]:
            detail: Dict[str, Any] = get(
                data,
                "item.itemContent.tweet_results.result.tweet",
            ) or get(data, "item.itemContent.tweet_results.result")
            if not detail:
                return Nothing
            if get(detail, "__typename") in ["TweetTombstone"]:
                return Nothing
            if "Advertisers" in detail.get("source", ""):
                return Nothing

            return Some(detail)

        data = self._get_authenticated_tweet_details(id, cursor).unwrap()
        entries = get(
            data, "data.threaded_conversation_with_injections_v2.instructions.0.entries"
        )
        cursor_bottom = None
        conversation_threads = []

        if not entries:
            return Success(
                {
                    "cursor_bottom": cursor_bottom,
                    "conversation_threads": conversation_threads,
                }
            )

        for entry in entries:
            if "conversationthread" in entry["entryId"]:
                conversation = []
                for reply in get(entry, "content.items"):
                    if "ShowMore" == get(reply, "item.itemContent.cursorType"):
                        showmore = get(reply, "item.itemContent.value")
                        replymore = self._get_authenticated_tweet_details(
                            id, showmore
                        ).unwrap()
                        entriesmore = get(
                            replymore,
                            "data.threaded_conversation_with_injections_v2.instructions.0.moduleItems",
                        )
                        for entrymore in entriesmore:
                            tweet(entrymore).bind_optional(self._filter).bind_optional(
                                conversation.append
                            )
                        continue
                    tweet(reply).bind_optional(self._filter).bind_optional(
                        conversation.append
                    )
                conversation_threads.append({"conversation": conversation})
            elif "Bottom" == get(entry, "content.itemContent.cursorType"):
                cursor_bottom = get(entry, "content.itemContent.value")

        return Success(
            {
                "cursor_bottom": cursor_bottom,
                "conversation_threads": conversation_threads,
            }
        )

    def _get_reply(self, id: str) -> Result[Dict[str, Any], Exception]:
        all_datas = []
        bottom_cursor = ""
        while True:
            data = self._reply_chunk(id, bottom_cursor).unwrap()
            all_datas.extend(get(data, "conversation_threads"))
            if get(data, "cursor_bottom") is None:
                break
            bottom_cursor = get(data, "cursor_bottom")

        return Success(all_datas)

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(max=60),
        before=reset_guest_token,
        retry_error_callback=print_error_stack,
    )
    def _guest_response(self, tweet_id: str) -> Result[Dict[str, Any], Exception]:
        headers = self._get_guest_headers()
        params = self._get_tweet_guest_params(tweet_id)
        with httpx.Client(proxy=self._choose_proxy(), timeout=10) as client:
            response = client.get(
                self.guest_tweet_detail_url,
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            return Success(response.json())

    @retry(
        stop=stop_after_attempt(20),
        wait=wait_exponential(min=60, max=660),
        reraise=True,
    )
    def _get_authenticated_tweet_details(
        self, tweet_id: str, cursor: str = ""
    ) -> Result[Dict[str, Any], Exception]:
        """获取认证后的推文详情"""
        if not self.cookie:
            return Failure(
                ValueError("Authentication required but no cookies available")
            )

        while True:
            with self.key_manager.context(self.settings.xpool or [self.cookie]) as key:
                try:
                    if self.use_pool:
                        decoded_data = base64.b64decode(key).decode("utf-8")
                        self.cookie = self.parse_cookie_string(decoded_data).unwrap()
                    headers = self._get_auth_headers(self.cookie)
                    params = self._get_tweet_auth_params(tweet_id, cursor)
                    with httpx.Client(proxy=self._choose_proxy(), timeout=10) as client:
                        response = client.get(
                            self.auth_tweet_detail_url,
                            headers=headers,
                            params=params,
                        )
                        response.raise_for_status()
                        res = response.json()
                    if str(get(res, "errors.0.code")) == "144":
                        return Success({})
                    if not res:
                        continue
                    if not get(res, "data"):
                        if str(get(res, "errors.0.code")) == "326":
                            if self.use_pool:
                                print("errors lock", key)
                                self.settings.xpool.remove(key)
                            else:
                                return Failure(
                                    ValueError(
                                        "You are locked out, please login X to unlock"
                                    )
                                )
                        continue
                    return Success(res)
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
                    continue
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        if self.use_pool:
                            self.key_manager.mark_key_cooldown(key)
                            continue
                        else:
                            time.sleep(660)
                            continue
                    raise e
                except Exception as e:
                    return Failure(e)

    def _check_result(
        self, response_data: Dict[str, Any]
    ) -> Result[Dict[str, Any], Exception]:
        auth_result = get(
            response_data,
            "data.threaded_conversation_with_injections_v2.instructions.0.entries.0.content.itemContent.tweet_results.result.tweet",
        ) or get(
            response_data,
            "data.threaded_conversation_with_injections_v2.instructions.0.entries.0.content.itemContent.tweet_results.result",
        )
        guest_result = get(response_data, "data.tweetResult.result.tweet") or get(
            response_data, "data.tweetResult.result"
        )
        result = guest_result or auth_result

        if not result:
            typename = get(response_data, "data.tweetResult.result.__typename")
            if typename == "TweetUnavailable":
                return Success(
                    {
                        "type": "unavailable",
                        "reason": get(response_data, "data.tweetResult.result.reason"),
                    }
                )
            elif get(response_data, "data.tweetResult") == {}:
                return Success(
                    {
                        "type": "None",
                        "reason": "Empty data",
                    }
                )
            return Failure(ValueError("Unknown response structure"))

        if "Advertisers" in result.get("source", ""):
            return Success({"rest_id": "ad"})

        return Success(result)

    def _process_tweet_details(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """处理推文详情的公共逻辑"""
        try:
            extract_info = self._filter(result)
        except Exception as e:
            if result:
                extract_info = result
            else:
                raise e
        return extract_info

    # @retry(
    #     stop=stop_after_attempt(3),
    #     before=reset_guest_token,
    #     retry_error_callback=print_error_stack,
    # )
    def get_tweet_details(self, tweet_id: str) -> Dict[str, Any]:
        """获取推文详情"""
        # 尝试访客访问
        guest_response = self._guest_response(tweet_id).bind(self._check_result)

        if isinstance(guest_response, Failure):
            raise guest_response.failure()

        response_data = guest_response.unwrap()

        # 判断推文是否需要登录才能访问
        if (
            response_data.get("type") == "unavailable"
            and response_data.get("reason") == "NsfwLoggedOut"
        ):
            auth_response = self._get_authenticated_tweet_details(tweet_id).bind(
                self._check_result
            )
            if isinstance(auth_response, Failure):
                raise auth_response.failure()
            response_data = auth_response.unwrap()

        # 处理推文详情
        return self._process_tweet_details(response_data)

    def _best_quality_image(self, url: str) -> str:
        parsed = urlparse(url)
        basename = os.path.basename(parsed.path)
        # Get the path component and extract the asset name
        asset_name = basename.split(".")[0]
        # Get the file extension
        extension = basename.split(".")[-1]
        return f"https://pbs.twimg.com/media/{asset_name}?format={extension}&name=4096x4096"

    # @snoop
    def _filter(self, data: Union[Dict[str, Any], List[Any]]) -> Dict[str, Any]:
        def remove_urls(text: str, urls: List[str]) -> str:
            """
            只移除在 text 尾部出现、并且属于 urls 列表中的 URL。
            urls 可能很多，所以这里先按长度倒序排一下，
            防止出现较短 URL 先匹配把长 URL 给拆了的情况。
            """
            # 先对要匹配的 urls 根据长度倒序排列，防止长的被短的覆盖
            urls_sorted = sorted(set(urls), key=len, reverse=True)

            # 由于可能末尾连续存在多个 URL，我们用 while 循环一直砍到不匹配为止
            while True:
                # 去掉末尾多余空格（有些末尾 URL 前面可能留有空格或换行）
                stripped_text = text.rstrip()
                if stripped_text == text:
                    # 如果没有额外空格，那就直接检查 URL
                    pass
                else:
                    # 如果发生了 rstrip，则更新 text
                    text = stripped_text

                found = False
                for url in urls_sorted:
                    if text.endswith(url):
                        # 如果末尾匹配，去掉该 URL，并把末尾再做一次 rstrip
                        text = text[: -len(url)].rstrip()
                        found = True
                        # 这里 break 是因为一次只移除一个匹配 URL，移除后再从头来
                        break
                if not found:
                    # 末尾不再匹配任何 URL 就结束
                    break

            return text

        def get_format_content(data: Dict[str, Any]):
            # 原始文本获取
            text_content: str = get(
                data, "note_tweet.note_tweet_results.result.text"
            ) or get(data, "legacy.full_text")

            # 收集所有需要处理的 URL（要替换成什么这里先不管）
            url_replacements = {
                ("legacy.quoted_status_permalink.url", ""): "",
                ("card.rest_id", ""): "",
                ("legacy.entities.media", "url"): "",
                ("legacy.entities.urls", "url"): "expanded_url",
                (
                    "note_tweet.note_tweet_results.result.entity_set.urls",
                    "url",
                ): "expanded_url",
                ("legacy.quoted_status_permalink.expanded", ""): "",
            }

            # 用来保存要在末尾检测并移除的 url
            urls_for_removal = []

            # 这个 expanded_urls 你原本是用来收集真正的 "expanded_url" 的
            expanded_urls = []
            card = parse_card(data)
            card and urls_for_removal.append(card.get("url"))
            article = parse_article(data)

            for (path, url_key), expanded_key in url_replacements.items():
                result = get(data, path)
                if not result:
                    continue
                # 如果是字符串，说明只有一个 url
                if isinstance(result, str):
                    urls_for_removal.append(result)
                else:
                    # 否则就认为是 list
                    for url_item in result:
                        url_val = url_item.get(url_key) if url_key else url_item
                        expanded_val = (
                            url_item.get(expanded_key) if expanded_key else ""
                        )

                        if expanded_val:
                            text_content = text_content.replace(url_val, expanded_val)
                            article and urls_for_removal.append(
                                article.get("id") in expanded_val and expanded_val
                            )
                            expanded_urls.append(expanded_val)
                        else:
                            urls_for_removal.append(url_val)

            content = remove_urls(text_content, urls_for_removal)

            return {
                "text": html.unescape(content).strip(),
                "expanded_urls": list(set(expanded_urls)),
            }

        def parse_media(_data):
            return (m := get(_data, "legacy.entities.media")) and (
                [
                    {
                        **{
                            "type": t,
                            "url": (
                                max(
                                    get(e, "video_info.variants") or [],
                                    key=lambda x: int(x.get("bitrate", 0) or 0),
                                    default={},
                                ).get("url")
                            ),
                            "aspect_ratio": get(e, "video_info.aspect_ratio"),
                            "thumb": get(e, "media_url_https"),
                        },
                        **(
                            {"duration_millis": get(e, "video_info.duration_millis")}
                            if t == "video"
                            else {}
                        ),
                    }
                    if (t := get(e, "type")) in ["video", "animated_gif"]
                    else {
                        "type": t,
                        "url": self._best_quality_image(get(e, "media_url_https")),
                    }
                    for e in m
                ]
            )

        def parse_article(_data):
            return (a := get(_data, "article.article_results.result")) and (
                {
                    "id": get(a, "rest_id"),
                    "title": get(a, "title"),
                    "description": get(a, "preview_text") + "...",
                    "url": "https://x.com/i/status/" + get(a, "rest_id"),
                }
            )

        def parse_card(_data):
            def get_binding_value(key):
                return next(
                    (
                        get(b, "value.string_value")
                        for b in get(card, "legacy.binding_values")
                        if b.get("key") == key
                    ),
                    None,
                )

            def get_expanded_url(card_url):
                return next(
                    (
                        get(r, "expanded_url")
                        for r in get(_data, "legacy.entities.urls")
                        if r.get("url") == card_url
                    ),
                    None,
                )

            if not (card := get(_data, "card")) or (
                "card://" in get(_data, "card.rest_id")
            ):
                return None

            title = get_binding_value("title")
            description = get_binding_value("description")
            card_url = get_binding_value("card_url")
            url = get_expanded_url(card_url)

            return {"title": title, "description": description, "url": url}

        def parse_author(_data):
            return {
                "name": get(_data, "core.user_results.result.legacy.name"),
                "screen_name": get(
                    _data, "core.user_results.result.legacy.screen_name"
                ),
                "avatar": {
                    "url": get(
                        _data, "core.user_results.result.legacy.profile_image_url_https"
                    )
                },
            }

        def parse_tweet(_data):
            return _data and {
                "rest_id": get(_data, "rest_id"),
                "author": parse_author(_data),
                "created_at": get(_data, "legacy.created_at"),
                "content": {
                    **get_format_content(_data),
                    **{"lang": get(_data, "legacy.lang")},
                },
                "media": parse_media(_data),
                "card": parse_card(_data),
                "article": parse_article(_data),
            }

        quote_data = get(data, "quoted_status_result.result.tweet") or get(
            data, "quoted_status_result.result"
        )
        quote = (
            None
            if not quote_data or quote_data.get("__typename") == "TweetTombstone"
            else quote_data
        )
        return {**parse_tweet(data), "quote": parse_tweet(quote)}
