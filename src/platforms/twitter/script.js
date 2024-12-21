// =========================
// 全局常量与变量定义
// =========================
let currentOffset = 0; // 已经从 all_data 中加载的偏移量
const chunkSize = 30; // 每批加载的 tweet 数量
const renderedTweetIds = new Set(); // 已经渲染到页面中的 tweet ID
const monitoredMediaContainers = {}; // 存储需要监控的 Tweet 媒体容器
const observedVideos = new WeakMap(); // 记录被 IntersectionObserver 观察的 video
const languageListeners = new WeakMap(); // 记录语言切换按钮监听器
const placeholderMap = {}; // 存储占位符相关信息
const visibleTweets = new Map(); // 存储当前可见的 tweets
const heightCache = new Map(); // 缓存 media container 的高度信息

let tweetsColumns; // 在DOMContentLoaded后初始化
let columnEnds; // 每列当前的 tweet 数量记录

// IntersectionObserver 用于视频自动播放
let videoObserver = null;

// =========================
// icon
// =========================

const language = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18" > <g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121" > <path d="M2.25 4.25H10.25"></path> <path d="M6.25 2.25V4.25"></path> <path d="M4.25 4.25C4.341 6.926 6.166 9.231 8.75 9.934"></path> <path d="M8.25 4.25C7.85 9.875 2.25 10.25 2.25 10.25"></path> <path d="M9.25 15.75L12.25 7.75H12.75L15.75 15.75"></path> <path d="M10.188 13.25H14.813"></path> </g> </svg>`;
const pin = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18" > <g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121" > <path d="M10.371 15.553C10.803 14.996 11.391 14.083 11.719 12.835C11.888 12.193 11.949 11.611 11.962 11.134L14.967 8.129C15.748 7.348 15.748 6.082 14.967 5.301L12.699 3.033C11.918 2.252 10.652 2.252 9.87101 3.033L6.86601 6.038C6.38801 6.051 5.80701 6.112 5.16501 6.281C3.91701 6.609 3.00401 7.197 2.44701 7.629L10.372 15.554L10.371 15.553Z" fill="#212121" fill-opacity="0.3" data-stroke="none" stroke="none" ></path> <path d="M3.08099 14.919L6.40899 11.591"></path> <path d="M10.371 15.553C10.803 14.996 11.391 14.083 11.719 12.835C11.888 12.193 11.949 11.611 11.962 11.134L14.967 8.129C15.748 7.348 15.748 6.082 14.967 5.301L12.699 3.033C11.918 2.252 10.652 2.252 9.87101 3.033L6.86601 6.038C6.38801 6.051 5.80701 6.112 5.16501 6.281C3.91701 6.609 3.00401 7.197 2.44701 7.629L10.372 15.554L10.371 15.553Z"></path> </g> </svg>`;

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
// 生成单条 Tweet HTML
// =========================
function showLangIcon(tweet) {
  if (!tweet.content.translation) return "";
  return `<div class="language">${language}</div>`;
}
function generateTranslationHtml(content) {
  if (!content.translation) return "";
  return `<span id="trs">${content.translation}</span>`;
}
function generateSourceHtml(content) {
  return `<span id="src">${content.text}</span>`;
}
function showContent(tweet) {
  if (!tweet.content.text) return "";
  return `<div class="tweet-content">${generateSourceHtml(
    tweet.content
  )}${generateTranslationHtml(tweet.content)}</div>`;
}
function generateMediaHtml(media, isQuote = false) {
  if (media.path === "media unavailable")
    return `<div class="media-unavailable">Media Unavailable</div>`;
  switch (media.type) {
    case "photo":
      return `<img class="${
        isQuote ? "quote-media-item" : "media-item"
      }" src="${media.path}" loading="lazy" />`;
    case "video":
      return `<div class="video-container" style="${`position: relative; padding-bottom: ${Math.min(
        ((media.aspect_ratio?.[1] ?? 9) / (media.aspect_ratio?.[0] ?? 16)) *
          100,
        100
      )}%`}" > <video class="${
        isQuote ? "quote-video-player" : "video-player"
      }" controls preload="none" playsinline poster="${
        media.thumb_path
      }" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"> <source src="${
        media.path
      }" type="video/mp4" /> Your browser does not support video. </video> </div>`;
    case "animated_gif":
      return `<div class="video-container" style="${`position: relative; padding-bottom: ${Math.min(
        ((media.aspect_ratio?.[1] ?? 9) / (media.aspect_ratio?.[0] ?? 16)) *
          100,
        100
      )}%`}" > <video class="${
        isQuote ? "quote-animated-gif-player" : "animated-gif-player"
      }" autoplay loop muted playsinline preload="auto" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;" > <source src="${
        media.path
      }" type="video/mp4" /> Your browser does not support video. </video> </div>`;
  }
}
function showMedia(tweet, isQuote = false) {
  if (!tweet.media) return "";
  return `<div class="media-container">${tweet.media
    .map((media) => generateMediaHtml(media, isQuote))
    .join("")}</div>`;
}
function showCard(card) {
  if (!card) return "";
  return `<a href="${
    card.url
  }" style="text-decoration: none; color: inherit;" target="_blank" > <div class="card" style="cursor: pointer; padding: 10px; border: 1px solid #e1e8ed; border-radius: 8px; margin-bottom: 10px;" > <div style="font-size: 12px; font-weight: bold;"> ${
    card.title
  } </div> ${
    card.description
      ? `<div style="font-size: 10px; color: #536471; margin-top: 5px;"> ${card.description} </div>`
      : ""
  } </div> </a>`;
}
function showQuote(qtweet) {
  if (!qtweet) return "";
  return `<div class="quote-tweet"> <div class="tweet-header"> <div class="user"> <div style="display: flex; justify-content: center; align-items: center;"> <img src="${
    qtweet.author.avatar.path
  }" alt="Avatar" class="avatar"/> </div> <div class="user-info"> <span class="name">${
    qtweet.author.name
  }</span> <span class="username">@${
    qtweet.author.screen_name
  }</span> </div> </div> <span class="timestamp"></span> </div> ${showContent(
    qtweet
  )} ${showMedia(qtweet, true)} </div>`;
}
function generateTweetHTML(tweet, index) {
  return `<div class="tweet" id="${index}"> <div class="tweet-header"> <div class="user"> <div style="display: flex; justify-content: center; align-items: center;"> <img src="${
    tweet.author.avatar.path
  }" alt="Avatar" class="avatar" > </div> <div class="user-info"> <span class="name">${
    tweet.author.name
  }</span> <span class="username">@${
    tweet.author.screen_name
  }</span> </div> </div> <span class="tool"> ${showLangIcon(
    tweet
  )} <div class="pin">${pin}</div> </span> </div> ${showContent(
    tweet
  )} ${showMedia(tweet)} ${showCard(tweet.card)} ${showQuote(
    tweet.quote
  )} <div style="margin-top: 8px"> <div class="footer"> <span class="timestamp">${
    tweet.created_at
  }</span> <a href="${
    tweet.url
  }" class="link2x" target="_blank"> View on Twitter </a> </div> </div> </div>`;
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
    tweetContainer.innerHTML = generateTweetHTML(tweet, tweetId);

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
    const { tweetContainer, mediaContainers } =
      monitoredMediaContainers[tweetId];
    const rect = tweetContainer.getBoundingClientRect();
    const tweetTop = rect.top + windowTop;
    const tweetBottom = rect.bottom + windowTop;

    // 进入可监视范围：tweetBottom >= windowTop && tweetTop <= windowBottom + 4000
    if (tweetBottom >= windowTop && tweetTop <= windowBottom + 4000) {
      for (const mediaContainer of mediaContainers) {
        monitorMediaContainer(mediaContainer, tweetContainer, heightCache);
      }
      delete monitoredMediaContainers[tweetId];
    }
  }
}

