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
    <span class="timestamp"></span>
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
/**
 * IntersectionObserver回调：
 * entries: IntersectionObserverEntry数组
 * observer: IntersectionObserver实例
 */
const handleVideoIntersection = (entries, observer) => {
  entries.forEach((entry) => {
    const video = entry.target;

    // 判断是否在视口内
    if (entry.isIntersecting) {
      // 刚刚进入视口，自动播放，muted，loop=false
      if (video.paused || video.ended) {
        video.currentTime = 0;
      }
      video.loop = false;
      video.muted = true;
      video.play().catch(() => {});
    } else {
      // 刚刚离开视口，暂停视频
      if (!video.paused) {
        video.pause();
      }
    }
  });
};

let videoObserver = new IntersectionObserver(handleVideoIntersection, {
  root: null,
  rootMargin: "0px",
  threshold: 0.1, // 超过10%出现在视口中即判定为进入视口，可根据需求调整
});

/**
 * Debounces a function, ensuring it's only called after a specified delay.
 * @param {Function} fn - The function to debounce.
 * @param {number} delay - The delay in milliseconds.
 * @returns {Function} - The debounced function.
 */
const debounce = (fn, delay) => {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
};

const observeNewVideos = (tweetContainer) => {
  tweetContainer
    .querySelectorAll(".video-player, .quote-video-player")
    .forEach((video) => {
      videoObserver.observe(video);
    });
};

/**
 * Handles clicks on media items, displaying them in a lightbox.
 * @param {HTMLImageElement} img - The clicked image element.
 */
const handleMediaItemClick = (img) => {
  const lightbox = document.querySelector(".lightbox");
  const lightboxImg = lightbox.querySelector(".lightbox-img");

  lightboxImg.src = img.src;
  lightbox.style.display = "flex";

  // 获取并固定 tweets-container 的左边缘
  const tweetContainer = document.querySelector(".tweets-container");
  const tweetContainerRect = tweetContainer.getBoundingClientRect();
  const tweetContainerLeft = tweetContainerRect.left + window.pageXOffset;
  tweetContainer.style.position = "absolute";
  tweetContainer.style.left = `${tweetContainerLeft}px`;

  requestAnimationFrame(() => {
    lightbox.classList.add("active");
    document.body.style.overflow = "hidden";
  });

  // Reset zoom state
  lightboxImg.classList.remove("zoomed");
  lightboxImg.style.width = "";
  lightboxImg.isZoomed = false;
};

/**
 * Handles clicks on the lightbox image for zooming.
 * @param {MouseEvent} e - The click event.
 */
const handleLightboxImageClick = (e) => {
  e.stopPropagation(); // Prevent closing the lightbox

  const lightboxImg = e.target;
  const lightbox = lightboxImg.closest(".lightbox");

  lightboxImg.isZoomed = !lightboxImg.isZoomed;

  if (lightboxImg.isZoomed) {
    // Calculate zoomed size
    const width = Math.min(
      lightboxImg.naturalWidth,
      window.innerWidth * 0.98
    );
    const zoomedHeight =
      width * (lightboxImg.naturalHeight / lightboxImg.naturalWidth);

    // Zoom only if height exceeds viewport
    if (zoomedHeight > window.innerHeight) {
      lightboxImg.classList.add("zoomed");
      lightboxImg.style.width = width + "px";
      lightboxImg.style.height = "auto";
      lightbox.classList.add("zoomed");
    }
  } else {
    // Unzoom
    lightboxImg.classList.remove("zoomed");
    lightbox.classList.remove("zoomed");
    lightboxImg.style.width = "";
    lightboxImg.style.height = "";
  }
};

/**
 * Handles clicks on the lightbox overlay to close it.
 * @param {MouseEvent} e - The click event.
 */
const handleLightboxCloseClick = (e) => {
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

      // 恢复 tweets-container 的定位
      const tweetContainer = document.querySelector(".tweets-container");
      tweetContainer.style.position = "";
      tweetContainer.style.left = "";
      // 恢复滚动
      document.body.style.overflow = "";
    }, 300);
  }
};

/**
 * Chunks an array into smaller arrays of a specified size.
 * @param {Array} arr - The array to chunk.
 * @param {number} size - The chunk size.
 * @returns {Array[]} - An array of chunks.
 */
const chunkArray = (arr, size) =>
  arr.reduce(
    (chunks, item, i) =>
      i % size ? chunks : [...chunks, arr.slice(i, i + size)],
    []
  );

/**
 * Updates the height of a tweet container based on its media content (debounced).
 * @param {HTMLElement} mediaContainer - The media container.
 * @param {HTMLElement} tweetContainer - The tweet container.
 * @param {Map} heightCache - The height cache.
 */
