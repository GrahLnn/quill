import logging
import os
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(5),
    reraise=True,
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
def download_image(url: str, save_dir: str = "downloaded_images") -> str:
    """
    从给定的URL下载图片并保存到指定目录。

    Args:
        url: 图片的URL
        save_dir: 保存图片的目录，默认为'downloaded_images'

    Returns:
        str: 保存的图片文件路径

    Raises:
        httpx.HTTPError: 当下载失败时
        OSError: 当文件操作失败时
    """
    try:
        # 创建保存目录
        os.makedirs(save_dir, exist_ok=True)

        # 处理文件名
        parsed_url = urlparse(url)
        file_name = os.path.basename(parsed_url.path)

        if not file_name:
            file_name = url.split("/")[-1]

        # 处理文件扩展名
        name, ext = os.path.splitext(file_name)
        if not ext and "format=" in url:
            format = url.split("format=")[-1].split("&")[0]
            file_name = f"{name}.{format}"

        save_path = os.path.join(save_dir, file_name)

        # 下载文件
        logger.info(f"Downloading image from {url}")
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()

        # 保存文件
        with open(save_path, "wb") as file:
            file.write(response.content)

        logger.info(f"Image saved to {save_path}")
        return save_path

    except httpx.HTTPError as e:
        logger.error(f"Failed to download image from {url}: {str(e)}")
        raise
    except OSError as e:
        logger.error(f"Failed to save image to {save_path}: {str(e)}")
        raise
