import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union

from returns.result import Failure, Result, Success

from .tw_api import get


FULL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Tweets Gallery</title>
    <link rel="icon" type="image/png" href="{favicon_path}">
    <style>{html_styles}</style>
    <script>
        const all_data = {all_data};
        {script}
    </script>
</head>
<body>
    <div class="toolbar">
        <button class="toolbar-button" id="translate-button"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18" > <g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121" > <path d="M2.25 4.25H10.25"></path> <path d="M6.25 2.25V4.25"></path> <path d="M4.25 4.25C4.341 6.926 6.166 9.231 8.75 9.934"></path> <path d="M8.25 4.25C7.85 9.875 2.25 10.25 2.25 10.25"></path> <path d="M9.25 15.75L12.25 7.75H12.75L15.75 15.75"></path> <path d="M10.188 13.25H14.813"></path> </g> </svg><span class="button-label">Translate Content</span></button>

        <button class="toolbar-button" id="filter-button"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18"><g fill="#212121"><path opacity="0.4" d="M12.7501 9.75H5.25009C4.83599 9.75 4.50009 9.4141 4.50009 9C4.50009 8.5859 4.83599 8.25 5.25009 8.25H12.7501C13.1642 8.25 13.5001 8.5859 13.5001 9C13.5001 9.4141 13.1642 9.75 12.7501 9.75Z"></path> <path d="M15.2501 5H2.75009C2.33599 5 2.00009 4.6641 2.00009 4.25C2.00009 3.8359 2.33599 3.5 2.75009 3.5H15.2501C15.6642 3.5 16.0001 3.8359 16.0001 4.25C16.0001 4.6641 15.6642 5 15.2501 5Z"></path> <path d="M10.0001 14.5H8.00009C7.58599 14.5 7.25009 14.1641 7.25009 13.75C7.25009 13.3359 7.58599 13 8.00009 13H10.0001C10.4142 13 10.7501 13.3359 10.7501 13.75C10.7501 14.1641 10.4142 14.5 10.0001 14.5Z"></path></g></svg><span class="button-label">Filter Content</span></button>

        <button class="toolbar-button" id="download-button"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18"><g fill="#212121"><path opacity="0.4" d="M14.146 6.32703C13.704 3.86403 11.535 2 9 2C6.105 2 3.75 4.355 3.75 7.25C3.75 7.378 3.755 7.50801 3.767 7.64001C2.163 8.07101 1 9.525 1 11.25C1 13.318 2.682 15 4.75 15H12.5C14.981 15 17 12.981 17 10.5C17 8.646 15.85 6.99703 14.146 6.32703Z"></path> <path d="M11.78 10.031L9.52999 12.281C9.38399 12.427 9.19199 12.501 8.99999 12.501C8.80799 12.501 8.61599 12.428 8.46999 12.281L6.21999 10.031C5.92699 9.73801 5.92699 9.26297 6.21999 8.96997C6.51299 8.67697 6.98799 8.67697 7.28099 8.96997L8.25099 9.94V6.75098C8.25099 6.33698 8.58699 6.00098 9.00099 6.00098C9.41499 6.00098 9.75099 6.33698 9.75099 6.75098V9.94L10.721 8.96997C11.014 8.67697 11.489 8.67697 11.782 8.96997C12.075 9.26297 12.075 9.73801 11.782 10.031H11.78Z"></path></g></svg><span class="button-label">Download Resources</span></button>

        <div class="flex-col"><span class="timestamp">{create_time}</span><span class="timestamp">{item}</span></div>
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

# 拼接文件路径
script_path = os.path.join(current_dir, "script.js")
style_path = os.path.join(current_dir, "style.css")
with open(script_path, "r", encoding="utf-8") as file:
    SCRIPT = file.read()
with open(style_path, "r", encoding="utf-8") as file:
    HTML_STYLES = file.read()


def format_timestamp(timestamp: str, format="%Y-%m-%d %H:%M") -> str:
    """格式化时间戳"""
    if not timestamp:
        return ""
    time_format = "%a %b %d %H:%M:%S %z %Y"
    local_tz = datetime.now().astimezone().tzinfo
    parsed_time = datetime.strptime(timestamp, time_format)
    return parsed_time.astimezone(local_tz).strftime(format)


def format_content_with_links(content: str, replace_urls: List[str]) -> str:
    """将文本中的URL替换为HTML链接，处理顺序：
    1. 按URL长度降序排序，避免短URL替换长URL中的子串
    2. 替换时使用临时占位符，避免重复替换
    """
    if not content:
        return ""

    text: str = html.escape(content)
    expanded_urls: List[str] = sorted(
        replace_urls, key=len, reverse=True
    )  # 按长度降序排序

    # 使用占位符替换，避免URL互相影响
    placeholders = {}
    for i, url in enumerate(expanded_urls):
        placeholder = f"__URL_PLACEHOLDER_{i}__"
        placeholders[placeholder] = url
        text = text.replace(url, placeholder)

    # 将占位符替换为最终的HTML链接
    for placeholder, url in placeholders.items():
        link_text = os.path.basename(url) or [u for u in url.split("/") if u][-1]
        html_link = f'<a href="{url}" target="_blank" class="link">{link_text}</a>'
        text = text.replace(placeholder, html_link)

    return text


