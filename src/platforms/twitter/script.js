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
let lastGlobalSwitchTime = 0; // 最后一次全局语言切换的时间戳

let tweetsColumns; // 在DOMContentLoaded后初始化
let columnEnds; // 每列当前的 tweet 数量记录

// IntersectionObserver 用于视频自动播放
let videoObserver = null;

let globalTranslationsEnabled = false; // 全局翻译开关
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
  const windowTop = window.scrollY;
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
function showQuoteLangIcon(tweet) {
  if (!tweet.content.translation && tweet.quote.content.translation)
    return `<div class="language">${language}</div>`;
  return "";
}
function generateTranslationHtml(content, isQuote = false) {
  if (!content.translation) return "";
  return `<span id="${isQuote ? "qtrs" : "trs"}">${content.translation}</span>`;
}
function generateSourceHtml(content, isQuote = false) {
  return `<span id="${isQuote ? "qsrc" : "src"}">${content.text}</span>`;
}
function showContent(tweet, isQuote = false) {
  if (!tweet.content.text) return "";
  return `<div class="tweet-content">${generateSourceHtml(
    tweet.content,
    isQuote
  )}${generateTranslationHtml(tweet.content, isQuote)}</div>`;
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
function showQuote(tweet) {
  const qtweet = tweet.quote;
  if (!qtweet) return "";
  return `<div class="quote-tweet"> <div class="tweet-header"> <div class="user"> <div style="display: flex; justify-content: center; align-items: center;"> <img src="${
    qtweet.author.avatar.path
  }" alt="Avatar" class="avatar"/> </div> <div class="user-info"> <span class="name">${
    qtweet.author.name
  }</span> <span class="username">@${
    qtweet.author.screen_name
  }</span> </div> </div> <span class="qtool">${showQuoteLangIcon(
    tweet
  )}</span> </div> ${showContent(qtweet, true)} ${showMedia(
    qtweet,
    true
  )} ${showCard(qtweet.card)} </div>`;
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
    tweet
  )} <div style="margin-top: 8px"> <div class="footer"> <span class="timestamp">${
    tweet.created_at
  }</span> <a href="https://x.com/i/status/${
    tweet.rest_id
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

