import base64
import logging
import os
import time
from typing import Dict, Tuple

import httpx
from tenacity import (
    RetryCallState,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from .base import BaseClient, LLMSettings

logging.getLogger("httpx").setLevel(logging.CRITICAL)

# ========== GeminiClient Class ==========
SUPPORTED_IMAGE_MIMES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}
SUPPORTED_VIDEO_MIMES = {
    ".mp4": "video/mp4",
    ".mpeg": "video/mpeg",
    ".mov": "video/mov",
    ".avi": "video/avi",
    ".flv": "video/x-flv",
    ".mpg": "video/mpg",
    ".webm": "video/webm",
    ".wmv": "video/wmv",
    ".3gp": "video/3gpp",
}
SUPPORTED_MIMES = {**SUPPORTED_IMAGE_MIMES, **SUPPORTED_VIDEO_MIMES}
UPLOAD_LIMIT_BYTES = 5 * 1000 * 1000  # 5MB阈值，需要按1000计算


def push_cd(retry_state: RetryCallState):
    instance: GeminiClient = retry_state.args[0]
    # path = retry_state.args[2]
    if retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        print(f"retrying...{exc}")
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code == 429:
                # 遇到429错误，mark key used
                instance.key_manager.mark_key_used(instance.api_key)
        # else:
        #     # 对其他异常也可以做相应处理
        #     instance.key_manager.mark_key_used(instance.api_key)
        # 尝试切换key
        instance.api_key = instance._get_key()
        # instance._clean_all_file()


def clean_all_uploaded_files():
    settins = LLMSettings()
    keys = settins.gemini_api_keys
    for key in keys:
        client = GeminiClient(key)
        client._clean_all_file()


class GeminiClient(BaseClient):
    def __init__(self, key=None):
        super().__init__()
        self.base_url = self.settings.gemini_base_url
        # 获取Key
        self.api_key = key or self._get_key()
        self.safe = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE",
            },
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        self.generation_config = {"temperature": 1, "topP": 0.95}

    def _clean_all_file(self):
        files = self._list_files()
        for file in files:
            self._delete_file(file)

    def _get_key(self) -> str:
        # 从settings中选key，再从key_manager中获取可用key
        if not self.settings.gemini_api_keys:
            raise ValueError("No Gemini API keys provided in settings")
        key = self.key_manager.get_available_key(self.settings.gemini_api_keys)

        if not key:
            raise ValueError("No available Gemini API keys at this moment.")
        return key

    def _get_mime_type(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_MIMES:
            raise ValueError(f"Unsupported file format: {ext}")
        return SUPPORTED_MIMES[ext]

    def _base64_encode_file(self, file_path: str) -> str:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _upload_file(self, file_path: str) -> Tuple[str, str]:
        mime_type = self._get_mime_type(file_path)
        file_size = os.path.getsize(file_path)
        display_name = os.path.basename(file_path)

        # step1: 获得上传URL
        url = f"{self.base_url}/upload/v1beta/files?key={self.api_key}"
        headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        }
        body = {"file": {"display_name": display_name}}
        r = self.client.post(url, headers=headers, json=body)
        r.raise_for_status()
        upload_url = r.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise RuntimeError("Failed to get upload URL")

        # step2: 上传数据
        with open(file_path, "rb") as f:
            data = f.read()
        headers = {
            "Content-Length": str(file_size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        }
        r = self.client.post(upload_url, headers=headers, content=data)
        r.raise_for_status()
        file_info: Dict = r.json()

        # Normalize the response to always have a uniform structure
        resource: Dict = file_info.get("file", file_info)
        file_name = resource["name"]
        state = resource.get("state")

        # 等待文件状态为 ACTIVE
        while state == "PROCESSING":
            time.sleep(1)
            get_url = f"{self.base_url}/v1beta/{file_name}?key={self.api_key}"
            rr = self.client.get(get_url)
            rr.raise_for_status()
            info = rr.json()
            # This GET response returns the file resource fields at the top level
            resource = info  # Directly use info since there's no 'file' key here
            state = resource.get("state")

        if state != "ACTIVE":
            raise RuntimeError("Uploaded file is not ACTIVE")
        return resource["uri"], resource["name"]

    def _list_files(self):
        url = f"{self.base_url}/v1beta/files?key={self.api_key}"
        r = self.client.get(url)
        r.raise_for_status()
        return [file.get("name") for file in r.json().get("files", [])]

    def _delete_file(self, file_name: str):
        url = f"{self.base_url}/v1beta/{file_name}?key={self.api_key}"
        r = self.client.delete(url)
        r.raise_for_status()

    def _content_with_media(self, prompt: str, file: str) -> str:
        contents = []
        parts = []
        uploaded_files_info = []
        # 将文件先放，再放文本提示
        mime_type = self._get_mime_type(file)
        file_size = os.path.getsize(file)
        if file_size <= UPLOAD_LIMIT_BYTES:
            data_b64 = self._base64_encode_file(file)
            parts.append({"inline_data": {"mime_type": mime_type, "data": data_b64}})
        else:
            file_uri, file_name = self._upload_file(file)
            parts.append({"file_data": {"mime_type": mime_type, "file_uri": file_uri}})
            uploaded_files_info.append(file_name)

        # 最后加上文本提示
        parts.append({"text": prompt})
        contents.append({"parts": parts})

        url = f"{self.base_url}/v1beta/models/{self.settings.model}:generateContent?key={self.api_key}"
        r = self.client.post(
            url,
            json={
                "generationConfig": self.generation_config,
                "safetySettings": self.safe,
                "contents": contents,
            },
        )

        r.raise_for_status()
        resp = r.json()

        candidates = resp.get("candidates", [])
        if not candidates:
            return None

        texts = [
            p.get("text", "")
            for p in candidates[0].get("content", {}).get("parts", [])
            if p.get("text")
        ]
        result = "\n".join(texts) if texts else None

        # 删除上传的文件
        for fn in uploaded_files_info:
            self._delete_file(fn)

        return result

    def _content_with_text(self, prompt: str) -> str:
        contents = []
        parts = []

        parts.append({"text": prompt})
        contents.append({"parts": parts})

        url = f"{self.base_url}/v1beta/models/{self.settings.model}:generateContent?key={self.api_key}"
        r = self.client.post(
            url,
            json={
                "generationConfig": self.generation_config,
                "safetySettings": self.safe,
                "contents": contents,
            },
        )
        r.raise_for_status()
        response = r.json()

        if "candidates" not in response or not response["candidates"]:
            raise Exception("No response from Gemini API")

        return response["candidates"][0]["content"]["parts"][0]["text"]

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(min=10, max=20),
        after=push_cd,
        reraise=True,
    )
    def generate_content(self, prompt: str, media: str = None) -> str:
        if media:
            return self._content_with_media(prompt, media)
        else:
            return self._content_with_text(prompt)
