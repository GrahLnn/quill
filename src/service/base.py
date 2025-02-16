import random
import time
from abc import ABC, abstractmethod
from collections import deque
from enum import Enum
from threading import Condition, Lock
from typing import Any, Dict, List, Optional

import httpx
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


# ========== Provider Enum ==========
class Provider(Enum):
    GEMINI = "gemini"
    LONGVU = "longvu"
    OPENAI = "openai"
    CLAUDE = "claude"
    GROQ = "groq"
    DEFAULT = "default"


ProviderModel = {
    "gemini": Provider.GEMINI,
    "gpt": Provider.OPENAI,
    "claude": Provider.CLAUDE,
}


# TODO: need more automation
# ========== LLMSettings Class ==========
class LLMSettings(BaseSettings):
    gemini_api_keys: Optional[List[str]] = Field(default=None, validate_default=True)
    openai_api_keys: Optional[List[str]] = Field(default=None, validate_default=True)
    claude_api_keys: Optional[List[str]] = Field(default=None, validate_default=True)

    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com")
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    claude_base_url: str = Field(default="https://api.claude.ai/api/v1")

    client_type: Provider = Field(default=None, validate_default=True)
    model: str = Field(default="gemini-2.0-flash-exp")

    rpm: int = Field(default=10)
    allow_concurrent: bool = Field(default=False)

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        extra_sources=[],
    )

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
        if v is None:
            return Provider.DEFAULT

        raise ValueError(f"Expected string or Provider instance, got {type(v)}")

    @field_validator("rpm")
    def validate_rpm(cls, v):
        if isinstance(v, str):
            return int(v)
        return v

    @field_validator("allow_concurrent")
    def validate_allow_concurrent(cls, v):
        if isinstance(v, str):
            return v.lower() == "true"
        return v

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


settings = LLMSettings()


