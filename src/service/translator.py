import tiktoken
from langcodes import Language
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings
from returns.maybe import Maybe, Nothing, Some
from returns.result import Result, Success

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
            self.llm_result = None  # 不需要翻译，不初始化 llm
        else:
            self.llm_result = LLMFactory.create_llm(llm_type)

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
        return self.llm_result.bind(lambda llm: Success(llm.generate_content(prompt)))

    def _translate_round_two(self, text: str, round_1: str) -> Result[str, Exception]:
        prompt = REFLECTION_TRANSLATION_PROMPT.format(
            target_lang=self.target_lang.display_name(),
            text=text,
            round_1=round_1,
        )
        return self.llm_result.bind(lambda llm: Success(llm.generate_content(prompt)))

    def _translate_round_three(
        self, text: str, round_1: str, round_2: str
    ) -> Result[str, Exception]:
        prompt = IMPROVE_TRANSLATION_PROMPT.format(
            target_lang=self.target_lang.display_name(),
            text=text,
            round_1=round_1,
            round_2=round_2,
        )
        return self.llm_result.bind(lambda llm: Success(llm.generate_content(prompt)))

    def translate(self, text: str) -> Maybe[str]:
        BOUNDARY = 20
        if self.llm_result is None or not text:
            return Nothing

        enc = tiktoken.get_encoding("o200k_base")
        if self.source_lang.to_tag() == "und" and len(enc.encode(text)) > BOUNDARY:
            prompt = f"{text}\n\nIs there any part of the above content in natural language? Please reply with yes or no."
            result = self.llm_result.bind(
                lambda llm: Success(llm.generate_content(prompt))
            ).unwrap()
            if "no" in result.lower():
                return Nothing

        if self.target_lang.to_tag() == "zh":
            self.target_lang = Language.get("zh-Hans")

        if len(enc.encode(text)) > BOUNDARY:
            round_1_result = self._translate_round_one(text).unwrap()
            round_2_result = self._translate_round_two(text, round_1_result).unwrap()
            result = self._translate_round_three(
                text, round_1_result, round_2_result
            ).unwrap()
        else:
            result = self._translate_round_one(text).unwrap()
        return Some(result.strip())
