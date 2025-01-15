import base64
import logging
import os
import time
from typing import Dict, List, Tuple

import httpx
from returns.result import Failure, Result, Success
from tenacity import (
    RetryCallState,
    retry,
    retry_if_not_exception_type,
    wait_fixed,
)

from ..base import BaseClient, LLMSettings
from ..helper import get, random_insert_substring

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


class NonRetryableException(Exception):
    """用于标记不可重试的异常"""

    pass


def push_cd(retry_state: RetryCallState):
    instance: GeminiClient = retry_state.args[0]
    # path = retry_state.args[2]
    if retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        # print(f"retrying...{exc}")
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code == 429:
                # 遇到429错误，mark key used
                instance.key_manager.mark_key_cooldown(instance.api_key)


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
        self.api_key = key
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
        try:
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
                for f in uploaded_files_info:
                    self._delete_file(f)
                return None

            texts = [
                p.get("text", "")
                for p in candidates[0].get("content", {}).get("parts", [])
                if p.get("text")
            ]
            result = "\n".join(texts) if texts else None
        finally:
            for f in uploaded_files_info:
                self._delete_file(f)
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

        if "candidates" not in response:
            raise NonRetryableException(f"No response from Gemini API: {response=}")
        content = get(response, "candidates.0.content.parts.0.text")
        if content:
            return content
        raise NonRetryableException(f"Error response from Gemini API: {response=}")

    def get_retry_count(self) -> int:
        """获取重试次数，为API key数量"""
        return len(self.settings.gemini_api_keys) + 48

    @retry(
        stop=lambda retry_state: retry_state.attempt_number
        > retry_state.args[0].get_retry_count(),
        wait=wait_fixed(1),
        after=push_cd,
        retry=retry_if_not_exception_type(NonRetryableException),
        reraise=True,
    )
    def llmgen_content(self, prompt: str, media: str = None) -> str:
        with self.key_manager.context(self.settings.gemini_api_keys) as key:
            self.api_key = key
            if media:
                return self._content_with_media(prompt, media)
            else:
                return self._content_with_text(prompt)

    def template_llmgen(
        self, template: str, modifiable_params: List[str], **kwargs
    ) -> Result:
        """
        使用模板和参数生成内容，若失败则对指定参数进行随机插入后重试。

        :param template: 模板字符串，其中包含格式化占位符。
        :param modifiable_params: 允许进行随机插入的参数名列表。
        :param kwargs: 格式化模板所需的关键字参数。
        :return: Success 或 Failure 对象。
        """
        try:
            prompt = template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"缺少必要的格式化参数: {e}")
        error = None
        for i in range(10):
            try:
                answer = self.llmgen_content(prompt)
                return Success(answer)
            except Exception as e:
                error = e
                for param in modifiable_params:
                    if param in kwargs and isinstance(kwargs[param], str):
                        kwargs[param] = random_insert_substring(
                            kwargs[param], 5 * (i + 2)
                        )

                # 重新生成 prompt
                try:
                    prompt = template.format(**kwargs)
                except KeyError as e:
                    raise ValueError(f"缺少必要的格式化参数: {e}")

        return Failure(ValueError(f"Failed to generate content {error}"))
