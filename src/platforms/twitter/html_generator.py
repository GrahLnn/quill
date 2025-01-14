import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union

import regex as re
from returns.result import Success, Result, Failure

from ...service.helper import get, remove_none_values
from .html_templete import FULL_HTML


def format_timestamp(timestamp: str, fmt="%Y-%m-%d %H:%M") -> str:
    """把 Twitter 原始时间转为本地时区自定义格式。"""
    if not timestamp:
        return ""
    time_format = "%a %b %d %H:%M:%S %z %Y"
    local_tz = datetime.now().astimezone().tzinfo
    parsed_time = datetime.strptime(timestamp, time_format)
    return parsed_time.astimezone(local_tz).strftime(fmt)


def format_content_with_links(content: str, replace_urls: List[str]) -> str:
    """
    将文本中的 URL 替换为 HTML 链接，先用占位符避免子串冲突，再还原。
    """
    if not content:
        return ""

    
    expanded_urls = sorted(replace_urls, key=len, reverse=True)

    placeholders = {}
    for i, url in enumerate(expanded_urls):
        placeholder = f"__URL_PLACEHOLDER_{i}__"
        placeholders[placeholder] = url
        content = content.replace(url, placeholder)
    text: str = html.escape(content)
    for placeholder, url in placeholders.items():
        link_text = os.path.basename(url) or [u for u in url.split("/") if u][-1]
        html_link = f'<a href="{url}" target="_blank" class="link">{link_text}</a>'
        text = text.replace(placeholder, html_link)

    return text


def transform_paths(tweet: Dict, output_dir: Path) -> Success[Dict]:
    """
    把推文中的本地资源路径变成相对于输出文件夹的相对路径。
    """

    def rel(path: str) -> str:
        try:
            return str(Path(path).relative_to(output_dir))
        except Exception as e:
            print(path)
            raise e

    # 转换头像路径
    if avatar_path := get(tweet, "author.avatar.path"):
        if avatar_path and avatar_path != "media unavailable":
            tweet["author"]["avatar"]["path"] = rel(avatar_path)

    # 转换媒体资源
    if get(tweet, "media"):
        for m in tweet["media"]:
            if m.get("path") != "media unavailable":
                if "path" in m:
                    m["path"] = rel(m["path"])
                if "thumb_path" in m:
                    m["thumb_path"] = rel(m["thumb_path"])

    # 转换引用推文的资源
    if get(tweet, "quote") and get(tweet, "quote.rest_id") != "tweet_unavailable":
        quote = tweet["quote"]
        if qavatar := get(quote, "author.avatar.path"):
            if qavatar and qavatar != "media unavailable":
                quote["author"]["avatar"]["path"] = rel(qavatar)

        if "media" in quote and isinstance(quote["media"], list):
            for qm in quote["media"]:
                if qm.get("path") != "media unavailable":
                    if "path" in qm:
                        qm["path"] = rel(qm["path"])
                    if "thumb_path" in qm:
                        qm["thumb_path"] = rel(qm["thumb_path"])

    return Success(tweet)


def transform_timestamp(tweet: Dict) -> Success[Dict]:
    tweet["created_at"] = format_timestamp(tweet.get("created_at"))
    return Success(tweet)


def transform_text(tweet: Dict) -> Success[Dict]:
    """
    为推文及其引用的文本增加 HTML 链接，并转义 HTML。
    """
    # 引用推文文本
    if get(tweet, "quote") and get(tweet, "quote.rest_id") != "tweet_unavailable":
        quote = tweet["quote"]
        origin_text = get(quote, "content.text") or ""
        quote["content"]["text"] = format_content_with_links(
            origin_text, get(quote, "content.expanded_urls") or []
        )
        if get(quote, "content.translation"):
            quote["content"]["translation"] = format_content_with_links(
                quote["content"]["translation"],
                get(quote, "content.expanded_urls") or [],
            )

    # 本推文文本
    if get(tweet, "content"):
        content = tweet["content"]
        content["text"] = format_content_with_links(
            get(content, "text"), get(content, "expanded_urls") or []
        )
        if content.get("translation"):
            content["translation"] = format_content_with_links(
                content["translation"], get(content, "expanded_urls") or []
            )

    return Success(tweet)


