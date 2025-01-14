from returns.result import Result, Success, Failure
from .models.gemini import BaseClient, GeminiClient


class LLMFactory:
    @staticmethod
    def create_llm(llm_type: str = "gemini"):
        match llm_type.lower():
            case "gemini":
                return Success(GeminiClient())
            case _:
                return Failure(ValueError(f"不支持的LLM类型: {llm_type}"))
