from typing import Optional

import ell
import openai
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class InsuranceSettings(BaseSettings):
    api_key: Optional[str] = Field(default=None, validation_alias="LAST_LLM_RESORT_KEY")
    endpoint: Optional[str] = Field(
        default=None, validation_alias="LAST_LLM_RESORT_ENDPOINT"
    )
    model: Optional[str] = Field(default=None, validation_alias="LAST_LLM_RESORT_MODEL")

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        extra_sources=[],
    )


class InsuranceClient:
    def __init__(self, model: Optional[str] = None):
        self.settings = InsuranceSettings()
        self.llm = openai.Client(
            api_key=self.settings.api_key, base_url=self.settings.endpoint
        )
        self.model = model or self.settings.model

    def ask(self, prompt: str):
        @ell.simple(model=self.model, client=self.llm)
        def do(prompt):
            return prompt

        return do(prompt)