const updateTweetContainerHeight = debounce(
  (mediaContainer, tweetContainer, heightCache) => {
    const height = mediaContainer.getBoundingClientRect().height;
    if (heightCache.get(mediaContainer) === height) return;
    heightCache.set(mediaContainer, height);
  },
  200
);

/**
 * Monitors a media container for changes and updates the tweet container's height.
 * @param {HTMLElement} mediaContainer - The media container.
 * @param {HTMLElement} tweetContainer - The tweet container.
 * @param {Map} heightCache - The height cache.
 */
const monitorMediaContainer = (
  mediaContainer,
  tweetContainer,
  heightCache
) => {
  const updateHeight = () =>
    updateTweetContainerHeight(
      mediaContainer,
      tweetContainer,
      heightCache
    );

  mediaContainer
    .querySelectorAll("img")
    .forEach(
      (img) => img.complete || img.addEventListener("load", updateHeight)
    );
  mediaContainer
    .querySelectorAll("video")
    .forEach(
      (video) =>
        video.readyState ||
        video.addEventListener("loadedmetadata", updateHeight)
    );

  new MutationObserver(updateHeight).observe(mediaContainer, {
    childList: true,
  });
  window.addEventListener("resize", updateHeight);
  updateHeight();
};

/**
 * Replaces a tweet container with a placeholder.
 * @param {HTMLElement} tweetContainer - The tweet container.
 * @param {Object} placeholderMap - The placeholder map.
 */
const replaceWithPlaceholder = (tweetContainer, placeholderMap) => {
  const tweetId = parseInt(tweetContainer.firstChild.id);
  if (placeholderMap[tweetId]) return;

  const height = parseFloat(
    tweetContainer.getBoundingClientRect().height.toFixed(3)
  );
  const placeholder = Object.assign(document.createElement("div"), {
    id: `placeholder-${tweetId}`,
    style: `height:${height}px;width:${tweetContainer.offsetWidth}px;background-color:#f0f0f0;box-sizing:border-box;`,
  });

  placeholderMap[tweetId] = { element: placeholder, height: height };
  tweetContainer.parentNode.replaceChild(placeholder, tweetContainer);
};

/**
 * 全局对象，用来存储需要监控的 Tweet，等到滚动或resize时再决定是否调用monitorMediaContainer。
 * 格式: monitoredMediaContainers[tweetId] = {tweetContainer: ..., mediaContainers: [...]}
 */
const monitoredMediaContainers = {};

/**
 * 注册一个tweetContainer到全局监视列表中
 * @param {number} tweetId
 * @param {HTMLElement} tweetContainer
 */
const registerMonitoredTweet = (tweetId, tweetContainer) => {
  const mediaContainers = Array.from(
    tweetContainer.querySelectorAll(".media-container")
  );
  if (mediaContainers.length > 0) {
    monitoredMediaContainers[tweetId] = {
      tweetContainer: tweetContainer,
      mediaContainers: mediaContainers,
    };
  }
};

/**
 * 检查已注册的tweetContainer是否在可监视范围内。
 * 若在范围内，则调用 monitorMediaContainer 开始监控，并从列表中移除该tweet。
 */
const updateMonitoredMediaContainers = (heightCache) => {
  const windowTop = window.pageYOffset;
  const windowBottom = windowTop + window.innerHeight;

  for (const tweetId in monitoredMediaContainers) {
    const { tweetContainer, mediaContainers } =
      monitoredMediaContainers[tweetId];
    const rect = tweetContainer.getBoundingClientRect();
    const tweetTop = rect.top + windowTop;
    const tweetBottom = rect.bottom + windowTop;

    if (tweetBottom >= windowTop && tweetTop <= windowBottom + 2000) {
      // 在扩展范围内，对其mediaContainers进行监测
      mediaContainers.forEach((mediaContainer) => {
        monitorMediaContainer(
          mediaContainer,
          tweetContainer,
          heightCache
        );
      });
      // 监控启动后，从列表中移除，以免重复添加事件
      delete monitoredMediaContainers[tweetId];
    }
  }
};

/**
 * Replaces a placeholder with the original tweet.
 * 在这里不直接调用 monitorMediaContainer，而是将其注册到全局列表中，等待updateMonitoredMediaContainers决定何时监控。
 * @param {HTMLElement} placeholder - The placeholder.
 * @param {Object} placeholderMap - The placeholder map.
 * @param {Array} all_data - All tweet data.
 * @param {Map} heightCache - The height cache.
 */