# ========== KeyManager Class ==========
class KeyManager:
    def __init__(
        self, rpm: int = 15, allow_concurrent: bool = False, cooldown_time: int = 60
    ):
        """
        :param rpm: 每分钟每个密钥可用的请求次数上限
        :param allow_concurrent: 是否允许同一密钥在同一时间段内被并发使用
        :param cooldown_time: 密钥进入冷却状态的持续时间（秒）
        """
        self.rpm = rpm
        self.allow_concurrent = allow_concurrent
        self.cooldown_time = cooldown_time

        # 每个密钥对应的请求时间戳队列，用于计算 RPM 限制
        self.request_counts: Dict[str, deque] = {}

        # 冷却中的密钥，值为冷却结束的时间戳
        self.cooldown_keys: Dict[str, float] = {}
        # 连续冷却计数
        self.consecutive_cooldown_counts: Dict[str, int] = {}

        # 当前被占用的密钥（如果不允许并发，则同一时间只允许一个线程占用某个特定密钥）
        self.occupied_keys: set = set()

        self._lock = Lock()
        self._condition = Condition(self._lock)

    def _hash_key(self, key: Any) -> str:
        """生成密钥的哈希表示，用于内部管理"""
        return str(hash(str(key)))

    def _clean_old_requests(self, internal_key: str, current_time: float):
        """移除超过60秒之前的请求记录以适应 RPM 限制"""
        if internal_key not in self.request_counts:
            self.request_counts[internal_key] = deque()
        rq = self.request_counts[internal_key]
        while rq and rq[0] <= current_time - 60:
            rq.popleft()

    def _is_key_available(self, internal_key: str, current_time: float) -> bool:
        """
        检查key在当前时刻是否可用：
        - 若仍在cooldown或ban中则不可用
        - 若cooldown/ban过期则恢复可用
          * 若是ban过期，则重置计数器为0
          * 若只是普通cooldown过期，不重置计数器（继续累积）
        """
        if internal_key in self.cooldown_keys:
            if current_time < self.cooldown_keys[internal_key]:
                # 仍在cooldown/ban中
                return False
            else:
                del self.cooldown_keys[internal_key]

        # 检查RPM限制
        self._clean_old_requests(internal_key, current_time)
        if len(self.request_counts[internal_key]) >= self.rpm:
            return False

        # 检查并发占用
        if not self.allow_concurrent and internal_key in self.occupied_keys:
            return False

        return True

    def _get_wait_time_for_key(self, internal_key: str, current_time: float) -> float:
        """
        计算下一个该密钥可能变为可用状态的等待时间（秒）。
        如不可计算或需要等待很久，则返回相对时间。可能为0表示无需等待。
        """
        wait_time = 0.0

        # 如果在冷却中
        if (
            internal_key in self.cooldown_keys
            and current_time < self.cooldown_keys[internal_key]
        ):
            wait_time = max(wait_time, self.cooldown_keys[internal_key] - current_time)

        # 如果达到了 RPM 限制，需要等待最早一次请求时间戳满60秒后再重试
        if (
            internal_key in self.request_counts
            and len(self.request_counts[internal_key]) >= self.rpm
        ):
            oldest_request = self.request_counts[internal_key][0]
            rpm_wait = (oldest_request + 60) - current_time
            wait_time = max(wait_time, rpm_wait)

        # 并发限制下，如果密钥被占用，也许只能等它被释放
        if not self.allow_concurrent and internal_key in self.occupied_keys:
            # 这里无法精确计算等待时间，只能设置为0，等待条件变量通知
            wait_time = max(wait_time, 0)

        return wait_time

    def mark_key_used(self, key: Any):
        """标记密钥被使用一次，并添加请求时间戳"""
        internal_key = self._hash_key(key)
        with self._lock:
            current_time = time.time()
            self._clean_old_requests(internal_key, current_time)
            self.request_counts[internal_key].append(current_time)
            if not self.allow_concurrent:
                self.occupied_keys.add(internal_key)
            self._condition.notify_all()

    def release_key(self, key: Any):
        """释放密钥占用"""
        internal_key = self._hash_key(key)
        with self._lock:
            if internal_key in self.occupied_keys:
                self.occupied_keys.remove(internal_key)
            self._condition.notify_all()

    def mark_key_cooldown(self, key: Any):
        """将密钥标记为进入冷却状态，如果连续3次进入长时冷却"""
        internal_key = self._hash_key(key)
        with self._lock:
            current_time = time.time()
            self.consecutive_cooldown_counts[internal_key] = (
                self.consecutive_cooldown_counts.get(internal_key, 0) + 1
            )

            if self.consecutive_cooldown_counts[internal_key] >= 3:
                self.cooldown_keys[internal_key] = current_time + 3600  # 1小时冷却
            else:
                self.cooldown_keys[internal_key] = current_time + self.cooldown_time

            if internal_key in self.occupied_keys:
                self.occupied_keys.remove(internal_key)
            self._condition.notify_all()

    def get_available_key(self, keys: List[Any]) -> Any:
        """获取一个可用的密钥，如果没有可用的则阻塞等待"""
        if not keys:
            raise ValueError("未提供任何 API 密钥")

        with self._lock:
            while True:
                current_time = time.time()
                shuffled_keys = keys.copy()
                random.shuffle(shuffled_keys)

                available_keys = []
                for key in shuffled_keys:
                    internal_key = self._hash_key(key)
                    if self._is_key_available(internal_key, current_time):
                        available_keys.append(key)

                if available_keys:
                    # 优先选择未被占用的密钥
                    for key in available_keys:
                        internal_key = self._hash_key(key)
                        if (
                            self.allow_concurrent
                            or internal_key not in self.occupied_keys
                        ):
                            self._clean_old_requests(internal_key, current_time)
                            if not self.allow_concurrent:
                                self.occupied_keys.add(internal_key)
                            return key

                # 判断是否有密钥仅被占用但未冷却
                occupied_only = [
                    key
                    for key in keys
                    if self._hash_key(key) in self.occupied_keys
                    and self._hash_key(key) not in self.cooldown_keys
                ]

                if occupied_only:
                    # 等待被占用的密钥被释放
                    self._condition.wait()
                    continue  # 重新检查密钥状态

                # 如果没有仅被占用的密钥，计算最小等待时间
                min_wait_time = float("inf")
                for key in keys:
                    internal_key = self._hash_key(key)
                    wait_time = self._get_wait_time_for_key(internal_key, current_time)
                    if wait_time < min_wait_time:
                        min_wait_time = wait_time

                if min_wait_time == float("inf"):
                    raise RuntimeError("无法确定密钥的等待时间，可能没有可用密钥。")

                if min_wait_time >= 4 * 3600:
                    total_keys = len(keys)
                    cooling_keys = len(self.cooldown_keys)
                    cooldown_info = ", ".join(
                        f"{k}: {(v - current_time) / 3600:.1f}h"
                        for k, v in self.cooldown_keys.items()
                    )
                    print(
                        f"All keys are unavailable, most likely due to daily API limits. "
                        f"Will retry in {min_wait_time / 3600:.1f} hours, or interrupt the program to add new keys. "
                        f"(Total keys: {total_keys}, Cooling down: {cooling_keys}, "
                        f"Cooldown times: {cooldown_info})"
                    )

                # 等待最小的等待时间，或者在等待被释放时唤醒
                wait_time = min_wait_time if min_wait_time > 0 else None
                self._condition.wait(timeout=wait_time)

    def context(self, keys: List[Any]):
        """
        上下文管理器，用于自动释放密钥。例如：
            with key_manager.context(keys) as key:
                # 使用 key 进行请求
        """

        class KeyContext:
            def __init__(self, manager: KeyManager, key: Any):
                self.manager = manager
                self.key = key
                self.entered = False

            def __enter__(self):
                # 在进入上下文时标记使用请求数+1
                self.manager.mark_key_used(self.key)
                self.entered = True
                return self.key

            def __exit__(self, exc_type, exc_val, exc_tb):
                # 无论成功或失败，都释放密钥占用
                if self.entered:
                    # 如果没有异常发生，说明key使用成功，重置连续冷却计数
                    if exc_type is None:
                        internal_key = self.manager._hash_key(self.key)
                        self.manager.consecutive_cooldown_counts[internal_key] = 0
                    self.manager.release_key(self.key)

        key = self.get_available_key(keys)
        return KeyContext(self, key)


# ========== BaseClient Class ==========
class BaseClient(ABC):
    settings: LLMSettings = LLMSettings()
    key_manager: KeyManager = KeyManager()

    def __init__(self):
        self.client = httpx.Client(timeout=3600)

    @abstractmethod
    def llmgen_content(
        self, prompt: str, file_paths: Optional[List[str]] = None
    ) -> str:
        pass

    def close(self):
        self.client.close()
