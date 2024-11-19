from typing import Dict, List

from ..base import BaseParser


class TwitterCellParser(BaseParser[Dict]):
    """Base parser for Twitter content that extracts tweet data into structured format"""

    def parse(self, element) -> Dict:
        """Parse tweet element and extract all relevant data into dictionary format"""
        data = {}
        data.update(self._extract_metadata(element))
        data.update(self._extract_author_info(element))
        data.update(self._extract_content(element))
        data.update(self._extract_images(element))
        data.update(self._check_videos(element))
        data.update(self._extract_card(element))
        data.update(self._check_content_uncomplete(element))
        return data

    def _extract_metadata(self, element) -> Dict:
        """Extract tweet metadata including URL, ID and publish timestamp"""
        time_ele = element.ele("tag:time", timeout=0)
        url_ele = time_ele.parent()
        url = url_ele.attr("href")
        return {
            "url": url,
            "id": url.split("/")[-1],
            "published_at": time_ele.attr("datetime"),
        }

    def _extract_author_info(self, element) -> Dict:
        """Extract author information including display name and handle"""
        author_ele = element.ele("@data-testid=User-Name")
        children = author_ele.children()
        name_into = children[0]
        while child := name_into.child(timeout=0):
            name_into = child
        return {
            "author_name": self._parse_content(name_into.parent()),
            "author_handle": children[1].text.split("\n")[0],
        }

    def _extract_content(self, element) -> Dict:
        """Extract main tweet text content"""
        text_ele = element.ele("@data-testid=tweetText", timeout=0)
        return {"content": self._parse_content(text_ele) if text_ele else ""}

    def _extract_images(self, element) -> Dict:
        """Extract image URLs from tweet, excluding video thumbnails"""
        photo_eles: List = element.eles("@data-testid=tweetPhoto", timeout=0)
        image_elements = []

        # 更安全的图片元素提取
        for twe in photo_eles:
            try:
                if img := twe.ele("tag:img", timeout=0):
                    image_elements.append(img)
            except Exception:
                continue

        VIDEO_THUMBS = [
            "tweet_video_thumb",
            "ext_tw_video_thumb",
            "amplify_video_thumb",
        ]

        def _process_image_url(url: str) -> str:
            """Process image URL to get highest quality version by replacing size parameters"""
            replacements = [
                ("&name=small", "&name=large"),
                ("&name=900x900", "&name=4096x4096"),
                ("&name=240x240", "&name=4096x4096"),
            ]
            for old, new in replacements:
                url = url.replace(old, new)
            return url

        images = [
            {"url": _process_image_url(img.attr("src"))}
            for img in image_elements
            if not any(thumb in img.attr("src") for thumb in VIDEO_THUMBS)
        ]

        return {"images": images or None}

    def _check_videos(self, element) -> Dict:
        """Check for presence of playable video content"""
        has_video = None
        if tweet_ele := element.ele("@data-testid=videoComponent", timeout=0):
            has_video = not tweet_ele.ele("The media could not be played.", timeout=0)
        return {"videos": has_video}

    def _extract_card(self, element) -> Dict:
        """Extract URL from tweet card if present"""
        card_url = None
        if card_ele := element.ele("@data-testid=card.wrapper", timeout=0):
            if link_ele := card_ele.ele("tag:a", timeout=0):
                card_url = link_ele.attr("href")
        return {"card": card_url}

    def _check_content_uncomplete(self, element) -> Dict:
        """Check if tweet content is truncated with 'Show more' link"""
        show_more_ele = element.ele(
            "@data-testid=tweet-text-show-more-link",
            timeout=0,
        )
        return {"content_uncomplete": bool(show_more_ele) or None}

    def _div_link_element(self, element):
        """Check if tweet is a quoted tweet"""
        return element.ele(
            "@@tag()=div@@role=link@!data-testid=tweet-text-show-more-link@!data-testid=birdwatch-pivot",
            timeout=0,
        )

    def _div_link_elements(self, element):
        return element.eles(
            "@@tag()=div@@role=link@!data-testid=tweet-text-show-more-link@!data-testid=birdwatch-pivot",
            timeout=0,
        )

    def _parse_content(self, element) -> str:
        """Parse text content from element, handling special cases for img and link elements"""
        text_content = []
        for child in element.children():
            match child.tag:
                case "img":
                    text_content.append(child.attr("alt"))
                case "a":
                    text_content.append(child.raw_text.strip("…"))
                case _:
                    text_content.append(child.raw_text)
        return "".join(filter(None, text_content))