const replaceWithTweet = (
  placeholder,
  placeholderMap,
  all_data,
  heightCache
) => {
  const tweetId = parseInt(placeholder.id.replace("placeholder-", ""));
  if (!all_data[tweetId] || !placeholderMap[tweetId]) return;

  const tweetContainer = Object.assign(document.createElement("div"), {
    id: `tweet-container-${tweetId}`,
    innerHTML: all_data[tweetId].html,
  });
  tweetContainer.firstChild.id = tweetId;

  placeholder.parentNode.replaceChild(tweetContainer, placeholder);
  delete placeholderMap[tweetId];

  // 注册此 tweetContainer 到全局监视对象中，稍后由 updateMonitoredMediaContainers 决定何时实际监控
  registerMonitoredTweet(tweetId, tweetContainer);

  tweetContainer
    .querySelectorAll(".media-item")
    .forEach((img) =>
      img.addEventListener("click", () => handleMediaItemClick(img))
    );
  tweetContainer
    .querySelectorAll(".quote-media-item")
    .forEach((img) =>
      img.addEventListener("click", () => handleMediaItemClick(img))
    );
  observeNewVideos(tweetContainer);
};

/**
 * Checks and updates tweet visibility, using placeholders for off-screen tweets.
 * @param {Map} visibleTweets - Map of visible tweet IDs.
 * @param {Object} placeholderMap - Placeholder map.
 * @param {Array} all_data - All tweet data.
 * @param {Map} heightCache - Height cache.
 */
const checkAndUpdateTweetVisibility = (
  visibleTweets,
  placeholderMap,
  all_data,
  heightCache
) => {
  const EXPAND_RANGE = 10000;
  const windowTop = window.pageYOffset;
  const windowBottom = window.pageYOffset + window.innerHeight;
  const viewportTop = windowTop - EXPAND_RANGE;
  const viewportBottom = windowBottom + EXPAND_RANGE;

  const isElementVisible = (element) => {
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const top = rect.top + window.pageYOffset;
    const bottom = rect.bottom + window.pageYOffset;
    return bottom >= viewportTop && top <= viewportBottom;
  };

  for (let i = 0; i < all_data.length; i++) {
    const tweetContainer = document.getElementById(
      `tweet-container-${i}`
    );
    const placeholder = document.getElementById(`placeholder-${i}`);

    if (isElementVisible(tweetContainer)) {
      // 若 tweetContainer 已在可见范围内，则设为可见
      visibleTweets.set(i, true);
    } else if (isElementVisible(placeholder)) {
      // 若 placeholder 在范围内，则替换回实际 tweet
      replaceWithTweet(
        placeholder,
        placeholderMap,
        all_data,
        heightCache
      );
      visibleTweets.set(i, true);
    } else {
      // 若该 tweet 不在范围内且已标记为可见，则将其替换为占位符
      if (visibleTweets.has(i)) {
        if (tweetContainer)
          replaceWithPlaceholder(tweetContainer, placeholderMap);
        visibleTweets.delete(i);
      }
    }
  }
};

/**
 * Adds tweets to columns, distributing them evenly.
 * 在这里也不直接调用 monitorMediaContainer，而是在替换时再注册。
 * @param {Array} tweets - Tweet data.
 * @param {NodeList} tweetsColumns - Tweet column elements.
 * @param {number[]} columnEnds - Next tweet index for each column.
 * @param {number} chunkIndex - Current chunk index.
 * @param {number} chunkSize - Chunk size.
 * @param {Map} heightCache - Height cache.
 */
const addTweetsToColumns = (
  tweets,
  tweetsColumns,
  columnEnds,
  chunkIndex,
  chunkSize,
  heightCache
) => {
  tweets.forEach((tweet, index) => {
    const minColumnIndex = columnEnds.indexOf(Math.min(...columnEnds));
    const tweetId = chunkIndex * chunkSize + index;
    const tweetContainer = Object.assign(document.createElement("div"), {
      id: `tweet-container-${tweetId}`,
      innerHTML: tweet.html,
    });
    tweetContainer.firstChild.id = tweetId;

    tweetsColumns[minColumnIndex].appendChild(tweetContainer);
    // 注册此 tweetContainer 到监视列表
    registerMonitoredTweet(tweetId, tweetContainer);

    tweetContainer
      .querySelectorAll(".media-item")
      .forEach((img) =>
        img.addEventListener("click", () => handleMediaItemClick(img))
      );
    tweetContainer
      .querySelectorAll(".quote-media-item")
      .forEach((img) =>
        img.addEventListener("click", () => handleMediaItemClick(img))
      );
    observeNewVideos(tweetContainer);
    columnEnds[minColumnIndex]++;
  });
};