def get_relative_path(path: str, output_dir: Path) -> str:
    path_obj = Path(path)
    return str(path_obj.relative_to(output_dir))


def transform_path(tweet: Dict, output_dir: Path) -> Success[Dict]:
    if (
        "author" in tweet
        and "avatar" in tweet["author"]
        and "path" in tweet["author"]["avatar"]
    ):
        avatar_path = get(tweet, "author.avatar.path")
        tweet["author"]["avatar"]["path"] = get_relative_path(avatar_path, output_dir)

    if "media" in tweet and isinstance(tweet["media"], list):
        for m in tweet["media"]:
            if not get(m, "path") == "media unavailable":
                if "path" in m:
                    m["path"] = get_relative_path(m["path"], output_dir)
                if "thumb_path" in m:
                    m["thumb_path"] = get_relative_path(m["thumb_path"], output_dir)

    if "quote" in tweet and isinstance(tweet["quote"], dict):
        quote = tweet["quote"]
        if (
            "author" in quote
            and "avatar" in quote["author"]
            and "path" in quote["author"]["avatar"]
        ):
            q_avatar_path = get(quote, "author.avatar.path")
            quote["author"]["avatar"]["path"] = get_relative_path(
                q_avatar_path, output_dir
            )

        if "media" in quote and isinstance(quote["media"], list):
            for qm in quote["media"]:
                if not get(qm, "path") == "media unavailable":
                    if "path" in qm:
                        qm["path"] = get_relative_path(qm["path"], output_dir)
                    if "thumb_path" in qm:
                        qm["thumb_path"] = get_relative_path(
                            qm["thumb_path"], output_dir
                        )
    return Success(tweet)


def transform_timestamp(tweet: Dict):
    tweet["created_at"] = format_timestamp(tweet.get("created_at"))
    return Success(tweet)


def transform_text(tweet: Dict) -> Success[Dict]:
    if quote := get(tweet, "quote"):
        tweet["quote"]["content"]["text"] = format_content_with_links(
            get(quote, "content.text"), get(quote, "content.expanded_urls")
        )
        if translation := get(quote, "content.translation"):
            tweet["quote"]["content"]["translation"] = format_content_with_links(
                translation, get(quote, "content.expanded_urls")
            )
    if content := get(tweet, "content"):
        tweet["content"]["text"] = format_content_with_links(
            get(content, "text"), get(content, "expanded_urls")
        )
        if translation := get(content, "translation"):
            tweet["content"]["translation"] = format_content_with_links(
                translation, get(content, "expanded_urls")
            )
    return Success(tweet)


def remove_none_values(data: Union[Dict, List]) -> Result[Union[Dict, List], Exception]:
    """
    递归移除字典中所有值为 None 的键值对，处理嵌套字典和列表，并返回 Success 类型。
    """
    try:
        if isinstance(data, dict):  # 如果是字典
            cleaned_data = {}
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    nested = remove_none_values(value).unwrap()  # 递归处理嵌套结构
                    if nested:  # 如果嵌套结果非空
                        cleaned_data[key] = nested
                elif value is not None:  # 如果值不是 None
                    cleaned_data[key] = value
            return Success(cleaned_data)
        elif isinstance(data, list):  # 如果是列表
            cleaned_list = [
                remove_none_values(item).unwrap() for item in data if item is not None
            ]
            return Success(cleaned_list)
        else:
            return Success(data)
    except Exception as e:
        return Failure(e)  # 捕获异常并返回 Failure


def transform_tweet_data(tweet: Dict, output_dir: Path) -> Dict:
    """
    针对单条 tweet，递归把其中涉及到的各种本地资源路径
    转成相对于 output_dir 的形式，供前端直接用 <img src="..."> 等。
    """

    return (
        transform_path(tweet, output_dir)
        .bind(transform_timestamp)
        .bind(transform_text)
        .bind(remove_none_values)
        .unwrap()
    )


def transform_all_tweets(tweets: List[Dict], output_dir: Path) -> List[Dict]:
    """
    批量处理所有 tweet，把其中的本地资源路径都转成相对路径。
    """
    new_tweets = []
    for t in tweets:
        new_tweets.append(transform_tweet_data(t, output_dir))
    return new_tweets


def generate_html(data: Dict, output_path) -> None:
    """生成包含所有推文的完整 HTML 页面"""
    metadata: Dict = data.get("metadata")
    tweets: List[Dict] = data.get("results", [])
    if isinstance(output_path, str):
        output_path = Path(output_path)
    output_dir = output_path.parent

    # Calculate relative path from output directory to assets
    assets_path = Path("assets") / "twitter.png"
    favicon_path = os.path.relpath(assets_path, output_dir).replace("\\", "/")

    # Verify that the favicon file exists
    if not assets_path.exists():
        print(f"Warning: Favicon file not found at {assets_path}")

    transformed_tweets = transform_all_tweets(tweets, output_dir)

    full_html = FULL_HTML.format(
        all_data=json.dumps(transformed_tweets, ensure_ascii=False),
        html_styles=HTML_STYLES,
        script=SCRIPT,
        favicon_path=favicon_path,
        create_time=metadata.get("created_at"),
        item=metadata.get("item"),
    )
    # 写入文件
    output_path.write_text(full_html, encoding="utf-8")
