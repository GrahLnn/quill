import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# --------------- Python 端只保留必需的辅助函数 ---------------

def get_relative_path(path: str, output_dir: Path) -> str:
    """
    将绝对路径或其他形式的路径转成相对于 output_dir 的相对路径，
    在浏览器中可用。比如:
      /home/user/project/media/xxx.jpg -> ../media/xxx.jpg
    """
    if not path or path == "media unavailable":
        return path
    try:
        # 如果只是相对路径本身，这里也能处理，不会报错
        return str(Path(path).relative_to(output_dir))
    except ValueError:
        # 若不能 relative_to，就直接返回原路径或自定义处理
        return path

def transform_tweet_data(tweet: Dict, output_dir: Path) -> Dict:
    """
    针对单条 tweet，递归把其中涉及到的各种本地资源路径
    转成相对于 output_dir 的形式，供前端直接用 <img src="..."> 等。
    """

    # 1) 处理作者头像
    if "author" in tweet and "avatar" in tweet["author"] and "path" in tweet["author"]["avatar"]:
        avatar_path = tweet["author"]["avatar"]["path"]
        tweet["author"]["avatar"]["path"] = get_relative_path(avatar_path, output_dir)

    # 2) 处理 media
    if "media" in tweet and isinstance(tweet["media"], list):
        for m in tweet["media"]:
            if "path" in m:
                m["path"] = get_relative_path(m["path"], output_dir)
            if "thumb_path" in m:
                m["thumb_path"] = get_relative_path(m["thumb_path"], output_dir)

    # 3) 处理 card
    #   - 若有更复杂的资源，比如 card 内也有图片路径，可类似处理

    # 4) 处理 quote
    if "quote" in tweet and isinstance(tweet["quote"], dict):
        quote = tweet["quote"]
        # 4.1) quote 作者头像
        if "author" in quote and "avatar" in quote["author"] and "path" in quote["author"]["avatar"]:
            q_avatar_path = quote["author"]["avatar"]["path"]
            quote["author"]["avatar"]["path"] = get_relative_path(q_avatar_path, output_dir)

        # 4.2) quote media
        if "media" in quote and isinstance(quote["media"], list):
            for qm in quote["media"]:
                if "path" in qm:
                    qm["path"] = get_relative_path(qm["path"], output_dir)
                if "thumb_path" in qm:
                    qm["thumb_path"] = get_relative_path(qm["thumb_path"], output_dir)

    return tweet

def transform_all_tweets(tweets: List[Dict], output_dir: Path) -> List[Dict]:
    """
    批量处理所有 tweet，把其中的本地资源路径都转成相对路径。
    """
    new_tweets = []
    for t in tweets:
        new_tweets.append(transform_tweet_data(t, output_dir))
    return new_tweets

# --------------- 前端的模板 + 样式 + JS脚本 ---------------

FULL_HTML = r"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Tweets Gallery</title>
    <link rel="icon" type="image/png" href="{favicon_path}">
    <style>{html_styles}</style>
    <script>
        // ================================================
        // 后端注入的 tweet 原始数据，只有相对路径等字段改写过
        // ================================================
        const all_data = {all_data_json};

        // ================================================
        // 下面是前端脚本：生成单条 Tweet HTML 的函数，以及
        // 懒加载、翻译切换、视频 IntersectionObserver 等逻辑
        // ================================================
        {render_script}
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

