from .llm import LLMFactory


class MediaProcessor:
    """
    媒体处理类
    """

    def __init__(self, llm_type: str = "gemini"):
        self.llm = LLMFactory.create_llm(llm_type)

    def describe(
        self,
        file_path: str,
        prompt: str = "Describe this media in detail. Only write your response.",
    ) -> str:
        """
        使用LLM处理媒体文件
        """

        return self.llm.aeiou(file_path, prompt)