/**
 * Loads more tweets and adds them to the columns.
 * @param {Array[][]} chunkedTweetsData - Chunked tweet data.
 * @param {number} chunkIndex - Current chunk index.
 * @param {NodeList} tweetsColumns - Tweet column elements.
 * @param {number[]} columnEnds - Next tweet index for each column.
 * @param {number} chunkSize - Chunk size.
 * @param {Map} heightCache - Height cache.
 * @returns {number} Updated chunk index.
 */
const loadMoreTweets = (
  chunkedTweetsData,
  chunkIndex,
  tweetsColumns,
  columnEnds,
  chunkSize,
  heightCache
) => {
  if (chunkIndex < chunkedTweetsData.length) {
    addTweetsToColumns(
      chunkedTweetsData[chunkIndex],
      tweetsColumns,
      columnEnds,
      chunkIndex,
      chunkSize,
      heightCache
    );
    return chunkIndex + 1;
  }
  return chunkIndex;
};

document.addEventListener("DOMContentLoaded", () => {
  const lightbox = Object.assign(document.createElement("div"), {
    className: "lightbox",
  });
  const lightboxImg = Object.assign(document.createElement("img"), {
    className: "lightbox-img",
  });
  lightbox.appendChild(lightboxImg);
  document.body.appendChild(lightbox);

  lightboxImg.addEventListener("click", handleLightboxImageClick);
  lightbox.addEventListener("click", handleLightboxCloseClick);

  const tweetsColumns = document.querySelectorAll(".tweets-column");
  const chunkSize = 30;
  let chunkIndex = 0;
  const columnEnds = Array(tweetsColumns.length).fill(0);
  const placeholderMap = {};
  const visibleTweets = new Map();
  const heightCache = new Map();

  // 请确保 all_data 已在全局定义，包含所有的 tweets 数据
  const chunkedTweetsData = chunkArray(all_data, chunkSize);

  const debouncedCheckVisibility = debounce(() => {
    checkAndUpdateTweetVisibility(
      visibleTweets,
      placeholderMap,
      all_data,
      heightCache
    );
    updateMonitoredMediaContainers(heightCache); // 在检查可见性后更新监控状态
  }, 100);

  // 初始加载 tweets
  chunkIndex = loadMoreTweets(
    chunkedTweetsData,
    chunkIndex,
    tweetsColumns,
    columnEnds,
    chunkSize,
    heightCache
  );
  checkAndUpdateTweetVisibility(
    visibleTweets,
    placeholderMap,
    all_data,
    heightCache
  );
  updateMonitoredMediaContainers(heightCache);

  window.addEventListener("scroll", () => {
    debouncedCheckVisibility();
    // 如果列底部接近视口底部，则加载更多 tweets
    if (
      Math.min(
        ...Array.from(tweetsColumns).map(
          (column) => column.getBoundingClientRect().bottom
        )
      ) <=
      window.innerHeight + 4000
    ) {
      chunkIndex = loadMoreTweets(
        chunkedTweetsData,
        chunkIndex,
        tweetsColumns,
        columnEnds,
        chunkSize,
        heightCache
      );
      updateMonitoredMediaContainers(heightCache);
    }
  });

  window.addEventListener("resize", () => {
    debouncedCheckVisibility();
    updateMonitoredMediaContainers(heightCache);
  });
});
"""

HTML_STYLES = """
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
"""


def format_timestamp(timestamp: str, format="%Y-%m-%d %H:%M") -> str:
    """格式化时间戳"""
    if not timestamp:
        return ""
    time_format = "%a %b %d %H:%M:%S %z %Y"
    local_tz = datetime.now().astimezone().tzinfo
    parsed_time = datetime.strptime(timestamp, time_format)
    return parsed_time.astimezone(local_tz).strftime(format)


def format_content_with_links(content: Dict) -> str:
    """将文本中的URL替换为HTML链接"""
    if not content:
        return ""

    text: str = html.escape(content.get("text", ""))
    expanded_urls = content.get("expanded_urls", [])

    for url in expanded_urls:
        link_text = os.path.basename(url) or url
        html_link = f'<a href="{url}" target="_blank" class="link">{link_text}</a>'
        text = text.replace(url, html_link)

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
        if (c := format_content_with_links(quote.get("content")))
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
    content_html = (
        f"""<div class="tweet-content">{c}</div>"""
        if (c := format_content_with_links(tweet.get("content")))
        else ""
    )
    avatar = get_relative_path(get(tweet, "author.avatar.path"), output_dir)
    media_html = generate_media_html(tweet.get("media", []), output_dir)
    quote_html = generate_quote_html(tweet.get("quote"), output_dir)
    tweet_id = tweet.get("rest_id", "")
    card_html = generate_card_html(tweet.get("card"))

    return TWEET_TEMPLATE.format(
        name=name,
        username=username,
        timestamp=timestamp,
        content=content_html,
        avatar=avatar,
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
