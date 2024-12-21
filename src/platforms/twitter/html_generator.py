import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

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
TWEET_TEMPLATE = """<div class="tweet" id="{index}">
  <div class="tweet-header">
    <div class="user">
        <div style="display: flex; justify-content: center; align-items: center;">
            <img src="{avatar}" alt="Avatar" class="avatar">
        </div>
        <div class="user-info">
            <span class="name">{name}</span><span class="username">@{username}</span>
        </div>
    </div>
    <span class="tool">
      {lang_tool}
      <div class="pin">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18"><g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121"><path d="M10.371 15.553C10.803 14.996 11.391 14.083 11.719 12.835C11.888 12.193 11.949 11.611 11.962 11.134L14.967 8.129C15.748 7.348 15.748 6.082 14.967 5.301L12.699 3.033C11.918 2.252 10.652 2.252 9.87101 3.033L6.86601 6.038C6.38801 6.051 5.80701 6.112 5.16501 6.281C3.91701 6.609 3.00401 7.197 2.44701 7.629L10.372 15.554L10.371 15.553Z" fill="#212121" fill-opacity="0.3" data-stroke="none" stroke="none"></path> <path d="M3.08099 14.919L6.40899 11.591"></path> <path d="M10.371 15.553C10.803 14.996 11.391 14.083 11.719 12.835C11.888 12.193 11.949 11.611 11.962 11.134L14.967 8.129C15.748 7.348 15.748 6.082 14.967 5.301L12.699 3.033C11.918 2.252 10.652 2.252 9.87101 3.033L6.86601 6.038C6.38801 6.051 5.80701 6.112 5.16501 6.281C3.91701 6.609 3.00401 7.197 2.44701 7.629L10.372 15.554L10.371 15.553Z"></path></g></svg>
      </div>
    </span>
  </div>
  {content}
  {media_html}{card_html}{quote_html}
  <div style="margin-top: 8px">
    <div class="footer">
      <span class="timestamp">{timestamp}</span>
      <a
        href="https://twitter.com/{username}/status/{tweet_id}"
        class="link2x"
        target="_blank"
        >View on Twitter</a
      >
    </div>
  </div>
</div>
"""
SCRIPT = """
// =========================
// 全局常量与变量定义
// =========================

// 所有 tweet 数据应在全局已有 all_data 数组
// all_data: Array<{ html: string, ... }>

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
// 工具函数
// =========================

/**
 * 防抖函数：在最后一次调用后的指定延迟后执行fn
 * @param {Function} fn 
 * @param {number} delay 
 * @returns {Function}
 */
function debounce(fn, delay) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

/**
 * 判断元素是否在可视区域内（包含一定的上下扩展范围）
 * @param {HTMLElement} element 
 * @param {number} extraTop - 视口顶部额外扩展
 * @param {number} extraBottom - 视口底部额外扩展
 * @returns {boolean}
 */
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


// =========================
// Tweet 数据加载与可见性控制
// =========================

/**
 * 从 all_data 中加载下一批 tweets。
 * @param {number} chunkSize - 每批次加载的数量。
 * @returns {Array} - 当前批次的 tweet 数据
 */
function loadNextChunk(chunkSize) {
  const nextChunk = all_data.slice(currentOffset, currentOffset + chunkSize);
  currentOffset += nextChunk.length;
  return nextChunk;
}

/**
 * 将一批 tweets 添加到列中，均匀分布。
 * @param {Array} tweets - 当前批次的 tweets 数据（含 html 字段）
 */
function addTweetsToColumns(tweets) {
  tweets.forEach((tweet, index) => {
    const minColumnIndex = columnEnds.indexOf(Math.min(...columnEnds));
    const tweetId = currentOffset - tweets.length + index;

    const tweetContainer = document.createElement("div");
    tweetContainer.id = `tweet-container-${tweetId}`;
    tweetContainer.innerHTML = tweet.html;

    if (tweetContainer.firstChild) {
      tweetContainer.firstChild.id = tweetId;
    }

    renderedTweetIds.add(tweetId);
    observeLanguage(tweetContainer);
    tweetsColumns[minColumnIndex].appendChild(tweetContainer);
    registerMonitoredTweet(tweetId, tweetContainer);
    observeNewVideos(tweetContainer);

    columnEnds[minColumnIndex]++;
  });
}

/**
 * 加载更多的 tweets 并添加到列中。
 */
function loadMoreTweets() {
  const tweets = loadNextChunk(chunkSize);
  if (tweets.length > 0) {
    addTweetsToColumns(tweets);
  }
}

/**
 * 更新已监控的媒体容器：如果它们进入可监视范围，则开始监听高度变化等
 */
function updateMonitoredMediaContainers() {
  const windowTop = window.pageYOffset;
  const windowBottom = windowTop + window.innerHeight;

  for (const tweetId in monitoredMediaContainers) {
    const { tweetContainer, mediaContainers } = monitoredMediaContainers[tweetId];
    const rect = tweetContainer.getBoundingClientRect();
    const tweetTop = rect.top + windowTop;
    const tweetBottom = rect.bottom + windowTop;

    // 进入可监视范围：tweetBottom >= windowTop && tweetTop <= windowBottom + 4000
    if (tweetBottom >= windowTop && tweetTop <= windowBottom + 4000) {
      mediaContainers.forEach((mediaContainer) => {
        monitorMediaContainer(mediaContainer, tweetContainer, heightCache);
      });
      delete monitoredMediaContainers[tweetId];
    }
  }
}

/**
 * 检查并更新已渲染的 tweet 的可见性，使用占位符替代不可见的 tweet。
 */
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


// =========================
// 媒体容器与高度监控
// =========================

/**
 * 监控 mediaContainer 的大小变化，更新对应 tweetContainer 的高度缓存。
 */
function monitorMediaContainer(mediaContainer, tweetContainer, heightCache) {
  const updateHeight = debounce(() => {
    const height = mediaContainer.getBoundingClientRect().height;
    if (heightCache.get(mediaContainer) !== height) {
      heightCache.set(mediaContainer, height);
    }
  }, 200);

  // 对 mediaContainer 中的资源加载进行监听
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

  // MutationObserver 用于监听子元素变更
  const observer = new MutationObserver(updateHeight);
  observer.observe(mediaContainer, { childList: true });

  // 窗口大小变化时也更新
  window.addEventListener("resize", updateHeight);
  updateHeight();
}

/**
 * 注册一个 tweetContainer 到全局监视列表中
 * 在后续滚动或 resize 时检查其是否需要开始 monitorMediaContainer
 */
function registerMonitoredTweet(tweetId, tweetContainer) {
  const mediaContainers = Array.from(tweetContainer.querySelectorAll(".media-container"));
  if (mediaContainers.length > 0) {
    monitoredMediaContainers[tweetId] = {
      tweetContainer: tweetContainer,
      mediaContainers: mediaContainers,
    };
  }
}


// =========================
// Tweet 占位符与替换
// =========================

/**
 * 用占位符替换一个不在可见范围内的 tweetContainer。
 */
function replaceWithPlaceholder(tweetContainer) {
  const tweetId = parseInt(tweetContainer.firstChild.id);
  if (placeholderMap[tweetId]) return;

  // 移除语言按钮监听器
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

/**
 * 将占位符替换回原始的 tweet。
 */
function replaceWithTweet(placeholder) {
  const tweetId = parseInt(placeholder.id.replace("placeholder-", ""));
  if (!all_data[tweetId] || !placeholderMap[tweetId]) return;

  const tweetContainer = document.createElement("div");
  tweetContainer.id = `tweet-container-${tweetId}`;
  tweetContainer.innerHTML = all_data[tweetId].html;
  tweetContainer.firstChild.id = tweetId;

  placeholder.parentNode.replaceChild(tweetContainer, placeholder);
  delete placeholderMap[tweetId];

  registerMonitoredTweet(tweetId, tweetContainer);
  observeNewVideos(tweetContainer);
  observeLanguage(tweetContainer);
}


// =========================
// 视频 IntersectionObserver
// =========================

function handleVideoIntersection(entries) {
  entries.forEach((entry) => {
    const video = entry.target;
    if (entry.isIntersecting) {
      // 进入视口自动播放
      if (video.paused || video.ended) {
        video.currentTime = 0;
      }
      video.loop = false;
      video.muted = true;
      video.play().catch(() => {});
    } else {
      // 离开视口暂停
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


// =========================
// 语言切换处理
// =========================

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
      // 切换到 trs
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
      // 切换回 src
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


// =========================
// Lightbox 图片放大预览
// =========================

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


// =========================
// DOMContentLoaded 事件初始化
// =========================

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

  // 初次加载与更新可见性
  loadMoreTweets();
  checkAndUpdateTweetVisibility();
  updateMonitoredMediaContainers();

  // 点击媒体事件（显示Lightbox）
  document.querySelector(".tweets-container").addEventListener("click", (event) => {
    const img = event.target.closest(".media-item, .quote-media-item");
    if (img) handleMediaItemClick(img);
  });

  // 滚动与Resize防抖事件
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

HTML_STYLES = """
    body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #f5f8fa;
            margin: 0;
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
        .tweet {
            background: white;
            border: 1px solid #e1e8ed;
            border-radius: 8px;
            padding: 12px;
            font-size: 14px;
            display: flex;
            flex-direction: column;
        }
        .tool {
            display: flex;
            gap: 2px;
        }
        .tweet .tool {
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        .tweet:hover .tool {
            opacity: 1;
        }
        .tweet:hover .tool > div {
            opacity: 0.6;
        }
        .tool .language, .tool .pin {
            width: 24px;
            height: 24px;
            border-radius: 4px;
            transition: all 0.2s ease;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            user-select: none;
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
        }

        .tool .language:hover, .tool .pin:hover {
            opacity: 0.9 !important;
            background-color: rgba(0, 0, 0, 0.05);

        }
        .tweets-column {
            display: flex;
            flex-direction: column;
            gap: 15px;
            max-width: 390px;
            align-self: flex-start;
        }
        .tweet-header {
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }
        .footer {
            margin-top: 2px;
            display: flex;
            justify-content: space-between;
            align-items: center;
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
            position: relative;
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
        .quote-video-player {
            width: 100%;
            border-radius: 4px;
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
        .card {
            border-radius: 8px;
            padding: 10px;
            margin: 8px 0;
            font-size: 0.95em;
            transition: all 0.2s ease-in-out;
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
            transition: opacity 0.3s ease;
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
        .avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            object-fit: cover;
        }
        .user {
            display: flex;
            gap: 8px;
        }
        .text-container {
            position: relative;
            overflow: hidden;
            transition: height 0.3s ease;
        }
"""


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


def generate_media_html(medias: List[Dict], output_dir: Path, is_quote=False) -> str:
    if not medias:
        return ""

    media_items = []
    for media in medias:
        path = media.get("path")
        if path == "media unavailable":
            media_items.append('<div class="media-unavailable">Media Unavailable</div>')
        elif path:
            rel_path = get_relative_path(path, output_dir)
            media_type = media.get("type")
            if media_type == "video":
                # 普通视频：不自动播放，不循环，不静音，使用JS控制
                poster = media.get("thumb_path", "")
                if poster:
                    poster = get_relative_path(poster, output_dir)

                aspect_ratio = media.get("aspect_ratio", [16, 9])
                ratio = aspect_ratio[1] / aspect_ratio[0]
                padding_bottom = min(ratio * 100, 100)

                media_items.append(
                    f'<div class="video-container" style="position: relative; padding-bottom: {padding_bottom}%;">'
                    f'<video class="{"video-player" if not is_quote else "quote-video-player"}" controls preload="none" playsinline poster="{poster}" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">'
                    f'<source src="{rel_path}" type="video/mp4">Your browser does not support video.'
                    f"</video></div>"
                )
            elif media_type == "animated_gif":
                # animated_gif：保持原有行为，autoplay、loop、muted、playsinline
                aspect_ratio = media.get("aspect_ratio", [16, 9])
                ratio = aspect_ratio[1] / aspect_ratio[0]
                padding_bottom = min(ratio * 100, 100)

                media_items.append(
                    f'<div class="video-container" style="position: relative; padding-bottom: {padding_bottom}%;">'
                    f'<video class="animated-gif-player" autoplay loop muted playsinline preload="auto" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">'
                    f'<source src="{rel_path}" type="video/mp4">Your browser does not support video.'
                    f"</video></div>"
                )
            else:
                # 图片
                media_items.append(
                    f'<img class="{"media-item" if not is_quote else "quote-media-item"}" src="{rel_path}" loading="lazy" />'
                )

    return (
        f'<div class="media-container">{"".join(media_items)}</div>'
        if media_items
        else ""
    )


def generate_card_html(card: Dict) -> str:
    if not card:
        return ""

    title = card.get("title") or ""
    description = card.get("description") or ""
    url = card.get("url")
    return f"""
    <a href="{url}" style="text-decoration: none; color: inherit;" target="_blank">
      <div class="card" style="cursor: pointer; padding: 10px; border: 1px solid #e1e8ed; border-radius: 8px; margin-bottom: 10px;">
        <div style="font-size: 12px; font-weight: bold;">
          {title}
        </div>
        {description and f'<div style="font-size: 10px; color: #536471; margin-top: 5px;">{description}</div>'}
      </div>
    </a>
    """


def generate_quote_html(quote: Dict, output_dir: Path) -> str:
    """生成引用推文的 HTML"""
    if not quote:
        return ""
    content_html = (
        f"""<div class="tweet-content">{c}</div>"""
        if (
            c := format_content_with_links(
                get(quote, "content.text"), get(quote, "content.expanded_urls")
            )
        )
        else ""
    )
    name = get(quote, "author.name")
    username = get(quote, "author.screen_name")
    avatar = get_relative_path(get(quote, "author.avatar.path"), output_dir)
    # timestamp = format_timestamp(quote.get("created_at"), format="%m-%d %H:%M")
    media_html = generate_media_html(quote.get("media", []), output_dir, is_quote=True)
    return f"""
    <div class="quote-tweet">
        <div class="tweet-header">
            <div class="user">
                <div style="display: flex; justify-content: center; align-items: center;">
                    <img src="{avatar}" alt="Avatar" class="avatar">
                </div>
                <div class="user-info">
                    <span class="name">{name}</span>
                    <span class="username">@{username}</span>
                </div>
            </div>
            <span class="timestamp"></span>
        </div>
        {content_html}
        {media_html}
    </div>
    """


def generate_tweet_html(tweet: Dict, output_dir: Path, index: int) -> str:
    """生成单条推文的 HTML"""
    name = get(tweet, "author.name")
    username = get(tweet, "author.screen_name")
    timestamp = format_timestamp(tweet.get("created_at"))
    translate_text_html = (
        f"<span id='trs'>{t}</span><span id='trs-unsee'>{t}</span>"
        if (
            t := format_content_with_links(
                get(tweet, "content.translation"), get(tweet, "content.expanded_urls")
            )
        )
        else ""
    )
    content_html = (
        f"""<div class="tweet-content"><span id="src">{c}</span>{translate_text_html}</div>"""
        if (
            c := format_content_with_links(
                get(tweet, "content.text"), get(tweet, "content.expanded_urls")
            )
        )
        else ""
    )
    avatar = get_relative_path(get(tweet, "author.avatar.path"), output_dir)
    media_html = generate_media_html(tweet.get("media", []), output_dir)
    quote_html = generate_quote_html(tweet.get("quote"), output_dir)
    tweet_id = tweet.get("rest_id", "")
    card_html = generate_card_html(tweet.get("card"))
    lang_tool = (
        """<div class="language">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18"><g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121"><path d="M2.25 4.25H10.25"></path> <path d="M6.25 2.25V4.25"></path> <path d="M4.25 4.25C4.341 6.926 6.166 9.231 8.75 9.934"></path> <path d="M8.25 4.25C7.85 9.875 2.25 10.25 2.25 10.25"></path> <path d="M9.25 15.75L12.25 7.75H12.75L15.75 15.75"></path> <path d="M10.188 13.25H14.813"></path></g></svg>
      </div>"""
        if get(tweet, "content.translation")
        else ""
    )

    return TWEET_TEMPLATE.format(
        name=name,
        username=username,
        timestamp=timestamp,
        content=content_html,
        avatar=avatar,
        lang_tool=lang_tool,
        media_html=media_html,
        quote_html=quote_html,
        card_html=card_html,
        tweet_id=tweet_id,
        index=index,
    )


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

    all_tweets_html = []
    for i, tweet in enumerate(tweets):
        tweet_html = generate_tweet_html(tweet, output_dir, i)
        all_tweets_html.append({"html": tweet_html})

    full_html = FULL_HTML.format(
        all_data=json.dumps(all_tweets_html, ensure_ascii=False),
        html_styles=HTML_STYLES,
        script=SCRIPT,
        favicon_path=favicon_path,
    )
    # 写入文件
    output_path.write_text(full_html, encoding="utf-8")
