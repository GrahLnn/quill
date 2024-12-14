import base64
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from tenacity import RetryCallState, retry, stop_after_attempt, wait_fixed


class Platform(Enum):
    GEMINI = "gemini"
    LONGVU = "longvu"
    OPENAI = "openai"
    CLAUDE = "claude"
    GROQ = "groq"


class Provider(Enum):
    GEMINI = Platform.GEMINI.value
    LONGVU = Platform.LONGVU.value
    OPENAI = Platform.OPENAI.value
    CLAUDE = Platform.CLAUDE.value
    GROQ = Platform.GROQ.value
    DEFAULT = "default"


def push_cd(retry_state: RetryCallState):
    """在重试前进入CD（按排除条件）"""
    instance: GeminiLLM = retry_state.args[0]  # 获取类实例 (self)
    if retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        error_message = str(exc)

        # 这里以字符串匹配为例，如果是包含特定文本的ValueError则不进CD
        # 可以根据需要调整判断逻辑
        if (
            isinstance(exc, ValueError)
            and "The `response.text` quick accessor requires" in error_message
        ):
            # 如果匹配到这类特定错误，不进行mark_key_used
            # raise exc
            return
        else:
            # 对其他异常情况进行CD标记
            instance._key_manager.mark_key_used(instance.key)


class LLMSettings(BaseSettings):
    gemini_api_keys: Optional[List[str]] = Field(default=None, validate_default=True)
    openai_api_keys: Optional[List[str]] = Field(default=None, validate_default=True)
    claude_api_keys: Optional[List[str]] = Field(default=None, validate_default=True)

    gemini_base_url: str = Field(default="https://api.gemini.com/v1")
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    claude_base_url: str = Field(default="https://api.claude.ai/api/v1")

    client_type: Provider = Field(default=Provider.DEFAULT, validate_default=True)
    model: str = Field(default="gemini-2.0-flash-exp")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        extra_sources = []

    @field_validator(
        "gemini_api_keys", "openai_api_keys", "claude_api_keys", mode="before"
    )
    def validate_api_keys(cls, v: str):
        if v is None or not v:
            return []
        return v.split(",")

    @field_validator("client_type", mode="before")
    def validate_client_type(cls, v: str):
        if isinstance(v, Provider):
            return v
        if isinstance(v, str):
            try:
                return Provider[v.upper()]
            except KeyError:
                valid_providers = ", ".join([p.name.lower() for p in Provider])
                raise ValueError(
                    f"Invalid provider '{v}'. Must be one of: {valid_providers}"
                )
        raise ValueError(f"Expected string or Provider instance, got {type(v)}")

    def choose_key(self, provider: Provider):
        match provider:
            case Provider.OPENAI:
                if not self.openai_api_keys:
                    raise ValueError("No OpenAI API keys provided")
                return random.choice(self.openai_api_keys)
            case Provider.CLAUDE:
                if not self.claude_api_keys:
                    raise ValueError("No Claude API keys provided")
                return random.choice(self.claude_api_keys)
            case Provider.GEMINI:
                if not self.gemini_api_keys:
                    raise ValueError("No Gemini API keys provided")
                return random.choice(self.gemini_api_keys)
            case _:
                raise ValueError(f"Invalid provider: {provider}, can not choose key")


@dataclass
class BaseLLM(ABC):
    """
    LLM基类，定义基本接口
    """

    settings: LLMSettings = field(default_factory=LLMSettings)

    @abstractmethod
    def aeiou(self, content: List[Any], safety_settings: Dict) -> Any:
        pass

    @abstractmethod
    def _setup_model(self) -> None:
        pass