/**
 * 检查并更新已渲染的 tweet 的可见性，使用占位符替代不可见的 tweet。
 */
function checkAndUpdateTweetVisibility() {
  for (const tweetId in renderedTweetIds) {
    const tweetContainer = document.getElementById(
      `tweet-container-${tweetId}`
    );
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
  }
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
  for (const img of mediaContainer.querySelectorAll("img")) {
    if (!img.complete) {
      img.addEventListener("load", updateHeight, { once: true });
    }
  }

  for (const video of mediaContainer.querySelectorAll("video")) {
    if (!video.readyState) {
      video.addEventListener("loadedmetadata", updateHeight, {
        once: true,
      });
    }
  }

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
  const mediaContainers = Array.from(
    tweetContainer.querySelectorAll(".media-container")
  );
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
  const tweetId = Number.parseInt(tweetContainer.firstChild.id);
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
  for (const video of videos) {
    if (observedVideos.has(video)) {
      videoObserver.unobserve(video);
      observedVideos.delete(video);
    }
    video.pause();
    video.src = "";
    video.load();
  }

  const height = Number.parseFloat(
    tweetContainer.getBoundingClientRect().height.toFixed(3)
  );
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
  const tweetId = Number.parseInt(placeholder.id.replace("placeholder-", ""));
  if (!all_data[tweetId] || !placeholderMap[tweetId]) return;

  const tweetContainer = document.createElement("div");
  tweetContainer.id = `tweet-container-${tweetId}`;
  tweetContainer.innerHTML = generateTweetHTML(all_data[tweetId], tweetId);
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
  for (const entry of entries) {
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
  }
}

