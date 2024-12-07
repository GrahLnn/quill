import html
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List


COLUMN_COUNT = 3  # 推文列数
TWEET_TEMPLATE = """
    <div class="tweet">
        <div class="tweet-header">
            <div class="user-info">
                <span class="name">{name}</span>
                <span class="username">@{username}</span>
            </div>
            <span class="timestamp">{timestamp}</span>
        </div>
        <div class="tweet-content">{content}</div>
        {media_html}
        {quote_html}
        <div style="margin-top: 8px;">
            <a href="https://twitter.com/{username}/status/{tweet_id}" class="link2x" target="_blank">
                View on Twitter
            </a>
        </div>
    </div>
"""
SCRIPT = """document.addEventListener('DOMContentLoaded', function() {
                // Create lightbox elements
                const lightbox = document.createElement('div');
                lightbox.className = 'lightbox';
                const lightboxImg = document.createElement('img');
                lightboxImg.className = 'lightbox-img';
                lightbox.appendChild(lightboxImg);
                document.body.appendChild(lightbox);

                let isZoomed = false;

                // Add click handlers to all media images
                document.querySelectorAll('.media-item').forEach(img => {
                    img.addEventListener('click', function() {
                        lightboxImg.src = this.src;
                        lightbox.style.display = 'flex';
                        // Add active class after a small delay to trigger transition
                        requestAnimationFrame(() => {
                            lightbox.classList.add('active');
                            document.body.style.overflow = 'hidden';
                        });
                        // Reset zoom state
                        isZoomed = false;
                        lightboxImg.classList.remove('zoomed');
                        lightboxImg.style.width = '';
                    });
                });

                // Handle lightbox image click for zoom
                lightboxImg.addEventListener('click', function(e) {
                    e.stopPropagation(); // 阻止关闭 lightbox
                    
                    if (!isZoomed) {
                        // 计算放大后的尺寸
                        const width = Math.min(this.naturalWidth, window.innerWidth * 0.98);
                        const zoomedHeight = width * (this.naturalHeight / this.naturalWidth);
                        
                        // 只在放大后高度超过视窗时才放大
                        if (zoomedHeight > window.innerHeight) {
                            this.classList.add('zoomed');
                            this.style.width = width + 'px';
                            this.style.height = 'auto';
                            lightbox.classList.add('zoomed');
                        }
                        isZoomed = true;
                    } else {
                        // 缩小
                        this.classList.remove('zoomed');
                        lightbox.classList.remove('zoomed');
                        this.style.width = '';
                        this.style.height = '';
                        isZoomed = false;
                    }
                });

                // Close lightbox when clicking outside the image
                lightbox.addEventListener('click', function(e) {
                    if (e.target === lightbox) {
                        lightbox.classList.remove('active');
                        lightbox.classList.remove('zoomed');
                        document.body.style.overflow = '';
                        // Wait for transition to finish before hiding
                        setTimeout(() => {
                            lightbox.style.display = 'none';
                            // Reset zoom state
                            isZoomed = false;
                            lightboxImg.classList.remove('zoomed');
                            lightboxImg.style.width = '';
                            lightboxImg.style.height = '';
                        }, 300);
                    }
                });
            });
"""
# 完整 HTML
FULL_HTML = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Tweets Gallery</title>
        <link rel="icon" type="image/png" href="{favicon_path}">
        <style>{html_styles}</style>
        <script>
            {script}
        </script>
    </head>
    <body>
        <div class="tweets-container">{columns_html}</div>
    </body>
    </html>