HTML_STYLES = r"""
/* 你的 CSS 样式，可根据实际需求微调 */
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #f5f8fa;
    margin: 0;
}
.main-container {
    min-height: 100vh;
    max-width: 100%;
}
.tweets-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 15px;
}
.tweets-column {
    display: flex;
    flex-direction: column;
    gap: 15px;
    max-width: 390px;
    align-self: flex-start;
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
.tweet-header {
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
}
.user {
    display: flex;
    gap: 8px;
}
.avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    object-fit: cover;
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
.tool {
    display: flex;
    gap: 2px;
    opacity: 0;
    transition: opacity 0.3s ease;
}
.tweet:hover .tool {
    opacity: 1;
}
.tool > div {
    width: 24px;
    height: 24px;
    border-radius: 4px;
    transition: all 0.2s ease;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    user-select: none;
}
.tool .language:hover, .tool .pin:hover {
    opacity: 0.9 !important;
    background-color: rgba(0, 0, 0, 0.05);
}
.tweet-content {
    margin-bottom: 10px;
    white-space: pre-wrap;
    word-wrap: break-word;
    position: relative;
}
#trs-unsee {
    position: absolute;
    left: 0;
    width: 100%;
    visibility: hidden;
}
@keyframes smoke {
    100% {
        filter: blur(6px);
        opacity: 0;
    }
}
.tweet-content span {
    display: inline-block;
    backface-visibility: hidden;
}
.tweet-content #src.smoke-out {
    animation: smoke 0.3s linear forwards;
}
.tweet-content #src.smoke-in {
    animation: smoke 0.3s linear reverse forwards;
}
.tweet-content #trs.smoke-out {
    animation: smoke 0.3s linear forwards;
}
.tweet-content #trs.smoke-in {
    animation: smoke 0.3s linear reverse forwards;
}
.footer {
    margin-top: 2px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.timestamp {
    color: #657786;
    font-size: 0.85em;
    white-space: nowrap;
}
.link2x {
    color: #1da1f2;
    text-decoration: none;
    font-size: 0.85em;
}
.link2x:hover {
    text-decoration: underline;
}
/* media */
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
.animated-gif-player {
    width: 100%;
    border-radius: 8px;
    max-height: 400px;
}
.quote-tweet {
    border: 1px solid #e1e8ed;
    border-radius: 8px;
    padding: 10px;
    margin-top: 8px;
    background: #f8f9fa;
    font-size: 0.95em;
}
.quote-video-player {
    width: 100%;
    border-radius: 4px;
    max-height: 400px;
}
.quote-media-item {
    width: 100%;
    border-radius: 4px;
    object-fit: cover;
    cursor: pointer;
    transition: opacity 0.2s;
}
.quote-media-item:hover {
    opacity: 0.9;
}
/* card */
.card {
    border-radius: 8px;
    padding: 10px;
    margin: 8px 0;
    font-size: 0.95em;
    transition: all 0.2s ease-in-out;
    border: 1px solid #e1e8ed;
}
.card:hover {
    background: #f8f9fa;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06),
                0 3px 6px rgba(0, 0, 0, 0.06),
                0 6px 12px rgba(0, 0, 0, 0.06);
}
.link {
    color: #1da1f2;
    text-decoration: none;
    font-size: 1em;
}
.link:hover {
    text-decoration: underline;
}
/* lightbox */
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
    transition: opacity 0.3s ease;
    box-sizing: border-box;
    padding: 0;
    overflow-y: auto;
}
.lightbox.active {
    display: flex;
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
    transform: scale(0.7);
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
}
"""

