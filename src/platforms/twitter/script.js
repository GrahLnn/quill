import gsap from "https://cdn.skypack.dev/gsap@3.12.0";
import { animate } from "https://cdn.jsdelivr.net/npm/motion@latest/+esm";
// =========================
// 全局常量与变量定义
// =========================
const all_data = [];
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
let isAnimating = false; // 动画锁
let globalTranslationsEnabled = false; // 全局翻译开关
// =========================
// icon
// =========================

const languageIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18" > <g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121" > <path d="M2.25 4.25H10.25"></path> <path d="M6.25 2.25V4.25"></path> <path d="M4.25 4.25C4.341 6.926 6.166 9.231 8.75 9.934"></path> <path d="M8.25 4.25C7.85 9.875 2.25 10.25 2.25 10.25"></path> <path d="M9.25 15.75L12.25 7.75H12.75L15.75 15.75"></path> <path d="M10.188 13.25H14.813"></path> </g> </svg>`;
const pinIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18" > <g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121" > <path d="M10.371 15.553C10.803 14.996 11.391 14.083 11.719 12.835C11.888 12.193 11.949 11.611 11.962 11.134L14.967 8.129C15.748 7.348 15.748 6.082 14.967 5.301L12.699 3.033C11.918 2.252 10.652 2.252 9.87101 3.033L6.86601 6.038C6.38801 6.051 5.80701 6.112 5.16501 6.281C3.91701 6.609 3.00401 7.197 2.44701 7.629L10.372 15.554L10.371 15.553Z" fill="#212121" fill-opacity="0.3" data-stroke="none" stroke="none" ></path> <path d="M3.08099 14.919L6.40899 11.591"></path> <path d="M10.371 15.553C10.803 14.996 11.391 14.083 11.719 12.835C11.888 12.193 11.949 11.611 11.962 11.134L14.967 8.129C15.748 7.348 15.748 6.082 14.967 5.301L12.699 3.033C11.918 2.252 10.652 2.252 9.87101 3.033L6.86601 6.038C6.38801 6.051 5.80701 6.112 5.16501 6.281C3.91701 6.609 3.00401 7.197 2.44701 7.629L10.372 15.554L10.371 15.553Z"></path> </g> </svg>`;
const msgIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 18 18"><g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" stroke="#212121"><path d="M9 1.75C4.996 1.75 1.75 4.996 1.75 9C1.75 10.319 2.108 11.552 2.723 12.617C3.153 13.423 2.67 15.329 1.75 16.25C3 16.318 4.647 15.753 5.383 15.277C5.872 15.559 6.647 15.933 7.662 16.125C8.095 16.207 8.543 16.25 9 16.25C13.004 16.25 16.25 13.004 16.25 9C16.25 4.996 13.004 1.75 9 1.75Z" fill="#212121" fill-opacity="0.3" data-stroke="none" stroke="none"></path> <path d="M9 1.75C4.996 1.75 1.75 4.996 1.75 9C1.75 10.319 2.108 11.552 2.723 12.617C3.153 13.423 2.67 15.329 1.75 16.25C3 16.318 4.647 15.753 5.383 15.277C5.872 15.559 6.647 15.933 7.662 16.125C8.095 16.207 8.543 16.25 9 16.25C13.004 16.25 16.25 13.004 16.25 9C16.25 4.996 13.004 1.75 9 1.75Z"></path> <path opacity="0.75" d="M9 10C8.448 10 8 9.551 8 9C8 8.449 8.448 8 9 8C9.552 8 10 8.449 10 9C10 9.551 9.552 10 9 10Z" fill="#212121" data-stroke="none" stroke="none"></path> <path d="M5.5 10C4.948 10 4.5 9.551 4.5 9C4.5 8.449 4.948 8 5.5 8C6.052 8 6.5 8.449 6.5 9C6.5 9.551 6.052 10 5.5 10Z" fill="#212121" data-stroke="none" stroke="none"></path> <path opacity="0.5" d="M12.5 10C11.948 10 11.5 9.551 11.5 9C11.5 8.449 11.948 8 12.5 8C13.052 8 13.5 8.449 13.5 9C13.5 9.551 13.052 10 12.5 10Z" fill="#212121" data-stroke="none" stroke="none"></path></g></svg>`;
// =========================
// 工具函数
// =========================
const measureHeight = (el) => (el ? el.offsetHeight : 0);
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
function isElementVisible(element, extraTop = 500, extraBottom = 500) {
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
  return `<div class="language">${languageIcon}</div>`;
}
function showQuoteLangIcon(tweet) {
  if (!tweet.content.translation && tweet.quote.content.translation)
    return `<div class="language">${languageIcon}</div>`;
  return "";
}
function generateTranslationHtml(content, isQuote = false) {
  if (!content.translation) return "";
  return `<span id="${isQuote ? "qtrs" : "trs"}">${content.translation}</span>`;
}
function generateSourceHtml(content, isQuote = false) {
  return `<span id="${isQuote ? "qsrc" : "src"}">${content.text}</span>`;
}
function showContent(tweet, state) {
  if (!tweet.content.text) return "";
  if (!state.inReply)
    return `<div class="tweet-content">${generateSourceHtml(
      tweet.content,
      state.isQuote
    )}${generateTranslationHtml(tweet.content, state.isQuote)}</div>`;
  return showReplyContent(tweet);
}
function generateReplyTranslationHtml(content) {
  if (!content.translation) return "";
  return `<span id="rtrs">${content.translation}</span>`;
}
function generateReplySourceHtml(content) {
  return `<span id="rsrc" style="padding: 0 4px">${content.text}</span>`;
}
function showReplyContent(tweet) {
  if (!tweet.content.text) return "";
  return `<div class="tweet-content" style="font-size: 0.9em; width: fit-content;">${generateReplySourceHtml(
    tweet.content
  )}${generateReplyTranslationHtml(tweet.content)}</div>`;
}
function generateMediaHtml(media, isQuote = false) {
  if (media.path === "media unavailable")
    return `<div class="media-unavailable">Media Unavailable</div>`;
  switch (media.type) {
    case "photo":
      return `<img class="${
        isQuote ? "quote-media-item" : "media-item"
      }" src="${media.path}" loading="lazy" />`;
    case "video": {
      const isLoop = media?.duration_millis ?? 0 < 31000;
      return `<div class="video-container" style="${`position: relative; padding-bottom: ${Math.min(
        ((media.aspect_ratio?.[1] ?? 9) / (media.aspect_ratio?.[0] ?? 16)) *
          100,
        100
      )}%`}" > <video class="${
        isQuote ? "quote-video-player" : "video-player"
      }" controls preload="none" playsinline poster="${
        media.thumb_path
      }" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;" ${
        isLoop ? "loop" : ""
      } > <source src="${
        media.path
      }" type="video/mp4" /> Your browser does not support video. </video> </div>`;
    }
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
function showMedia(tweet, state) {
  if (!tweet.media) return "";
  return `<div class="media-container">${tweet.media
    .map((media) => generateMediaHtml(media, state.isQuote))
    .join("")}</div>`;
}
function showCard(card) {
  if (!card) return "";
  return `<a href="${
    card.url
  }" style="text-decoration: none; color: inherit;" target="_blank" > <div class="card" style="cursor: pointer; border: 1px solid #e1e8ed;" > <div style="font-size: 12px; font-weight: bold;"> ${
    card.title
  } </div> ${
    card.description
      ? `<div style="font-size: 10px; color: #536471; word-break: break-word; overflow-wrap: break-word;"> ${card.description} </div>`
      : ""
  } </div> </a>`;
}
function showQuote(tweet) {
  const qtweet = tweet.quote;
  if (!qtweet) return "";
  return `<div class="quote-tweet"> <div class="tweet-header"> <div class="user"> <div style="display: flex; justify-content: center; align-items: center;"> <img src="${
    qtweet.author.avatar.path
  }" alt="Avatar" class="avatar" /> </div> <div class="user-info"> <span class="name">${
    qtweet.author.name
  }</span> <span class="username">@${
    qtweet.author.screen_name
  }</span> </div> </div> <span class="qtool">${showQuoteLangIcon(
    tweet
  )}</span> </div> ${showDetail(qtweet, { isQuote: true })} </div>`;
}
function showDetail(tweet, state = { isQuote: false, inReply: false }) {
  const contentHTML = showContent(tweet, state);
  const mediaHTML = showMedia(tweet, state);
  const cardHTML = showCard(tweet.card);
  const quoteHTML = showQuote(tweet);
  return `<div class="flex-col" style="gap: 8px;">${contentHTML}${mediaHTML}${cardHTML}${quoteHTML}</div>`;
}

