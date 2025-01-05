import regex as re
import tiktoken
from langcodes import Language
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings
from returns.maybe import Maybe, Nothing, Some
from returns.result import Failure, Result, Success

from .llm import LLMFactory
from .prompt.translate_agent import (
    BASIC_TRANSLATION_PROMPT,
    IMPROVE_TRANSLATION_PROMPT,
    REFLECTION_TRANSLATION_PROMPT,
)

class LanguageSettings(BaseSettings):
    target_lang: str = Field(default="zh")

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        extra_sources=[],
    )

    @field_validator("target_lang")
    def validate_target_lang(cls, v: str) -> str:
        if not v:
            v = "zh"
        try:
            lang = Language.get(v)
            return str(lang)
        except Exception:
            valid_languages = [
                "en",
                "fr",
                "es",
                "de",
                "ja",
                "ko",
            ]
            suggestion = ", ".join(valid_languages)
            raise ValueError(
                f"Invalid language code: {v}. Here are some valid language codes: {suggestion}"
            )


class Translator:
    INVALID_LANGS = {"qme", "art", "zxx"}

    def __init__(self, source_lang, llm_type: str = "gemini"):
        self.settings = LanguageSettings()
        self.source_lang = Language.get(source_lang)
        self.target_lang = Language.get(self.settings.target_lang)

        # 初始化时判断是否需要翻译
        if not self._can_translate():
            self.llm = None  # 不需要翻译，不初始化 llm
        else:
            self.llm = LLMFactory.create_llm(llm_type).unwrap()

    def _can_translate(self) -> bool:
        """
        判断是否满足翻译条件。
        """
        if not self.source_lang or self.source_lang == self.target_lang:
            return False
        if self.source_lang.to_tag() in self.INVALID_LANGS:
            return False
        return True

    def _translate_round_one(self, text: str) -> Result[str, Exception]:
        prompt = BASIC_TRANSLATION_PROMPT.format(
            target_lang=self.target_lang.display_name(),
            text=text,
        )
        response = self.llm.generate_content(prompt)
        # 使用正则表达式提取 <translation> 标签中的内容
        pattern = r"<translation>(.*?)</translation>"
        match = re.search(pattern, response, re.DOTALL)
        if not match:
            return Failure(ValueError("No translation tags found in response"))
        return Success(match.group(1).strip())

    def _translate_round_two(self, text: str, round_1: str) -> Result[str, Exception]:
        prompt = REFLECTION_TRANSLATION_PROMPT.format(
            target_lang=self.target_lang.display_name(),
            text=text,
            round_1=round_1,
        )
        return Success(self.llm.generate_content(prompt))

    def _translate_round_three(
        self, text: str, round_1: str, round_2: str
    ) -> Result[str, Exception]:
        prompt = IMPROVE_TRANSLATION_PROMPT.format(
            target_lang=self.target_lang.display_name(),
            source_text=text,
            initial_translation=round_1,
            expert_suggestions=round_2,
        )
        response = self.llm.generate_content(prompt)
        pattern = r"<improved_translation>(.*?)</improved_translation>"
        match = re.search(pattern, response, re.DOTALL)
        if not match:
            return Failure(ValueError("No translation tags found in response"))
        return Success(match.group(1).strip())

    def _tokens_length(self, text: str) -> bool:
        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))

    def translate(self, text: str) -> Maybe[str]:
        BOUNDARY = 20
        if self.llm is None or not text:
            return Nothing

        enc = tiktoken.get_encoding("o200k_base")
        if self.source_lang.to_tag() == "und" and len(enc.encode(text)) > BOUNDARY:
            prompt = f"{text}\n\nIs there any part of the above content in natural language? Please reply with yes or no."
            result = self.llm.generate_content(prompt)
            if "no" in result.lower():
                return Nothing

        if self.target_lang.to_tag() == "zh":
            self.target_lang = Language.get("zh-Hans")

        # TODO: if has media, include media description as context
        if len(enc.encode(text)) > BOUNDARY:
            round_1_result = self._translate_round_one(text).unwrap()
            round_2_result = self._translate_round_two(text, round_1_result).unwrap()
            result = self._translate_round_three(
                text, round_1_result, round_2_result
            ).unwrap()
        else:
            result = self._translate_round_one(text).unwrap()
        return Some(result.strip())
