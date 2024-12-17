from langcodes import Language
from pydantic import Field, field_validator
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        extra_sources = []

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
    INVALID_LANGS = {"qme", "und"}

    def __init__(self, source_lang, llm_type: str = "gemini"):
        self.llm_result = LLMFactory.create_llm(llm_type)
        self.settings = LanguageSettings()
        self.source_lang = Language.get(source_lang)
        self.target_lang = Language.get(self.settings.target_lang)

    def _translate_round_one(self, text: str) -> Result[str, Exception]:
        prompt = BASIC_TRANSLATION_PROMPT.format(
            source_lang=self.source_lang.display_name(),
            target_lang=self.target_lang.display_name(),
            text=text,
        )
        return self.llm_result.bind(lambda llm: Success(llm.generate_content(prompt)))

    def _translate_round_two(self, text: str, round_1: str) -> Result[str, Exception]:
        prompt = REFLECTION_TRANSLATION_PROMPT.format(
            source_lang=self.source_lang.display_name(),
            target_lang=self.target_lang.display_name(),
            text=text,
            round_1=round_1,
        )
        return self.llm_result.bind(lambda llm: Success(llm.generate_content(prompt)))

    def _translate_round_three(
        self, text: str, round_1: str, round_2: str
    ) -> Result[str, Exception]:
        prompt = IMPROVE_TRANSLATION_PROMPT.format(
            source_lang=self.source_lang.display_name(),
            target_lang=self.target_lang.display_name(),
            text=text,
            round_1=round_1,
            round_2=round_2,
        )
        return self.llm_result.bind(lambda llm: Success(llm.generate_content(prompt)))

    def translate(self, text: str) -> Maybe[str]:
        if not text or self.source_lang == self.target_lang or self.source_lang.to_tag() in self.INVALID_LANGS:
            return Nothing

        if self.target_lang.to_tag() == "zh":
            self.target_lang = Language.get("zh-Hans")

        round_1_result = self._translate_round_one(text).unwrap()
        round_2_result = self._translate_round_two(text, round_1_result).unwrap()
        round_3_result = self._translate_round_three(
            text, round_1_result, round_2_result
        ).unwrap()
        return Some(round_3_result.strip())
