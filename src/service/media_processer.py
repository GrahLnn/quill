from returns.result import Result, Success

from .llm import LLMFactory


class MediaProcessor:
    def __init__(self):
        self.llm_result = LLMFactory.create_llm()

    def describe(
        self,
        file_path: str,
        prompt: str = "Describe this media in detail. Only write your response.",
    ) -> Result[str, Exception]:
        return self.llm_result.bind(
            lambda llm: Success(llm.generate_content(prompt, file_path))
        )
