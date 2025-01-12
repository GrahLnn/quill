import os
from pathlib import Path
import traceback
from typing import Optional
from urllib.parse import urlparse, parse_qsl

import httpx
from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential


def print_error_stack(retry_state: RetryCallState):
    """在最终失败时打印堆栈"""
    print(f"Maximum retry attempts reached: {retry_state.args[0]}. Printing stack trace...")
    exc = retry_state.outcome.exception()  # 获取异常对象
    if exc:
        traceback.print_exception(type(exc), exc, exc.__traceback__)


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=4, max=660),
    retry_error_callback=print_error_stack,
)
def download(url: str, save_folder: str) -> Optional[str]:
    """
    Download a file from the given URL and save it to the specified folder.
    If the file already exists, skip downloading.

    Args:
        url: The URL to download from
        save_folder: The folder path to save the downloaded file

    Returns:
        str: The path to the saved file if successful, None otherwise
    """
    # Create save folder if it doesn't exist
    Path(save_folder).mkdir(parents=True, exist_ok=True)

    # Extract filename from URL and format parameter
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    query_params = dict(parse_qsl(parsed_url.query))

    # Add extension from format parameter if available
    if "format" in query_params:
        filename = f"{filename}.{query_params['format']}"

    # Construct save path
    save_path = os.path.join(save_folder, filename)

    # Check if file already exists
    if os.path.exists(save_path):
        return save_path

    # Download the file
    with httpx.Client() as client:
        try:
            response = client.get(url)
            response.raise_for_status()  # Raise exception for bad status codes

            # Save the file
            with open(save_path, "wb") as f:
                f.write(response.content)

            return save_path
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [403, 307, 404]:
                return "media unavailable"
            raise e