"""
HTML_STYLES = (
    """body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f8fa;
            }
            .tweets-container {
                display: grid;
                grid-template-columns: repeat("""
    + str(COLUMN_COUNT)
    + """, 1fr);
                gap: 15px;
            }
            .tweet {
                background: white;
                border: 1px solid #e1e8ed;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                display: flex;
                flex-direction: column;
            }
            .tweets-column {
                display: flex;
                flex-direction: column;
                gap: 15px;
                max-width: 390px;
            }
            .tweet-header {
                margin-bottom: 8px;
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
            }
            .user-info {
                display: flex;
                flex-direction: column;
            }
            .name {
                font-weight: bold;
                color: #14171a;
            }
            .username {
                color: #657786;
                font-size: 0.9em;
            }
            .timestamp {
                color: #657786;
                font-size: 0.85em;
                white-space: nowrap;
            }
            .tweet-content {
                margin-bottom: 10px;
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            .tweet-stats {
                display: flex;
                gap: 15px;
                color: #657786;
                font-size: 0.9em;
                margin: 8px 0;
            }
            .media-container {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 8px;
                margin-top: 8px;
            }
            .media-item {
                width: 100%;
                border-radius: 8px;
                object-fit: cover;
                cursor: pointer;
                transition: opacity 0.2s;
            }
            .media-item:hover {
                opacity: 0.9;
            }
            .media-unavailable {
                background: #f8f9fa;
                color: #657786;
                padding: 15px;
                text-align: center;
                border-radius: 8px;
                border: 1px dashed #ccd6dd;
            }
            .video-container {
                width: 100%;
                margin-top: 8px;
            }
            .video-player {
                width: 100%;
                border-radius: 8px;
                max-height: 400px;
            }
            .quote-tweet {
                border: 1px solid #e1e8ed;
                border-radius: 8px;
                padding: 10px;
                margin: 8px 0;
                background: #f8f9fa;
                font-size: 0.95em;
            }
            .link {
                color: #1da1f2;
                text-decoration: none;
                font-size: 1em;
            }
            .link:hover {
                text-decoration: underline;
            }
            .link2x {
                color: #1da1f2;
                text-decoration: none;
                font-size: 0.85em;
            }
            .link2x:hover {
                text-decoration: underline;
            }
            .lightbox {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                backdrop-filter: blur(10px);
                background-color: rgba(255, 255, 255, 0.5);
                justify-content: center;
                align-items: center;
                z-index: 1000;
                opacity: 0;
                transition: opacity 0.5s ease;
                box-sizing: border-box;
                padding: 0;
                overflow-y: auto;
            }
            .lightbox.active {
                opacity: 1;
            }
            .lightbox.zoomed {
                align-items: start;
            }
            .lightbox-img {
                max-width: 90%;
                max-height: 90vh;
                object-fit: contain;
                border-radius: 4px;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
                transform: scale(0.95);
                transition: transform 0.3s ease;
            }
            .lightbox-img.zoomed {
                max-width: 98vw;
                max-height: none;
                margin: 16px 0;
                transition: width 0.3s ease, transform 0.3s ease;
            }
            .lightbox-img:hover {
                cursor: pointer;
            }
            .lightbox-img.zoomed:hover {
                cursor: pointer;
            }
            .lightbox.active .lightbox-img {
                transform: scale(1);
            }"""
)


def format_timestamp(timestamp: str) -> str:
    """格式化时间戳"""
    if not timestamp:
        return ""
    time_format = "%a %b %d %H:%M:%S %z %Y"
    local_tz = datetime.now().astimezone().tzinfo
    parsed_time = datetime.strptime(timestamp, time_format)
    return parsed_time.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")


def format_content_with_links(content: Dict) -> str:
    """将文本中的URL替换为HTML链接"""
    if not content:
        return ""

    text: str = html.escape(content.get("text", ""))
    expanded_urls = content.get("expanded_urls", [])

    for url in expanded_urls:
        link_text = os.path.basename(url)
        html_link = f'<a href="{url}" target="_blank" class="link">{link_text}</a>'
        text = text.replace(url, html_link)

    return text


def generate_media_html(medias: List[Dict], output_dir: Path) -> str:
    """生成媒体的 HTML"""
    if not medias:  # This will handle both None and empty list cases
        return ""

    media_items = []
    for media in medias:
        path = media.get("path")
        if path == "media unavailable":
            media_items.append('<div class="media-unavailable">Media Unavailable</div>')
        elif path:
            path_obj = Path(path)
            rel_path = path_obj.relative_to(output_dir)
            if media.get("type") in ["video", "animated_gif"]:
                poster = media.get("thumb_path", "")
                if poster:
                    poster_path = Path(poster)
                    poster = str(poster_path.relative_to(output_dir))

                # Calculate aspect ratio from width and height array
                aspect_ratio = media.get("aspect_ratio", [16, 9])
                ratio = aspect_ratio[1] / aspect_ratio[0]
                padding_bottom = min(ratio * 100, 100)  # Cap at 100%

                # For animated GIFs, add autoplay, loop, and muted attributes
                video_attrs = 'controls preload="none"'
                if media.get("type") == "animated_gif":
                    video_attrs = 'autoplay loop muted playsinline preload="auto"'

                media_items.append(
                    f'<div class="video-container" style="position: relative; padding-bottom: {padding_bottom}%;">'
                    f'<video class="video-player" {video_attrs} poster="{poster}" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">'
                    f'<source src="{rel_path}" type="video/mp4">Your browser does not support video.'
                    f"</video></div>"
                )
            else:
                media_items.append(
                    f'<img class="media-item" src="{rel_path}" loading="lazy" />'
                )
    return (
        f'<div class="media-container">{"".join(media_items)}</div>'
        if media_items
        else ""
    )


def generate_quote_html(quote: Dict, output_dir: Path) -> str:
    """生成引用推文的 HTML"""
    if not quote:
        return ""
    content = format_content_with_links(quote.get("content"))
    name = quote.get("name", "")
    username = quote.get("screen_name", "")
    timestamp = format_timestamp(quote.get("created_at"))
    media_html = generate_media_html(quote.get("media", []), output_dir)
    return f"""
    <div class="quote-tweet">
        <div class="tweet-header">
            <div class="user-info">
                <span class="name">{name}</span>
                <span class="username">@{username}</span>
            </div>
            <span class="timestamp">{timestamp}</span>
        </div>
        <div class="tweet-content">{content}</div>
        {media_html}
    </div>
    """


def generate_tweet_html(tweet: Dict, output_dir: Path, template: str) -> str:
    """生成单条推文的 HTML"""
    name = tweet.get("name", "")
    username = tweet.get("screen_name", "")
    timestamp = format_timestamp(tweet.get("created_at"))
    content = format_content_with_links(tweet.get("content"))
    media_html = generate_media_html(tweet.get("media", []), output_dir)
    quote_html = generate_quote_html(tweet.get("quote", {}), output_dir)
    tweet_id = tweet.get("rest_id", "")

    return template.format(
        name=name,
        username=username,
        timestamp=timestamp,
        content=content,
        media_html=media_html,
        quote_html=quote_html,
        tweet_id=tweet_id,
    )


def generate_html(data: Dict, output_path: Path) -> None:
    """生成包含所有推文的完整 HTML 页面"""
    metadata = data.get("metadata")
    tweets = data.get("results", [])
    output_dir = output_path.parent

    # Calculate relative path from output directory to assets
    assets_path = Path("assets") / "twitter.png"
    favicon_path = os.path.relpath(assets_path, output_dir).replace("\\", "/")

    # Verify that the favicon file exists
    if not assets_path.exists():
        print(f"Warning: Favicon file not found at {assets_path}")

    # 每列初始化为空列表
    tweets_columns = [[] for _ in range(COLUMN_COUNT)]

    # 按列分配推文
    for i, tweet in enumerate(tweets):
        col_index = i % COLUMN_COUNT
        tweets_columns[col_index].append(
            generate_tweet_html(tweet, output_dir, TWEET_TEMPLATE)
        )

    # 合成列 HTML
    columns_html = "".join(
        f'<div class="tweets-column">{"".join(column)}</div>'
        for column in tweets_columns
    )

    full_html = FULL_HTML.format(
        columns_html=columns_html,
        html_styles=HTML_STYLES,
        script=SCRIPT,
        favicon_path=favicon_path,
    )
    # 写入文件
    output_path.write_text(full_html, encoding="utf-8")
