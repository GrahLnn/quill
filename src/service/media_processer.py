from returns.result import Result, Success

from .llm import LLMFactory


class MediaProcessor:
    def __init__(self):
        self.llm = LLMFactory.create_llm().unwrap()

    def describe(
        self,
        file_path: str,
        prompt: str = "Describe this media in detail, only show the describtion in English.",
    ) -> Result[str, Exception]:
        return Success(self.llm.llmgen_content(prompt, file_path))