function observeNewVideos(tweetContainer) {
  const videos = tweetContainer.querySelectorAll(
    ".video-player, .quote-video-player"
  );
  for (const video of videos) {
    videoObserver.observe(video);
    observedVideos.set(video, true);
  }
}

// =========================
// 语言切换处理
// =========================

function observeLanguage(tweetContainer) {
  const langButton = tweetContainer.querySelector(".language");
  const srcSpan = tweetContainer.querySelector("#src");
  const trsSpan = tweetContainer.querySelector("#trs");
  const tweetContent = tweetContainer.querySelector(".tweet-content");

  if (!langButton || !srcSpan || !trsSpan || !tweetContent) return;

  trsSpan.style.display = "none";

  const measureHeight = (element) => (element ? element.offsetHeight : 0);

  const handleLanguageToggle = (e) => {
    e.preventDefault();
    e.stopPropagation();

    const showingSrc = srcSpan.style.display !== "none";
    if (showingSrc) {
      // 切换到 trs
      trsSpan.style.display = "inline-block";
      const targetHeight = measureHeight(trsSpan);
      trsSpan.style.display = "none";

      const currentHeight = measureHeight(srcSpan);
      srcSpan.classList.add("smoke-out");
      if (currentHeight !== targetHeight) {
        tweetContent.style.height = `${currentHeight}px`;
        tweetContent.style.transition = "height 0.3s linear";

        requestAnimationFrame(() => {
          tweetContent.style.height = `${targetHeight}px`;
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

        trsSpan.style.display = "inline-block";
        trsSpan.classList.add("smoke-in");
        trsSpan.addEventListener(
          "animationend",
          function handleTrsIn() {
            trsSpan.removeEventListener("animationend", handleTrsIn);
            trsSpan.classList.remove("smoke-in");
          },
          { once: true }
        );
      };

      srcSpan.addEventListener("animationend", handleSrcOutEnd, {
        once: true,
      });
    } else {
      // 切换回 src
      const currentHeight = measureHeight(trsSpan);
      srcSpan.style.display = "inline-block";
      const targetHeight = measureHeight(srcSpan);
      srcSpan.style.display = "none";

      trsSpan.classList.add("smoke-out");
      if (currentHeight !== targetHeight) {
        tweetContent.style.height = `${currentHeight}px`;
        tweetContent.style.transition = "height 0.3s linear";
        requestAnimationFrame(() => {
          tweetContent.style.height = `${targetHeight}px`;
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

        srcSpan.style.display = "inline-block";
        srcSpan.classList.add("smoke-in");
        srcSpan.addEventListener(
          "animationend",
          function handleSrcIn() {
            srcSpan.removeEventListener("animationend", handleSrcIn);
            srcSpan.classList.remove("smoke-in");
          },
          { once: true }
        );
      };

      trsSpan.addEventListener("animationend", handleTrsOutEnd, {
        once: true,
      });
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
    const zoomedHeight =
      width * (lightboxImg.naturalHeight / lightboxImg.naturalWidth);

    if (zoomedHeight > window.innerHeight) {
      lightboxImg.classList.add("zoomed");
      lightboxImg.style.width = `${width}px`;
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
  document
    .querySelector(".tweets-container")
    .addEventListener("click", (event) => {
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
    const minColumnBottom = Math.min(
      ...Array.from(tweetsColumns).map(
        (column) => column.getBoundingClientRect().bottom
      )
    );
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
