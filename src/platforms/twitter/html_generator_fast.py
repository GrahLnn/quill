import html
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fasthtml import FastHTML
from .tw_api import get

# 创建FastHTML实例
h = FastHTML()

def format_timestamp(timestamp: str, format="%Y-%m-%d %H:%M") -> str:
    dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.strftime(format)

def format_content_with_links(content: Dict) -> str:
    text = content.get("text", "")
    entities = content.get("entities", {})
    urls = entities.get("urls", [])
    
    # 按照位置倒序排序，这样替换时不会影响其他URL的位置
    urls.sort(key=lambda x: x["start"], reverse=True)
    
    for url in urls:
        start, end = url["start"], url["end"]
        display_url = url.get("display_url", "")
        expanded_url = url.get("expanded_url", "")
        link_html = h.a(display_url, href=expanded_url, target="_blank", rel="noopener noreferrer")
        text = text[:start] + str(link_html) + text[end:]
    
    return text

def get_relative_path(path: str, output_dir: Path) -> str:
    return os.path.relpath(path, output_dir)

def generate_media_html(medias: List[Dict], output_dir: Path, is_quote=False) -> str:
    if not medias:
        return ""
    
    media_count = len(medias)
    container_class = f"media-container media-{media_count}" + (" quote-media" if is_quote else "")
    
    with h.div(class_=container_class) as media_container:
        for i, media in enumerate(medias):
            media_type = media.get("type", "")
            media_url = media.get("url", "")
            
            if media_type == "video":
                video_variants = media.get("video_info", {}).get("variants", [])
                video_url = next((v["url"] for v in video_variants if v["content_type"] == "video/mp4"), None)
                if video_url:
                    h.video(controls=True, class_="media-content") \
                        .source(src=video_url, type="video/mp4")
            elif media_type == "photo":
                img_class = "media-content" + (" quote-img" if is_quote else "")
                h.img(src=get_relative_path(media_url, output_dir), class_=img_class, loading="lazy")
    
    return str(media_container)

def generate_card_html(card: Dict) -> str:
    if not card:
        return ""
    
    with h.div(class_="card") as card_container:
        with h.a(href=card.get("url", ""), target="_blank", rel="noopener noreferrer"):
            if card.get("image"):
                h.img(src=card["image"], alt="Card image", class_="card-img")
            with h.div(class_="card-content"):
                h.div(card.get("title", ""), class_="card-title")
                h.div(card.get("description", ""), class_="card-description")
                h.div(card.get("domain", ""), class_="card-domain")
    
    return str(card_container)

def generate_quote_html(quote: Dict, output_dir: Path) -> str:
    if not quote:
        return ""
    
    with h.div(class_="quoted-tweet") as quote_container:
        with h.div(class_="tweet-header"):
            with h.div(class_="user"):
                with h.div(style="display: flex; justify-content: center; align-items: center;"):
                    h.img(src=quote["user"].get("profile_image_url", ""), alt="Avatar", class_="avatar")
                with h.div(class_="user-info"):
                    h.span(quote["user"].get("name", ""), class_="name")
                    h.span(f"@{quote['user'].get('username', '')}", class_="username")
        
        content = format_content_with_links(quote)
        h.div(content, class_="tweet-content")
        
        if quote.get("media"):
            quote_container.append(generate_media_html(quote["media"], output_dir, is_quote=True))
    
    return str(quote_container)

def generate_tweet_html(tweet: Dict, output_dir: Path, index: int) -> str:
    with h.div(id=str(index), class_="tweet") as tweet_container:
        # Tweet header
        with h.div(class_="tweet-header"):
            with h.div(class_="user"):
                with h.div(style="display: flex; justify-content: center; align-items: center;"):
                    h.img(src=tweet["user"].get("profile_image_url", ""), alt="Avatar", class_="avatar")
                with h.div(class_="user-info"):
                    h.span(tweet["user"].get("name", ""), class_="name")
                    h.span(f"@{tweet['user'].get('username', '')}", class_="username")
            h.span(class_="timestamp")
        
        # Tweet content
        content = format_content_with_links(tweet)
        h.div(content, class_="tweet-content")
        
        # Media, card and quote
        if tweet.get("media"):
            tweet_container.append(generate_media_html(tweet["media"], output_dir))
        if tweet.get("card"):
            tweet_container.append(generate_card_html(tweet["card"]))
        if tweet.get("quoted_tweet"):
            tweet_container.append(generate_quote_html(tweet["quoted_tweet"], output_dir))
        
        # Footer
        with h.div(style="margin-top: 8px"):
            with h.div(class_="footer"):
                h.span(format_timestamp(tweet["created_at"]), class_="timestamp")
                h.a(
                    f"https://twitter.com/{tweet['user']['username']}/status/{tweet['id']}",
                    href=f"https://twitter.com/{tweet['user']['username']}/status/{tweet['id']}",
                    target="_blank",
                    rel="noopener noreferrer",
                    class_="tweet-link"
                )
    
    return str(tweet_container)

def generate_html(data: Dict, output_path: str) -> None:
    # 创建基本的HTML结构
    with h.html() as doc:
        with h.head():
            h.meta(charset="UTF-8")
            h.title("Tweets Gallery")
            h.link(rel="icon", type="image/png", href=data.get("favicon_path", ""))
            h.style(data["html_styles"])
            h.script(f"const all_data = {json.dumps(data['tweets'])};")
            h.script(data["script"])
        
        with h.body():
            with h.main(class_="main-container"):
                with h.div(class_="tweets-container"):
                    h.div(class_="tweets-column")
                    h.div(class_="tweets-column")
                    h.div(class_="tweets-column")
    
    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(str(doc))
