import random
import time
from abc import ABC, abstractmethod
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional

import httpx
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


# ========== Provider Enum ==========
class Provider(Enum):
    GEMINI = "gemini"
    LONGVU = "longvu"
    OPENAI = "openai"
    CLAUDE = "claude"
    GROQ = "groq"
    DEFAULT = "default"


# ========== LLMSettings Class ==========
class LLMSettings(BaseSettings):
    gemini_api_keys: Optional[List[str]] = Field(default=None, validate_default=True)
    openai_api_keys: Optional[List[str]] = Field(default=None, validate_default=True)
    claude_api_keys: Optional[List[str]] = Field(default=None, validate_default=True)

    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com")
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
    def validate_api_keys(cls, v):
        if v is None or not v:
            return []
        if isinstance(v, str):
            return v.split(",")
        return v

    @field_validator("client_type", mode="before")
    def validate_client_type(cls, v):
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


# ========== KeyManager Class ==========
class KeyManager:
    """Key 管理器，用于管理API Key在并发下的冷却使用"""

    def __init__(self, cooldown_time: int = 60):
        self.cooldown_time = cooldown_time
        self.cooldown_keys: Dict[str, float] = {}  # key->冷却结束时间
        self._lock = Lock()

    def _is_key_available(self, key: str) -> bool:
        if key not in self.cooldown_keys:
            return True
        return time.time() >= self.cooldown_keys[key]

    def mark_key_used(self, key: str):
        with self._lock:
            self.cooldown_keys[key] = time.time() + self.cooldown_time

    def get_available_key(self, keys: List[str]) -> Optional[str]:
        if not keys:
            raise ValueError("No API keys provided")
        with self._lock:
            random.shuffle(keys)
            for key in keys:
                if self._is_key_available(key):
                    return key

            # 没有可用的key，找到最短CD
            current_time = time.time()
            min_cooldown_time = float("inf")
            min_key = None
            for key in keys:
                if key in self.cooldown_keys:
                    remaining = self.cooldown_keys[key] - current_time
                    if remaining < min_cooldown_time:
                        min_cooldown_time = remaining
                        min_key = key

        # 等待CD结束
        if min_key and min_cooldown_time > 0:
            time.sleep(min_cooldown_time)
        with self._lock:
            # 再次移除CD限制
            if min_key in self.cooldown_keys:
                self.cooldown_keys.pop(min_key)
            return min_key


# ========== BaseClient Class ==========
class BaseClient(ABC):
    settings: LLMSettings = LLMSettings()
    key_manager: KeyManager = KeyManager()

    def __init__(self):
        self.client = httpx.Client(timeout=3600)

    @abstractmethod
    def generate_content(
        self, prompt: str, file_paths: Optional[List[str]] = None
    ) -> str:
        pass

    def close(self):
        self.client.close()