function generateConversationHTML(conversation, mainAuthorName) {
  const lastMessageIndices = new Set();
  let lastName = "";
  conversation.forEach((tweet, index) => {
    if (!lastName) {
      lastName = tweet.author.screen_name;
      return;
    }
    if (lastName !== tweet.author.screen_name) {
      lastMessageIndices.add(index - 1);
      lastName = tweet.author.screen_name;
    }
  });
  lastMessageIndices.add(conversation.length - 1);

  lastName = "";
  return conversation
    .filter(
      (tweet) =>
        tweet.content.text?.trim() ||
        tweet.media?.length ||
        tweet.card ||
        tweet.quote
    )
    .map((tweet, index) => {
      const whichName = `<span style="margin-top: 2px; margin-bottom: 4px; color: ${
        tweet.author.name === mainAuthorName
          ? "#545454; font-size: 0.9em;"
          : "hsl(0 0% 50%); font-size: 0.8em;"
      } font-weight: bold;">${
        tweet.author.name === mainAuthorName
          ? mainAuthorName
          : `@${tweet.author.screen_name}`
      }</span>`;

      const borderRadius = lastMessageIndices.has(index) ? "4px 16px 16px 16px" : "4px 16px 16px 4px";

      const html = `<div class="flex">
  <div class="flex-col">
    ${tweet.author.screen_name === lastName ? "" : whichName}
    <div style="background-color: #f8f9fa26; padding: 8px; border-radius: ${borderRadius}; display: inline-block; width: fit-content; border: 1px solid #eeeeee; word-break: break-word; overflow-wrap: break-word;">
      ${showDetail(tweet)}
    </div>
  </div>
</div>`;

      lastName = tweet.author.screen_name;
      return html;
    })
    .join("");
}