# 这里就是替代原先的 SCRIPT，用于在前端生成 Tweet HTML
# 大体是把你前面给出的 JS 改造好的版本拼起来。
RENDER_SCRIPT = r"""
// =========================
// 全局常量与变量定义
// =========================

let currentOffset = 0;             // 已经从 all_data 中加载的偏移量
const chunkSize = 30;              // 每批加载的 tweet 数量
const renderedTweetIds = new Set();// 已经渲染到页面中的 tweet ID
const monitoredMediaContainers = {};// 存储需要监控的 Tweet 媒体容器
const observedVideos = new WeakMap();// 记录被 IntersectionObserver 观察的 video
const languageListeners = new WeakMap();// 记录语言切换按钮监听器
const placeholderMap = {};         // 存储占位符相关信息
const visibleTweets = new Map();   // 存储当前可见的 tweets
const heightCache = new Map();     // 缓存 media container 的高度信息

let tweetsColumns; // 在DOMContentLoaded后初始化
let columnEnds;    // 每列当前的 tweet 数量记录

// IntersectionObserver 用于视频自动播放
let videoObserver = null;


// =========================
// 时间戳格式化示例
// =========================
function formatTimestamp(raw) {
  if (!raw) return "";
  // 如果 raw 是标准的 "Sat Dec 10 14:46:52 +0000 2022" 之类，需要先做转换
  // 这里演示最简单用 new Date() 直接 parse
  const date = new Date(raw);
  if (isNaN(date.getTime())) return raw;
  return date.toLocaleString();
}


// =========================
// 文本转义及 URL 转链接
// =========================
function escapeAndLinkify(text, expandedUrls) {
  if (!text) return "";
  // 1) 转义 HTML 特殊字符
  let escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // 2) 将 URL 转换为 <a> 链接（此处仅示例，和你原先 Python 里的逻辑类似）
  if (Array.isArray(expandedUrls)) {
    // 先按长度降序
    expandedUrls.sort((a, b) => b.length - a.length);
    expandedUrls.forEach((url) => {
      // 这里简单处理
      const linkText = url.split("/").pop() || url;
      const safeUrl = url.replace(/([.*+?^${}()|\[\]\/\\])/g, '\\$1'); // 正则转义
      const pattern = new RegExp(safeUrl, "g");
      escaped = escaped.replace(
        pattern,
        `<a href="${url}" target="_blank" class="link">${linkText}</a>`
      );
    });
  }

  return escaped;
}


// =========================
// 生成单条 Tweet HTML
// =========================
function generateMediaHtml(medias, isQuote = false) {
  if (!Array.isArray(medias) || medias.length === 0) return "";

  const mediaItems = medias.map((media) => {
    const path = media.path;
    if (!path || path === "media unavailable") {
      return '<div class="media-unavailable">Media Unavailable</div>';
    }
    const mediaType = media.type;
    if (mediaType === "video") {
      // 普通视频
      return `
        <div class="video-container">
          <video class="${isQuote ? "quote-video-player" : "video-player"}" 
                 controls preload="none" playsinline style="width: 100%; height: 100%;">
            <source src="${path}" type="video/mp4">
            Your browser does not support video.
          </video>
        </div>
      `;
    } else if (mediaType === "animated_gif") {
      // GIF
      return `
        <div class="video-container">
          <video class="animated-gif-player" autoplay loop muted playsinline 
                 style="width: 100%; height: 100%;">
            <source src="${path}" type="video/mp4">
            Your browser does not support video.
          </video>
        </div>
      `;
    } else {
      // 图片
      return `<img class="${isQuote ? "quote-media-item" : "media-item"}" src="${path}" loading="lazy" />`;
    }
  });

  return `<div class="media-container">${mediaItems.join("")}</div>`;
}

function generateCardHtml(card) {
  if (!card || !card.url) return "";
  const title = card.title || "";
  const description = card.description || "";
  const url = card.url;
  return `
    <a href="${url}" style="text-decoration: none; color: inherit;" target="_blank">
      <div class="card">
        <div style="font-size: 12px; font-weight: bold;">
          ${title}
        </div>
        ${
          description
            ? `<div style="font-size: 10px; color: #536471; margin-top: 5px;">${description}</div>`
            : ""
        }
      </div>
    </a>
  `;
}

function generateQuoteHtml(quote) {
  if (!quote) return "";
  // 引用推文的文本
  const content = quote.content || {};
  const textHtml = escapeAndLinkify(content.text || "", content.expanded_urls || []);

  // 用户信息
  const name = quote.author?.name || "";
  const username = quote.author?.screen_name || "";
  const avatar = quote.author?.avatar?.path || "";

  // 媒体
  const mediaHtml = generateMediaHtml(quote.media, true);

  return `
    <div class="quote-tweet">
      <div class="tweet-header">
        <div class="user">
          <div style="display: flex; justify-content: center; align-items: center;">
            <img src="${avatar}" alt="Avatar" class="avatar">
          </div>
          <div class="user-info">
            <span class="name">${name}</span>
            <span class="username">@${username}</span>
          </div>
        </div>
        <span class="timestamp"></span>
      </div>
      <div class="tweet-content">${textHtml}</div>
      ${mediaHtml}
    </div>
  `;
}

function generateTweetHTML(tweet, index) {
  // 1) 用户信息
  const name = tweet.author?.name || "";
  const username = tweet.author?.screen_name || "";
  const avatar = tweet.author?.avatar?.path || "";

  // 2) 时间戳
  const createdAt = tweet.created_at || "";
  const timestamp = formatTimestamp(createdAt);

  // 3) 正文与翻译
  const contentText = tweet.content?.text || "";
  const expandedUrls = tweet.content?.expanded_urls || [];
  const contentHtml = escapeAndLinkify(contentText, expandedUrls);

  let translationHtml = "";
  if (tweet.content?.translation) {
    const translation = escapeAndLinkify(tweet.content.translation, expandedUrls);
    translationHtml = `
      <span id="trs">${translation}</span>
      <span id="trs-unsee">${translation}</span>
    `;
  }

  // 4) 媒体
  const mediaHtml = generateMediaHtml(tweet.media);

  // 5) 卡片
  const cardHtml = generateCardHtml(tweet.card);

  // 6) 引用
  const quoteHtml = generateQuoteHtml(tweet.quote);

  // 7) 翻译按钮
  let langTool = "";
  if (tweet.content?.translation) {
    langTool = `
      <div class="language">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18">
          <g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121">
            <path d="M2.25 4.25H10.25"></path>
            <path d="M6.25 2.25V4.25"></path>
            <path d="M4.25 4.25C4.341 6.926 6.166 9.231 8.75 9.934"></path>
            <path d="M8.25 4.25C7.85 9.875 2.25 10.25 2.25 10.25"></path>
            <path d="M9.25 15.75L12.25 7.75H12.75L15.75 15.75"></path>
            <path d="M10.188 13.25H14.813"></path>
          </g>
        </svg>
      </div>
    `;
  }

  // 8) 拼装最终 DOM
  return `
    <div class="tweet" id="${index}">
      <div class="tweet-header">
        <div class="user">
          <div style="display: flex; justify-content: center; align-items: center;">
            <img src="${avatar}" alt="Avatar" class="avatar">
          </div>
          <div class="user-info">
            <span class="name">${name}</span>
            <span class="username">@${username}</span>
          </div>
        </div>
        <span class="tool">
          ${langTool}
          <div class="pin">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18">
              <g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121">
                <path d="M10.371 15.553C10.803 14.996 11.391 14.083 11.719 12.835C11.888 12.193 11.949 11.611 11.962 11.134L14.967 8.129C15.748 7.348 15.748 6.082 14.967 5.301L12.699 3.033C11.918 2.252 10.652 2.252 9.87101 3.033L6.86601 6.038C6.38801 6.051 5.80701 6.112 5.16501 6.281C3.91701 6.609 3.00401 7.197 2.44701 7.629L10.372 15.554L10.371 15.553Z" fill="#212121" fill-opacity="0.3" data-stroke="none" stroke="none"></path>
                <path d="M3.08099 14.919L6.40899 11.591"></path>
                <path d="M10.371 15.553C10.803 14.996 11.391 14.083 11.719 12.835C11.888 12.193 11.949 11.611 11.962 11.134L14.967 8.129C15.748 7.348 15.748 6.082 14.967 5.301L12.699 3.033C11.918 2.252 10.652 2.252 9.87101 3.033L6.86601 6.038C6.38801 6.051 5.80701 6.112 5.16501 6.281C3.91701 6.609 3.00401 7.197 2.44701 7.629L10.372 15.554L10.371 15.553Z"></path>
              </g>
            </svg>
          </div>
        </span>
      </div>
      <div class="tweet-content">
        <span id="src">${contentHtml}</span>
        ${translationHtml}
      </div>
      ${mediaHtml}
      ${cardHtml}
      ${quoteHtml}
      <div style="margin-top: 8px">
        <div class="footer">
          <span class="timestamp">${timestamp}</span>
          <a
            href="https://twitter.com/${username}/status/${tweet.rest_id}"
            class="link2x"
            target="_blank"
          >
            View on Twitter
          </a>
        </div>
      </div>
    </div>
  `;
}


// =========================
// 懒加载、视频、翻译切换等逻辑
// （保留你原先的逻辑）
// =========================

function debounce(fn, delay) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

function isElementVisible(element, extraTop = 10000, extraBottom = 6500) {
  if (!element) return false;
  const rect = element.getBoundingClientRect();
  const windowTop = window.pageYOffset;
  const top = rect.top + windowTop;
  const bottom = rect.bottom + windowTop;
  const viewportTop = windowTop - extraTop;
  const viewportBottom = windowTop + window.innerHeight + extraBottom;
  return bottom >= viewportTop && top <= viewportBottom;
}

function loadNextChunk(chunkSize) {
  const nextChunk = all_data.slice(currentOffset, currentOffset + chunkSize);
  currentOffset += nextChunk.length;
  return nextChunk;
}

function addTweetsToColumns(tweets) {
  tweets.forEach((tweet, indexInBatch) => {
    const globalIndex = currentOffset - tweets.length + indexInBatch;
    const minColumnIndex = columnEnds.indexOf(Math.min(...columnEnds));

    // 1) 生成 tweet 的 HTML
    const tweetHTML = generateTweetHTML(tweet, globalIndex);

    // 2) 放进容器
    const tweetContainer = document.createElement("div");
    tweetContainer.id = `tweet-container-${globalIndex}`;
    tweetContainer.innerHTML = tweetHTML;

    // 3) 加入 DOM
    tweetsColumns[minColumnIndex].appendChild(tweetContainer);

    // 4) 观察
    renderedTweetIds.add(globalIndex);
    observeLanguage(tweetContainer);
    registerMonitoredTweet(globalIndex, tweetContainer);
    observeNewVideos(tweetContainer);

    columnEnds[minColumnIndex]++;
  });
}

function loadMoreTweets() {
  const tweets = loadNextChunk(chunkSize);
  if (tweets.length > 0) {
    addTweetsToColumns(tweets);
  }
}

function updateMonitoredMediaContainers() {
  const windowTop = window.pageYOffset;
  const windowBottom = windowTop + window.innerHeight;

  for (const tweetId in monitoredMediaContainers) {
    const { tweetContainer, mediaContainers } = monitoredMediaContainers[tweetId];
    const rect = tweetContainer.getBoundingClientRect();
    const tweetTop = rect.top + windowTop;
    const tweetBottom = rect.bottom + windowTop;

    if (tweetBottom >= windowTop && tweetTop <= windowBottom + 4000) {
      mediaContainers.forEach((mediaContainer) => {
        monitorMediaContainer(mediaContainer, tweetContainer, heightCache);
      });
      delete monitoredMediaContainers[tweetId];
    }
  }
}

function checkAndUpdateTweetVisibility() {
  renderedTweetIds.forEach((tweetId) => {
    const tweetContainer = document.getElementById(`tweet-container-${tweetId}`);
    const placeholder = document.getElementById(`placeholder-${tweetId}`);

    if (isElementVisible(tweetContainer)) {
      visibleTweets.set(tweetId, true);
    } else if (isElementVisible(placeholder)) {
      replaceWithTweet(placeholder);
      visibleTweets.set(tweetId, true);
    } else {
      if (visibleTweets.has(tweetId)) {
        if (tweetContainer) {
          replaceWithPlaceholder(tweetContainer);
        }
        visibleTweets.delete(tweetId);
      }
    }
  });
}

function monitorMediaContainer(mediaContainer, tweetContainer, heightCache) {
  const updateHeight = debounce(() => {
    const height = mediaContainer.getBoundingClientRect().height;
    if (heightCache.get(mediaContainer) !== height) {
      heightCache.set(mediaContainer, height);
    }
  }, 200);

  mediaContainer.querySelectorAll("img").forEach((img) => {
    if (!img.complete) {
      img.addEventListener("load", updateHeight, { once: true });
    }
  });

  mediaContainer.querySelectorAll("video").forEach((video) => {
    if (!video.readyState) {
      video.addEventListener("loadedmetadata", updateHeight, { once: true });
    }
  });

  const observer = new MutationObserver(updateHeight);
  observer.observe(mediaContainer, { childList: true });

  window.addEventListener("resize", updateHeight);
  updateHeight();
}

function registerMonitoredTweet(tweetId, tweetContainer) {
  const mediaContainers = Array.from(tweetContainer.querySelectorAll(".media-container"));
  if (mediaContainers.length > 0) {
    monitoredMediaContainers[tweetId] = {
      tweetContainer: tweetContainer,
      mediaContainers: mediaContainers,
    };
  }
}

// ========== 占位符与替换 ==========
function replaceWithPlaceholder(tweetContainer) {
  const tweetId = parseInt(tweetContainer.firstChild.id);
  if (placeholderMap[tweetId]) return;

  // 移除翻译按钮监听器
  const langButton = tweetContainer.querySelector(".language");
  if (langButton) {
    const handleLanguageToggle = languageListeners.get(langButton);
    if (handleLanguageToggle) {
      langButton.removeEventListener("click", handleLanguageToggle);
      languageListeners.delete(langButton);
    }
  }

  // 停止视频观察并释放资源
  const videos = tweetContainer.querySelectorAll("video");
  videos.forEach((video) => {
    if (observedVideos.has(video)) {
      videoObserver.unobserve(video);
      observedVideos.delete(video);
    }
    video.pause();
    video.src = "";
    video.load();
  });

  const height = parseFloat(tweetContainer.getBoundingClientRect().height.toFixed(3));
  const placeholder = document.createElement("div");
  placeholder.id = `placeholder-${tweetId}`;
  placeholder.style = `height:${height}px;width:${tweetContainer.offsetWidth}px;background-color:#f0f0f0;box-sizing:border-box;`;

  placeholderMap[tweetId] = { element: placeholder, height: height };
  tweetContainer.parentNode.replaceChild(placeholder, tweetContainer);
}

function replaceWithTweet(placeholder) {
  const tweetId = parseInt(placeholder.id.replace("placeholder-", ""));
  if (!all_data[tweetId] || !placeholderMap[tweetId]) return;

  // 重新生成 tweet
  const tweetHTML = generateTweetHTML(all_data[tweetId], tweetId);
  const tweetContainer = document.createElement("div");
  tweetContainer.id = `tweet-container-${tweetId}`;
  tweetContainer.innerHTML = tweetHTML;

  placeholder.parentNode.replaceChild(tweetContainer, placeholder);
  delete placeholderMap[tweetId];

  registerMonitoredTweet(tweetId, tweetContainer);
  observeNewVideos(tweetContainer);
  observeLanguage(tweetContainer);
}

// ========== 视频 IntersectionObserver ==========
function handleVideoIntersection(entries) {
  entries.forEach((entry) => {
    const video = entry.target;
    if (entry.isIntersecting) {
      if (video.paused || video.ended) {
        video.currentTime = 0;
      }
      video.loop = false;
      video.muted = true;
      video.play().catch(() => {});
    } else {
      if (!video.paused) {
        video.pause();
      }
    }
  });
}

function observeNewVideos(tweetContainer) {
  const videos = tweetContainer.querySelectorAll(".video-player, .quote-video-player");
  videos.forEach((video) => {
    videoObserver.observe(video);
    observedVideos.set(video, true);
  });
}

// ========== 语言切换处理 ==========
function observeLanguage(tweetContainer) {
  const langButton = tweetContainer.querySelector(".language");
  const srcSpan = tweetContainer.querySelector("#src");
  const trsSpan = tweetContainer.querySelector("#trs");
  const trsUnsee = tweetContainer.querySelector("#trs-unsee");
  const tweetContent = tweetContainer.querySelector(".tweet-content");

  if (!langButton || !srcSpan || !trsSpan || !trsUnsee || !tweetContent) return;

  trsSpan.style.display = "none";

  const measureHeight = (element) => (element ? element.offsetHeight : 0);

  const handleLanguageToggle = (e) => {
    e.preventDefault();
    e.stopPropagation();

    const showingSrc = srcSpan.style.display !== "none";
    if (showingSrc) {
      trsUnsee.style.display = "inline";
      const targetHeight = measureHeight(trsUnsee);
      trsUnsee.style.display = "none";

      const currentHeight = measureHeight(srcSpan);
      srcSpan.classList.add("smoke-out");

      if (currentHeight !== targetHeight) {
        tweetContent.style.height = currentHeight + "px";
        tweetContent.style.transition = "height 0.3s linear";
        requestAnimationFrame(() => {
          tweetContent.style.height = targetHeight + "px";
        });
      }

      const handleSrcOutEnd = () => {
        srcSpan.removeEventListener("animationend", handleSrcOutEnd);
        srcSpan.style.display = "none";
        srcSpan.classList.remove("smoke-out");

        if (currentHeight !== targetHeight) {
          tweetContent.style.transition = "";
          tweetContent.style.height = "";
        }

        trsSpan.style.display = "inline";
        trsSpan.classList.add("smoke-in");
        trsSpan.addEventListener("animationend", function handleTrsIn() {
          trsSpan.removeEventListener("animationend", handleTrsIn);
          trsSpan.classList.remove("smoke-in");
        }, { once: true });
      };

      srcSpan.addEventListener("animationend", handleSrcOutEnd, { once: true });
    } else {
      const currentHeight = measureHeight(trsSpan);
      srcSpan.style.display = "inline";
      const targetHeight = measureHeight(srcSpan);
      srcSpan.style.display = "none";

      trsSpan.classList.add("smoke-out");

      if (currentHeight !== targetHeight) {
        tweetContent.style.height = currentHeight + "px";
        tweetContent.style.transition = "height 0.3s linear";
        requestAnimationFrame(() => {
          tweetContent.style.height = targetHeight + "px";
        });
      }

      const handleTrsOutEnd = () => {
        trsSpan.removeEventListener("animationend", handleTrsOutEnd);
        trsSpan.style.display = "none";
        trsSpan.classList.remove("smoke-out");

        if (currentHeight !== targetHeight) {
          tweetContent.style.transition = "";
          tweetContent.style.height = "";
        }

        srcSpan.style.display = "inline";
        srcSpan.classList.add("smoke-in");
        srcSpan.addEventListener("animationend", function handleSrcIn() {
          srcSpan.removeEventListener("animationend", handleSrcIn);
          srcSpan.classList.remove("smoke-in");
        }, { once: true });
      };

      trsSpan.addEventListener("animationend", handleTrsOutEnd, { once: true });
    }
  };

  languageListeners.set(langButton, handleLanguageToggle);
  langButton.addEventListener("click", handleLanguageToggle);
}

// ========== Lightbox ==========
function handleMediaItemClick(img) {
  const lightbox = document.querySelector(".lightbox");
  const lightboxImg = lightbox.querySelector(".lightbox-img");

  lightboxImg.src = img.src;
  lightbox.style.display = "flex";

  const tweetContainer = document.querySelector(".tweets-container");
  const tweetContainerRect = tweetContainer.getBoundingClientRect();
  const tweetContainerLeft = tweetContainerRect.left + window.pageXOffset;
  tweetContainer.style.position = "absolute";
  tweetContainer.style.left = `${tweetContainerLeft}px`;

  requestAnimationFrame(() => {
    lightbox.classList.add("active");
    document.body.style.overflow = "hidden";
  });

  lightboxImg.classList.remove("zoomed");
  lightboxImg.style.width = "";
  lightboxImg.isZoomed = false;
}

function handleLightboxImageClick(e) {
  e.stopPropagation();
  const lightboxImg = e.target;
  const lightbox = lightboxImg.closest(".lightbox");
  lightboxImg.isZoomed = !lightboxImg.isZoomed;

  if (lightboxImg.isZoomed) {
    const width = Math.min(lightboxImg.naturalWidth, window.innerWidth * 0.98);
    const zoomedHeight = width * (lightboxImg.naturalHeight / lightboxImg.naturalWidth);
    if (zoomedHeight > window.innerHeight) {
      lightboxImg.classList.add("zoomed");
      lightboxImg.style.width = width + "px";
      lightboxImg.style.height = "auto";
      lightbox.classList.add("zoomed");
    }
  } else {
    lightboxImg.classList.remove("zoomed");
    lightbox.classList.remove("zoomed");
    lightboxImg.style.width = "";
    lightboxImg.style.height = "";
  }
}

function handleLightboxCloseClick(e) {
  const lightbox = e.target;
  const lightboxImg = lightbox.querySelector(".lightbox-img");
  if (e.target === lightbox) {
    lightbox.classList.remove("active");
    lightbox.classList.remove("zoomed");

    setTimeout(() => {
      lightbox.style.display = "none";
      lightboxImg.isZoomed = false;
      lightboxImg.classList.remove("zoomed");
      lightboxImg.style.width = "";
      lightboxImg.style.height = "";

      const tweetContainer = document.querySelector(".tweets-container");
      tweetContainer.style.position = "";
      tweetContainer.style.left = "";
      document.body.style.overflow = "";
    }, 300);
  }
}

// ========== DOMContentLoaded ==========
document.addEventListener("DOMContentLoaded", () => {
  // 创建 Lightbox 容器
  const lightbox = document.createElement("div");
  lightbox.className = "lightbox";
  const lightboxImg = document.createElement("img");
  lightboxImg.className = "lightbox-img";
  lightbox.appendChild(lightboxImg);
  document.body.appendChild(lightbox);

  // Lightbox事件
  lightboxImg.addEventListener("click", handleLightboxImageClick);
  lightbox.addEventListener("click", handleLightboxCloseClick);

  // 获取列容器
  tweetsColumns = document.querySelectorAll(".tweets-column");
  columnEnds = Array.from({ length: tweetsColumns.length }, () => 0);

  // 初始化 IntersectionObserver
  videoObserver = new IntersectionObserver(handleVideoIntersection, {
    root: null,
    rootMargin: "0px",
    threshold: 0.1,
  });

  // 初次加载 + 更新可见性
  loadMoreTweets();
  checkAndUpdateTweetVisibility();
  updateMonitoredMediaContainers();

  // 点击图片事件（显示 Lightbox）
  document.querySelector(".tweets-container").addEventListener("click", (event) => {
    const img = event.target.closest(".media-item, .quote-media-item");
    if (img) handleMediaItemClick(img);
  });

  // 滚动与 Resize 防抖
  const debouncedCheckVisibility = debounce(() => {
    checkAndUpdateTweetVisibility();
    updateMonitoredMediaContainers();
  }, 100);

  window.addEventListener("scroll", () => {
    debouncedCheckVisibility();
    // 当列底部接近视口底部时加载更多 tweets
    const minColumnBottom = Math.min(...Array.from(tweetsColumns).map(column => column.getBoundingClientRect().bottom));
    if (minColumnBottom <= window.innerHeight + 6000) {
      loadMoreTweets();
      updateMonitoredMediaContainers();
    }
  });

  window.addEventListener("resize", () => {
    debouncedCheckVisibility();
    updateMonitoredMediaContainers();
  });
});
"""