function globalLanguageSwitch(container, shouldAnimate = true) {
  const translationState = globalTranslationsEnabled;

  const elements = [
    {
      src: "#src",
      trs: "#trs",
      contentSelector: ".tweet-content",
      langBtnSelector: ".language",
    },
    {
      src: "#qsrc",
      trs: "#qtrs",
      contentSelector: ".quote-tweet .tweet-content",
      langBtnSelector: ".language",
    },
  ];

  for (const element of elements) {
    const { src, trs, contentSelector, langBtnSelector } = element;

    const srcSpan = container.querySelector(src);
    const trsSpan = container.querySelector(trs);
    const content = container.querySelector(contentSelector);
    const langButton = container.querySelector(langBtnSelector);

    if (srcSpan && trsSpan && content && langButton) {
      if (translationState) {
        // 启用翻译：显示翻译，隐藏源文本
        if (srcSpan.style.display !== "none") {
          if (shouldAnimate) {
            doSwitchAnimation(srcSpan, trsSpan, content);
          } else {
            srcSpan.style.display = "none";
            trsSpan.style.display = "inline-block";
          }
          langButton.classList.toggle("active", true);
        }
      } else {
        // 禁用翻译：显示源文本，隐藏翻译
        if (trsSpan.style.display !== "none") {
          if (shouldAnimate) {
            doSwitchAnimation(trsSpan, srcSpan, content);
          } else {
            srcSpan.style.display = "inline-block";
            trsSpan.style.display = "none";
          }
          langButton.classList.toggle("active", false);
        }
      }
    }
  }
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
    globalLanguageSwitch(tweetContainer);
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
  for (const tweetId of renderedTweetIds) {
    const tweetContainer = document.getElementById(
      `tweet-container-${tweetId}`
    );
    const placeholder = document.getElementById(`placeholder-${tweetId}`);

    if (tweetContainer && isElementVisible(tweetContainer)) {
      visibleTweets.set(tweetId, true);
    } else if (placeholder && isElementVisible(placeholder)) {
      replaceWithTweet(placeholder);
      visibleTweets.set(tweetId, true);
    } else {
      if (visibleTweets.has(tweetId) && tweetContainer) {
        replaceWithPlaceholder(tweetContainer);
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

// 函数：处理鼠标悬停进入
function handleToolbarMouseEnter(event) {
  const button = event.currentTarget;
  const label = button.querySelector(".button-label");
  if (label) {
    label.classList.add("visible");
  }
}

// 函数：处理鼠标悬停离开
function handleToolbarMouseLeave(event) {
  const button = event.currentTarget;
  const label = button.querySelector(".button-label");
  if (label) {
    label.classList.remove("visible");
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
  globalLanguageSwitch(tweetContainer, false);
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
/**
 * 一个通用的动画切换函数(隐藏 -> 显示)
 * @param {HTMLElement} hideElement   - 当前显示的节点(如源文本或翻译)
 * @param {HTMLElement} showElement   - 目标要显示的节点(如翻译或源文本)
 * @param {HTMLElement} container     - 容器用于做高度过渡，一般是 tweet-content
 */
function doSwitchAnimation(hideElement, showElement, container) {
  if (!hideElement || !showElement || !container) return;

  const measureHeight = (el) => (el ? el.offsetHeight : 0);

  const currentHeight = measureHeight(hideElement);
  // 先把 showElement 显示一下，以得到目标高度
  showElement.style.display = "inline-block";
  const targetHeight = measureHeight(showElement);
  // 再隐藏回去
  showElement.style.display = "none";

  // 隐藏的元素执行「渐隐」动画
  hideElement.classList.add("smoke-out");

  // 如果高度不同，则给父容器做一个过渡动画
  if (currentHeight !== targetHeight) {
    container.style.height = `${currentHeight}px`;
    container.style.transition = "height 0.3s linear";

    requestAnimationFrame(() => {
      container.style.height = `${targetHeight}px`;
    });
  }

  // 监听动画结束
  const handleHideOutEnd = () => {
    hideElement.removeEventListener("animationend", handleHideOutEnd);
    hideElement.classList.remove("smoke-out");
    hideElement.style.display = "none";

    // 恢复容器高度
    if (currentHeight !== targetHeight) {
      container.style.transition = "";
      container.style.height = "";
    }

    // 显示要「渐显」的内容
    showElement.style.display = "inline-block";
    showElement.classList.add("smoke-in");
    showElement.addEventListener(
      "animationend",
      function handleShowIn() {
        showElement.removeEventListener("animationend", handleShowIn);
        showElement.classList.remove("smoke-in");
      },
      { once: true }
    );
  };
  hideElement.addEventListener("animationend", handleHideOutEnd, {
    once: true,
  });
}

function observeLanguage(tweetContainer) {
  // 定义推文类型及其相关选择器和类名
  const tweetTypes = [
    {
      type: "main",
      langButtonSelector: ".language",
      srcSelector: "#src",
      trsSelector: "#trs",
      contentSelector: ".tweet-content",
    },
    {
      type: "quote",
      langButtonSelector: ".language",
      srcSelector: "#qsrc",
      trsSelector: "#qtrs",
      contentSelector: ".quote-tweet .tweet-content",
    },
  ];

  // 缓存所有相关元素，并初始化隐藏译文
  const cachedElements = {};
  for (const t of tweetTypes) {
    const {
      type,
      srcSelector,
      trsSelector,
      contentSelector,
      langButtonSelector,
    } = t;

    cachedElements[type] = {
      langButton: tweetContainer.querySelector(langButtonSelector),
      src: tweetContainer.querySelector(srcSelector),
      trs: tweetContainer.querySelector(trsSelector),
      content: tweetContainer.querySelector(contentSelector),
    };

    // 初始化：隐藏译文
    if (cachedElements[type].trs) {
      cachedElements[type].trs.style.display = "none";
    }
  }

  /**
   * 通用的切换处理函数
   * @param {Object} primary - 推文类型对象
   * @param {Array} relatedTypes - 相关推文类型数组
   */
  function toggleLanguage(primary, relatedTypes = []) {
    return (e) => {
      e.preventDefault();
      e.stopPropagation();

      const { src, trs, content, langButton } = primary;
      if (!src || !trs || !content || !langButton) return;

      const isShowingSrc = src.style.display !== "none";

      if (isShowingSrc) {
        // 切换到译文
        doSwitchAnimation(src, trs, content);
        langButton.classList.toggle("active", true);

        // 同时切换相关推文类型
        for (const type of relatedTypes) {
          const related = cachedElements[type];
          if (related && related.src.style.display !== "none") {
            doSwitchAnimation(related.src, related.trs, related.content);
            related.langButton.classList.toggle("active", true);
          }
        }
      } else {
        // 切回源文本
        doSwitchAnimation(trs, src, content);
        langButton.classList.toggle("active", false);

        // 同时切换相关推文类型
        for (const type of relatedTypes) {
          const related = cachedElements[type];
          if (related && related.trs.style.display !== "none") {
            doSwitchAnimation(related.trs, related.src, related.content);
            related.langButton.classList.toggle("active", false);
          }
        }
      }
    };
  }

  // 检查哪些推文类型有翻译
  const availableTweetTypes = tweetTypes.filter(
    (t) => cachedElements[t.type].trs && cachedElements[t.type].langButton
  );

  const hasMainTranslation = availableTweetTypes.some((t) => t.type === "main");
  const hasQuoteTranslation = availableTweetTypes.some(
    (t) => t.type === "quote"
  );

  // 绑定事件监听器
  for (const t of availableTweetTypes) {
    const { langButton } = cachedElements[t.type];
    if (langButton) {
      let handler;
      if (t.type === "main" && hasQuoteTranslation) {
        handler = toggleLanguage(cachedElements[t.type], ["quote"]);
      } else if (t.type === "quote" && !hasMainTranslation) {
        handler = toggleLanguage(cachedElements[t.type]);
      } else {
        handler = toggleLanguage(cachedElements[t.type]);
      }

      langButton.addEventListener("click", handler);
      languageListeners.set(langButton, handler);
    }
  }

  // 如果都没有翻译，或找不到对应按钮，就不做任何绑定
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

  // 为每个工具栏按钮添加事件监听器
  const toolbarButtons = document.querySelectorAll(".toolbar-button");
  for (const button of toolbarButtons) {
    button.addEventListener("mouseenter", handleToolbarMouseEnter);
    button.addEventListener("mouseleave", handleToolbarMouseLeave);
  }

  // 点击媒体事件（显示Lightbox）
  document
    .querySelector(".tweets-container")
    .addEventListener("click", (event) => {
      const img = event.target.closest(".media-item, .quote-media-item");
      if (img) handleMediaItemClick(img);
    });

  // 滚动与Resize事件处理
  let scrollTimeout = null;
  let isScrolling = false;
  let lastScrollTime = 0;

  const handleScroll = () => {
    const now = Date.now();
    if (now - lastScrollTime < 16) {
      // 限制最小间隔约为60fps
      return;
    }
    lastScrollTime = now;

    checkAndUpdateTweetVisibility();

    // 检查是否需要加载更多tweets
    const minColumnBottom = Math.min(
      ...Array.from(tweetsColumns).map(
        (column) => column.getBoundingClientRect().bottom
      )
    );
    if (minColumnBottom <= window.innerHeight + 6000) {
      loadMoreTweets();
    }

    // 更新媒体容器监控
    if (!isScrolling) {
      isScrolling = true;
      updateMonitoredMediaContainers();
    }

    // 清除之前的timeout
    if (scrollTimeout) {
      clearTimeout(scrollTimeout);
    }

    // 设置新的timeout
    scrollTimeout = setTimeout(() => {
      isScrolling = false;
      updateMonitoredMediaContainers();
    }, 150);
  };

  window.addEventListener("scroll", () => {
    requestAnimationFrame(handleScroll);
  });

  window.addEventListener("resize", () => {
    requestAnimationFrame(() => {
      checkAndUpdateTweetVisibility();
      updateMonitoredMediaContainers();
    });
  });

  // 获取翻译按钮
  const translateButton = document.getElementById("translate-button");

  // 绑定点击事件监听器
  translateButton.addEventListener("click", () => {
    const now = Date.now();
    if (now - lastGlobalSwitchTime <= 700) {
      return;
    }
    lastGlobalSwitchTime = now;
    // 切换全局翻译状态
    globalTranslationsEnabled = !globalTranslationsEnabled;

    // 更新按钮的外观
    translateButton.classList.toggle("active", globalTranslationsEnabled);

    // 遍历所有已渲染的 tweets 并切换翻译显示
    for (const tweetID of renderedTweetIds) {
      const tweetContainer = document.getElementById(
        `tweet-container-${tweetID}`
      );
      if (tweetContainer) {
        globalLanguageSwitch(tweetContainer);
      }
    }
  });
});
