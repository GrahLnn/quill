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
    metadata = data.get("metadata")
    tweets = data.get("results", [])
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
    )
    # 写入文件
    output_path.write_text(full_html, encoding="utf-8")