class KeyManager:
    """Key管理器，处理API密钥的冷却时间"""

    def __init__(self, cooldown_time: int = 30):
        self.cooldown_time = cooldown_time
        self.cooldown_keys: Dict[str, float] = {}  # key -> 冷却结束时间
        self._lock = Lock()

    def _is_key_available(self, key: str) -> bool:
        """内部方法，在已经获得锁的情况下检查key是否可用"""
        if key not in self.cooldown_keys:
            return True
        is_available = time.time() >= self.cooldown_keys[key]
        return is_available

    def mark_key_used(self, key: str) -> None:
        with self._lock:
            self.cooldown_keys[key] = time.time() + self.cooldown_time

    def get_available_key(self, keys: List[str]) -> Optional[str]:
        if not keys:
            raise ValueError("No API keys provided")

        with self._lock:
            random.shuffle(keys)
            # 首先尝试找到一个可用的key
            for key in keys:
                if self._is_key_available(key):
                    return key

            # 如果没有可用的key，找出剩余CD时间最短的key
            current_time = time.time()
            min_cooldown_time = float("inf")
            min_cooldown_key = None

            for key in keys:
                if key in self.cooldown_keys:
                    remaining_time = self.cooldown_keys[key] - current_time
                    if remaining_time < min_cooldown_time:
                        min_cooldown_time = remaining_time
                        min_cooldown_key = key

        # 到这里锁已经被释放
        # 如果找到最短CD的key，先等待其CD结束
        if min_cooldown_key and min_cooldown_time > 0:
            time.sleep(min_cooldown_time)

        with self._lock:
            # 再次获取锁后，从冷却字典中移除该key的CD限制
            if min_cooldown_key in self.cooldown_keys:
                self.cooldown_keys.pop(min_cooldown_key)
            return min_cooldown_key


class LLMFactory:
    """
    LLM工厂类
    """

    @staticmethod
    def create_llm(llm_type: str) -> BaseLLM:
        match llm_type.lower():
            case "gemini":
                return GeminiLLM()
            case _:
                raise ValueError(f"不支持的LLM类型: {llm_type}")


class GeminiLLM(BaseLLM):
    """
    Gemini LLM实现
    """

    _key_manager = KeyManager()
    key: Optional[str] = None

    def __init__(self):
        super().__init__()

    def _setup_model(self) -> genai.GenerativeModel:
        if not self.settings.gemini_api_keys:
            raise ValueError("No Gemini API keys available in settings")

        self.key = self._key_manager.get_available_key(self.settings.gemini_api_keys)
        if not self.key:
            raise ValueError(
                "No available API keys at the moment. All keys are in cooldown."
            )
        genai.configure(api_key=self.key, transport="rest")

        generation_config = {
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        }

        return genai.GenerativeModel(
            model_name=self.settings.model,
            generation_config=generation_config,
        )

    @retry(stop=stop_after_attempt(10), after=push_cd, reraise=True)
    def aeiou(self, file_path, prompt) -> str:
        # 处理媒体文件
        media_file = MediaFile(file_path, Platform.GEMINI)
        # 准备内容
        content = [prompt, media_file.get_content_for_llm()]
        # 设置安全设置
        safety_settings = {
            "harassment": HarmBlockThreshold.BLOCK_NONE,
            "hate": HarmBlockThreshold.BLOCK_NONE,
            "sex": HarmBlockThreshold.BLOCK_NONE,
            "danger": HarmBlockThreshold.BLOCK_NONE,
        }
        model = self._setup_model()
        response = model.generate_content(content, safety_settings=safety_settings)
        return response.text


class MediaFile:
    """
    媒体文件类，用于封装媒体文件的处理逻辑
    """

    def __init__(self, file_path: str, platform: Platform):
        self.file_path = file_path
        self.platform = platform

    def _get_mime_type(self) -> str:
        """
        根据文件扩展名返回对应的MIME类型
        只返回支持的图片和视频格式
        """
        SUPPORTED_MIMES = {
            # 图片格式
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".heic": "image/heic",
            ".heif": "image/heif",
            # 视频格式
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

        ext = os.path.splitext(self.file_path)[1].lower()
        if ext not in SUPPORTED_MIMES:
            raise ValueError(
                f"不支持的文件格式: {ext}。支持的格式: {', '.join(SUPPORTED_MIMES.keys())}"
            )

        return SUPPORTED_MIMES[ext]

    def _process_file_for_gemini(self) -> Tuple[Any, str]:
        """
        根据文件大小处理媒体文件
        小于20MB的文件使用base64编码
        大于20MB的文件使用上传方式
        """
        file_size = os.path.getsize(self.file_path)
        size_limit = 19 * 1024 * 1024

        if file_size < size_limit:
            with open(self.file_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8"), "base64"
        else:
            media = genai.upload_file(self.file_path)
            while media.state.name == "PROCESSING":
                time.sleep(1)
                media = genai.get_file(media.name)
            return media, "upload"

    def get_content_for_llm(self) -> Dict[str, str]:
        """
        返回适用于LLM的内容格式
        """
        match self.platform:
            case Platform.GEMINI:
                content, process_type = self._process_file_for_gemini()
                if process_type == "base64":
                    return {
                        "mime_type": self._get_mime_type(),
                        "data": content,
                    }
                return content