function generateReplyHTML(tweet) {
  if (!tweet.replies?.length) return "";
  return `<div class="reply" style="display: none;">${tweet.replies
    .map((reply, index, array) => {
      const isLast = index === array.length - 1;
      const convHTML = generateConversationHTML(
        reply.conversation,
        tweet.author.name
      );
      return convHTML.trim() === ""
        ? ""
        : `
        <div style="height: 10px;"></div>
        <div class="conversation">
          ${convHTML}
        </div>
          ${
            !isLast
              ? '<div style="border-bottom: 1px solid #f0f0f0; width: 100%; margin-top: 16px; margin-bottom: 6px;"></div>'
              : ""
          }
        
      `;
    })
    .join("")}</div>`;
}
const bullHTML = `<span style="color: #657786;">&bull;</span>`;

function footerToolHTML(tweet) {
  const replyButton = tweet.replies?.length
    ? `<span class="link2x cursor-pointer" id="reply-buttom">See reply</span>${bullHTML}`
    : "";
  return `<div class="select-none text-tool">
    ${replyButton}
    <a href="https://x.com/i/status/${tweet.rest_id}" class="link2x" target="_blank">View on 𝕏</a>
  </div>`;
}

function generateTweetHTML(tweet) {
  return `<div class="tweet-item"><div class="tweet"> <div class="tweet-header"> <div class="user"> <div style="display: flex; justify-content: center; align-items: center;"> <img src="${
    tweet.author.avatar.path
  }" alt="Avatar" class="avatar" > </div> <div class="user-info"> <span class="name">${
    tweet.author.name
  }</span> <span class="username">@${
    tweet.author.screen_name
  }</span> </div> </div> <span class="tool"> ${showLangIcon(
    tweet
  )} <div class="pin">${pinIcon}</div> </span> </div> ${showDetail(
    tweet
  )} <div style="margin-top: 8px"> <div class="footer"> <div class="flex"><span class="timestamp">${
    tweet.created_at
  }</span></div>${footerToolHTML(tweet)} </div></div></div>${generateReplyHTML(
    tweet
  )}</div>`;
}

