import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union

from returns.result import Failure, Result, Success

from ...service.helper import get


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

    text: str = html.escape(content)
    expanded_urls = sorted(replace_urls, key=len, reverse=True)

    placeholders = {}
    for i, url in enumerate(expanded_urls):
        placeholder = f"__URL_PLACEHOLDER_{i}__"
        placeholders[placeholder] = url
        text = text.replace(url, placeholder)

    for placeholder, url in placeholders.items():
        link_text = os.path.basename(url) or url.split("/")[-1]
        html_link = f'<a href="{url}" target="_blank" class="link">{link_text}</a>'
        text = text.replace(placeholder, html_link)

    return text


def remove_none_values(
    data: Union[Dict, List, str, int],
) -> Success[Union[Dict, List, str, int]]:
    """
    递归移除值为 None 的键值对，返回 Success 包裹的清洗后结果。
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                nested = remove_none_values(v).unwrap()
                if nested:
                    cleaned[k] = nested
            elif v is not None:
                cleaned[k] = v
        return Success(cleaned)
    elif isinstance(data, list):
        cleaned_list = [
            remove_none_values(item).unwrap() for item in data if item is not None
        ]
        return Success(cleaned_list)
    else:
        return Success(data)


def transform_paths(tweet: Dict, output_dir: Path) -> Success[Dict]:
    """
    把推文中的本地资源路径变成相对于输出文件夹的相对路径。
    """

    def rel(path: str) -> str:
        return str(Path(path).relative_to(output_dir))

    # 转换头像路径
    if get(tweet, "author.avatar.path"):
        tweet["author"]["avatar"]["path"] = rel(tweet["author"]["avatar"]["path"])

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
        if get(quote, "author.avatar.path"):
            quote["author"]["avatar"]["path"] = rel(quote["author"]["avatar"]["path"])

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


def transform_tweets_recursive(tweets: List[Dict], output_dir: Path) -> List[Dict]:
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
    return tweets


FULL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Tweets Gallery</title>
    <link rel="icon" type="image/png" href="{favicon_path}">
    <style>{html_styles}</style>
    <script type="module">
        {script}
    </script>
</head>
  <body>
    <div class="toolbar">
      <nav class="nav" data-orientation="horizontal">
        <ul>
          <li id="translate-button">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 18 18"
            >
              <g
                fill="none"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="1.5"
                stroke="#212121"
              >
                <path d="M2.25 4.25H10.25"></path>
                <path d="M6.25 2.25V4.25"></path>
                <path d="M4.25 4.25C4.341 6.926 6.166 9.231 8.75 9.934"></path>
                <path d="M8.25 4.25C7.85 9.875 2.25 10.25 2.25 10.25"></path>
                <path d="M9.25 15.75L12.25 7.75H12.75L15.75 15.75"></path>
                <path d="M10.188 13.25H14.813"></path>
              </g>
            </svg>
          </li>
          <li>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 18 18"
            >
              <g fill="#212121">
                <path
                  opacity="0.4"
                  d="M12.7501 9.75H5.25009C4.83599 9.75 4.50009 9.4141 4.50009 9C4.50009 8.5859 4.83599 8.25 5.25009 8.25H12.7501C13.1642 8.25 13.5001 8.5859 13.5001 9C13.5001 9.4141 13.1642 9.75 12.7501 9.75Z"
                ></path>
                <path
                  d="M15.2501 5H2.75009C2.33599 5 2.00009 4.6641 2.00009 4.25C2.00009 3.8359 2.33599 3.5 2.75009 3.5H15.2501C15.6642 3.5 16.0001 3.8359 16.0001 4.25C16.0001 4.6641 15.6642 5 15.2501 5Z"
                ></path>
                <path
                  d="M10.0001 14.5H8.00009C7.58599 14.5 7.25009 14.1641 7.25009 13.75C7.25009 13.3359 7.58599 13 8.00009 13H10.0001C10.4142 13 10.7501 13.3359 10.7501 13.75C10.7501 14.1641 10.4142 14.5 10.0001 14.5Z"
                ></path>
              </g>
            </svg>
          </li>
          <li>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 18 18"
            >
              <g fill="#212121">
                <path
                  opacity="0.4"
                  d="M14.146 6.32703C13.704 3.86403 11.535 2 9 2C6.105 2 3.75 4.355 3.75 7.25C3.75 7.378 3.755 7.50801 3.767 7.64001C2.163 8.07101 1 9.525 1 11.25C1 13.318 2.682 15 4.75 15H12.5C14.981 15 17 12.981 17 10.5C17 8.646 15.85 6.99703 14.146 6.32703Z"
                ></path>
                <path
                  d="M11.78 10.031L9.52999 12.281C9.38399 12.427 9.19199 12.501 8.99999 12.501C8.80799 12.501 8.61599 12.428 8.46999 12.281L6.21999 10.031C5.92699 9.73801 5.92699 9.26297 6.21999 8.96997C6.51299 8.67697 6.98799 8.67697 7.28099 8.96997L8.25099 9.94V6.75098C8.25099 6.33698 8.58699 6.00098 9.00099 6.00098C9.41499 6.00098 9.75099 6.33698 9.75099 6.75098V9.94L10.721 8.96997C11.014 8.67697 11.489 8.67697 11.782 8.96997C12.075 9.26297 12.075 9.73801 11.782 10.031H11.78Z"
                ></path>
              </g>
            </svg>
          </li>
        </ul>
      </nav>
      <div class="flex-col"><span class="timestamp">{create_time}</span><span class="timestamp">{item}</span></div>
    </div>

    <div class="tip" aria-hidden="true">
      <div class="tip__track">
        <div>Show Translate</div>
        <div>Filter Content</div>
        <div>Download Resources</div>
      </div>
    </div>
    <main class="main-container">
      <div class="tweets-container">
        <div class="tweets-column"></div>
        <div class="tweets-column"></div>
        <div class="tweets-column"></div>
      </div>
    </main>
  </body>
</html>
"""

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

    # 先把推文递归处理一遍
    transformed_tweets = transform_tweets_recursive(tweets, output_dir)

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