def transform_single_tweet(tweet: Dict, output_dir: Path) -> Success[Dict]:
    """
    最终针对单条 Tweet 的转换管道，在这里将所有 transform 函数串联起来。
    """
    return (
        transform_paths(tweet, output_dir)
        .bind(transform_timestamp)
        .bind(transform_text)
        .bind(remove_none_values)
    )


def at_who(text):
    """
    获取文本中的@提及信息及其位置
    :param text: 文本内容
    :return: 列表，每项包含 (用户名, [开始位置, 结束位置])
    """
    mentions = []
    for match in re.finditer(r"@(\w+)", text):
        username = match.group(0)  # 完整匹配（包含@）
        start = match.start()
        end = match.end()
        mentions.append({"name": username, "indices": [start, end]})
    return mentions


def rm_mention(tweets: List[Dict]) -> Success[List[Dict]]:
    for tw in tweets:
        mentions = [d.get("name") for d in at_who(get(tw, "content.text"))]
        mentions.append(f"@{get(tw, 'author.screen_name')}")
        if "replies" in tw:
            for reply in tw["replies"]:
                for convitem in reply.get("conversation", []):
                    mentions.append(f"@{get(convitem, 'author.screen_name')}")
                    reply_mentions = at_who(get(convitem, "content.text"))
                    mention_end = None
                    for i, men in enumerate(reply_mentions):
                        if reply_mentions[0]["indices"][0] != 0:
                            break
                        if i == 0 and men.get("name") in mentions:
                            # if i == 0:
                            mention_end = men["indices"][1]
                        elif (
                            mention_end and men["indices"][0] - mention_end == 1
                        ):  # repost user in mention but i can't identify
                            mention_end = men["indices"][1]
                        else:
                            break
                    if mention_end:
                        convitem["content"]["text"] = convitem["content"]["text"][
                            mention_end + 1 :
                        ]
    return Success(tweets)


def transform_tweets_recursive(
    tweets: List[Dict], output_dir: Path
) -> Success[List[Dict]]:
    """
    递归处理推文及其 conversation（例如回复链）。
    """
    for tw in tweets:
        # 处理主推文
        transform_single_tweet(tw, output_dir)

        # 如果有 replies, 再处理其中的 conversation
        if "replies" in tw:
            for reply in tw["replies"]:
                conv = reply.get("conversation", [])
                transform_tweets_recursive(conv, output_dir)
    return Success(tweets)


current_dir = os.path.dirname(os.path.abspath(__file__))
script_path = os.path.join(current_dir, "script.js")
style_path = os.path.join(current_dir, "style.css")

with open(script_path, "r", encoding="utf-8") as f:
    SCRIPT = f.read()
with open(style_path, "r", encoding="utf-8") as f:
    HTML_STYLES = f.read()


def generate_html(data: Dict, output_path: Union[str, Path]) -> None:
    """
    生成包含所有推文的完整 HTML 页面并写入到指定输出路径。
    """
    if isinstance(output_path, str):
        output_path = Path(output_path)
    output_dir = output_path.parent

    metadata = data.get("metadata", {})
    tweets = data.get("results", [])

    # favicon 也是资源，相对输出目录
    assets_path = Path("assets") / "twitter.png"
    favicon_path = os.path.relpath(assets_path, output_dir).replace("\\", "/")
    if not assets_path.exists():
        print(f"Warning: Favicon file not found at {assets_path}")

    transformed_tweets = (
        transform_tweets_recursive(tweets, output_dir).bind(rm_mention).unwrap()
    )

    # 组装最终 HTML
    full_html = FULL_HTML.format(
        html_styles=HTML_STYLES,
        script=SCRIPT.replace(
            "const all_data = [];",
            f"const all_data = {json.dumps(transformed_tweets, ensure_ascii=False)}",
        ),
        favicon_path=favicon_path,
        create_time=metadata.get("created_at", ""),
        item=metadata.get("item", ""),
    )
    # 写入文件
    output_path.write_text(full_html, encoding="utf-8")