# --------------- 生成最终 HTML 的核心函数 ---------------

def generate_html(data: Dict, output_path: Path) -> None:
    """
    生成包含所有原始 tweet 数据 (仅改写了资源路径), 
    以及前端 JS/HTML/CSS 的完整 HTML 页面
    """
    # 从 data 中拿到 tweets
    tweets = data.get("results", [])

    # 确保输出目录存在
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) 处理所有 tweet 的资源路径 -> 相对 output_dir
    transformed_tweets = transform_all_tweets(tweets, output_dir)

    # 2) 计算 favicon 的相对路径（如果需要）
    assets_path = Path("assets") / "twitter.png"
    favicon_path = os.path.relpath(assets_path, output_dir).replace("\\", "/")
    if not assets_path.exists():
        print(f"Warning: Favicon file not found at {assets_path}")

    # 3) 将 transformed_tweets 转成 JSON，注入到 all_data
    all_data_json = json.dumps(transformed_tweets, ensure_ascii=False)

    # 4) 渲染最终完整 HTML
    full_html = FULL_HTML.format(
        all_data_json=all_data_json,
        html_styles=HTML_STYLES,
        render_script=RENDER_SCRIPT,
        favicon_path=favicon_path,
    )

    # 5) 写入输出文件
    output_path.write_text(full_html, encoding="utf-8")