function addTweet(tweetContainer, idx) {
  tweetContainer.id = `tweet-container-${idx}`;
  tweetContainer.innerHTML = generateTweetHTML(all_data[idx]);
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
    addTweet(tweetContainer, tweetId);

    renderedTweetIds.add(tweetId);
    observeLanguage(tweetContainer);
    observeReply(tweetContainer);
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
  const windowTop = window.scrollY;
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

// =========================
// Tweet 占位符与替换
// =========================

/**
 * 用占位符替换一个不在可见范围内的 tweetContainer。
 */
function replaceWithPlaceholder(tweetContainer) {
  const tweetId = Number.parseInt(
    tweetContainer.id.replace("tweet-container-", "")
  );
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
  addTweet(tweetContainer, tweetId);
  placeholder.parentNode.replaceChild(tweetContainer, placeholder);
  delete placeholderMap[tweetId];

  registerMonitoredTweet(tweetId, tweetContainer);
  observeNewVideos(tweetContainer);
  observeLanguage(tweetContainer);
  observeReply(tweetContainer);
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
      // video.loop = true;
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
/**
 * @param {HTMLElement | string} target 需要执行“烟雾消失”动画的DOM或选择器
 * @param {number} duration 动画时长（秒）
 * @returns {Promise<void>} 可被await或then
 */
function smokeOut(target, duration = 0.3) {
  return animate(
    target,
    {
      // 使用滤镜和透明度模拟烟雾消散
      filter: ["blur(0px)", "blur(6px)"],
      opacity: [1, 0],
    },
    {
      duration, // 动画持续时长
      ease: "linear", // 使用线性过渡，模拟 css: animation-timing-function: linear
    }
  );
}
/**
 * @param {HTMLElement | string} target 需要执行“烟雾出现”动画的DOM或选择器
 * @param {number} duration 动画时长（秒）
 * @returns {Promise<void>}
 */
function smokeIn(target, duration = 0.3) {
  return animate(
    target,
    {
      // 可以从模糊+透明 到 清晰+不透明
      filter: ["blur(6px)", "blur(0px)"],
      opacity: [0, 1],
    },
    {
      duration,
      ease: "linear",
    }
  );
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

function closeHeight(el) {
  const currentHeight = measureHeight(el);
  el.style.height = `${currentHeight}px`;
  el.style.transition = "height 0.1s linear";
  requestAnimationFrame(() => {
    el.style.height = "0px";
  });
}

function isElementInViewport(el) {
  if (!el) return false;
  const rect = el.getBoundingClientRect();
  return (
    rect.top < (window.innerHeight || document.documentElement.clientHeight) &&
    rect.bottom > 0 &&
    rect.left < (window.innerWidth || document.documentElement.clientWidth) &&
    rect.right > 0
  );
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
async function doSwitchAnimation(hideElement, showElement, container) {
  if (!hideElement || !showElement || !container) return;
  const isVisible = isElementInViewport(container);

  if (!isVisible) {
    // 直接更改显示属性，而不执行动画
    const hideHight = measureHeight(hideElement);
    hideElement.removeAttribute("style");
    hideElement.style.display = "none";
    showElement.removeAttribute("style");
    showElement.style.display = "inline-block";
    const showHeight = measureHeight(showElement);
    animate(
      container,
      { height: [`${hideHight}px`, `${showHeight}px`] },
      { ease: "linear", duration: 0.2 }
    );

    return;
  }

  isAnimating = true; // 开始动画锁
  const currentHeight = measureHeight(hideElement);
  // 预先显示 showElement 以便测量目标高度
  showElement.style.display = "inline-block";
  const targetHeight = measureHeight(showElement);
  // 再隐藏回去
  showElement.style.display = "none";

  animate(
    container,
    { height: [`${currentHeight}px`, `${targetHeight}px`] },
    {
      type: "spring",
      duration: 0.3,
    }
  );
  await smokeOut(hideElement);
  hideElement.style.display = "none";

  // 显示要「渐显」的内容
  showElement.style.display = "inline-block";
  await smokeIn(showElement);
  isAnimating = false;
}

function observeReply(tweetContainer) {
  const replyButton = tweetContainer.querySelector("#reply-buttom");
  const reply = tweetContainer.querySelector(".reply");

  if (!replyButton || !reply) return;
  let isShow = false;
  let inAnime = false;

  replyButton.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();

    if (isShow && !inAnime) {
      inAnime = true;
      reply.removeAttribute("style");
      replyButton.textContent = "See reply";
      closeHeight(reply);
      smokeIn(replyButton);
      await smokeOut(reply);
      reply.style.display = "none";
      isShow = false;
    } else if (!isShow && !inAnime) {
      inAnime = true;
      reply.removeAttribute("style");
      replyButton.textContent = "Close reply";
      smokeIn(replyButton);
      await smokeIn(reply);
      isShow = true;
    }
    inAnime = false;
  });
}

function observeTweetColumn() {
  const resizeObserver = new ResizeObserver((entries) => {
    for (const _ of entries) {
      // 当 .tweets-column 的尺寸发生变化时调用 checkAndUpdateTweetVisibility
      checkAndUpdateTweetVisibility();
    }
  });

  // 选择所有 .tweets-column 元素
  const tweetsColumns = document.querySelectorAll(".tweets-column");

  // 开始观察每个 .tweets-column 元素
  for (const column of tweetsColumns) {
    resizeObserver.observe(column);
  }
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
      if (isAnimating) return;

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
  const tweetContainerLeft = tweetContainerRect.left + window.scrollX;
  tweetContainer.style.position = "absolute";
  tweetContainer.style.left = `${tweetContainerLeft}px`;

  const toolbar = document.querySelector(".toolbar");
  if (toolbar) {
    toolbar.style.transition = "opacity 0.3s ease-in-out";
    toolbar.style.opacity = "0";
  }

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

    const toolbar = document.querySelector(".toolbar");
    if (toolbar) {
      toolbar.style.transition = "opacity 0.3s ease-in-out";
      toolbar.style.opacity = "1";
    }

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

function toolTip() {
  const config = {
    theme: "light",
    locked: false,
    speed: 0.26,
    blur: 4,
    debug: false,
    flow: "vertical",
  };

  const update = () => {
    document.documentElement.dataset.theme = config.theme;
    document.documentElement.dataset.debug = config.debug;
    document.documentElement.dataset.locked = config.locked;
    document.documentElement.dataset.flow = config.flow;
    document.documentElement.style.setProperty("--speed", config.speed);
    document.documentElement.style.setProperty("--blur", config.blur);
  };

  update();

  const nav = document.querySelector("nav");
  const navSize = nav.getBoundingClientRect().width;
  nav.style.opacity = "1";
  nav.style.setProperty("--width", navSize);
  document.documentElement.dataset.orientation = "horizontal";

  // 声明一个对象来存储指针位置（初始值可随意）
  // biome-ignore lint/style/useConst: <explanation>
  let pointerCoord = { x: 0, y: 0 };

  let bounds;

  const track = (event) => {
    const target = event.target;
    if (!target || !target.getBoundingClientRect) return;

    const targetBounds = target.getBoundingClientRect();
    const centerX = targetBounds.left + targetBounds.width / 2;
    const centerY = targetBounds.top + targetBounds.height / 2;

    const shiftX = (event.x - centerX) * 0.2;
    const shiftY = (event.y - centerY) * 0.2;

    // 在这里使用 GSAP 的补间来平滑更新 pointerCoord
    gsap.to(pointerCoord, {
      x: centerX - bounds.left + shiftX,
      y: centerY - bounds.top + shiftY,
      duration: 0.2, // 控制平滑的速度
      ease: "power2.out", // 可以自由选择缓动
      onUpdate: () => {
        // 在补间更新时，将 pointerCoord 映射到 CSS 变量
        document.documentElement.style.setProperty("--tip-x", pointerCoord.x);
        document.documentElement.style.setProperty("--tip-y", pointerCoord.y);
      },
    });
  };

  const teardown = () => {
    nav.removeEventListener("pointermove", track);
    nav.removeEventListener("pointerleave", teardown);
  };

  const initPointerTrack = () => {
    bounds = nav.getBoundingClientRect();
    nav.addEventListener("pointermove", track);
    nav.addEventListener("pointerleave", teardown);
  };

  nav.addEventListener("pointerenter", initPointerTrack);
  function createHiddenTipTrackMeasurements(tip) {
    // 1. 复制当前的 tip
    const hiddenTip = tip.cloneNode(true); // 克隆整个 tip
    hiddenTip.style.scale = 1;
    hiddenTip.style.position = "absolute";
    hiddenTip.style.top = "-9999px"; // 移出可视区域
    hiddenTip.style.left = "-9999px";
    hiddenTip.style.visibility = "hidden"; // 确保不可见
    hiddenTip.style.pointerEvents = "none"; // 禁止交互
    document.body.appendChild(hiddenTip); // 临时添加到 DOM 中

    const hiddenTipTrack = hiddenTip.querySelector(".tip__track");
    hiddenTipTrack.style.transition = "none"; // 禁用动画

    // 2. 测量每个项目的宽度
    const measurements = Array.from(hiddenTipTrack.children).map(
      (child, index) => {
        return {
          index,
          trackWidth: hiddenTipTrack.getBoundingClientRect().width,
          targetWidth: child.getBoundingClientRect().width,
        };
      }
    );

    // 3. 清理临时元素
    document.body.removeChild(hiddenTip);

    // 返回所有测量结果
    return measurements;
  }

  const navItems = document.querySelectorAll(".nav li");
  const tipTrack = document.querySelector(".tip__track");
  const tip = document.querySelector(".tip");

  // 初始化时测量所有项目的宽度
  const tipMeasurements = createHiddenTipTrackMeasurements(tip);

  navItems.forEach((li, index) => {
    li.addEventListener("mouseenter", () => {
      // 获取测量的宽度信息
      const measurement = tipMeasurements.find((m) => m.index === index);
      if (!measurement) return;

      const { trackWidth, targetWidth } = measurement;

      // 计算偏移量并设置 translate
      const offsetX = (trackWidth - targetWidth) / 2;
      tipTrack.style.translate = `-${offsetX}px calc((var(--active) - 1) * (var(--tip-height) * -1))`;

      animate(
        tipTrack,
        {
          width: targetWidth,
        },
        {
          duration: 0.2,
          type: "spring",
        }
      );
    });
  });
}

function lightbox() {
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

  // 点击媒体事件（显示Lightbox）
  document
    .querySelector(".tweets-container")
    .addEventListener("click", (event) => {
      const img = event.target.closest(".media-item, .quote-media-item");
      if (img) handleMediaItemClick(img);
    });
}

function globalTranslate() {
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
}

// =========================
// DOMContentLoaded 事件初始化
// =========================

document.addEventListener("DOMContentLoaded", () => {
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
  observeTweetColumn();
  toolTip();
  lightbox();
  globalTranslate();

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
    if (minColumnBottom <= window.innerHeight + 500) {
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
});