# --------------- 示例入口 ---------------
if __name__ == "__main__":
    # 假设你已经有一个 data = {...}，其中包含 "results": [ ...tweets... ]
    # 以下只是示例，可自行替换
    example_data = {
        "results": [
            {
                "rest_id": "1234567890",
                "created_at": "Sat Dec 10 14:46:52 +0000 2022",
                "author": {
                    "name": "Alice",
                    "screen_name": "AliceInWonderland",
                    "avatar": {
                        "path": "/absolute/path/to/alice_avatar.jpg"
                    }
                },
                "content": {
                    "text": "Check out this cool picture!",
                    "expanded_urls": ["https://example.com/some-pic"],
                    "translation": "看看这张很酷的照片！",
                },
                "media": [
                    {
                        "type": "photo",
                        "path": "/absolute/path/to/pic1.jpg"
                    }
                ],
                "quote": {
                    "author": {
                        "name": "Bob",
                        "screen_name": "bob123",
                        "avatar": {
                            "path": "/absolute/path/to/bob_avatar.png"
                        }
                    },
                    "content": {
                        "text": "I am Bob!",
                        "expanded_urls": []
                    },
                    "media": [
                        {
                            "type": "video",
                            "path": "/absolute/path/to/bob_video.mp4"
                        }
                    ]
                },
                "card": {
                    "title": "Some Link Card Title",
                    "description": "Link description here",
                    "url": "https://example.com/some-link"
                }
            },
            # ... 其它 tweets ...
        ]
    }

    # 指定输出 HTML 的路径
    out_html = Path("output.html")

    # 调用生成函数
    generate_html(example_data, out_html)

    print(f"Done. HTML has been generated to {out_html.resolve()}")
