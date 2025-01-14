import regex as re

from .llm import LLMFactory
from .prompt.normal import KEYWORD_PROMPT


class KeywordProcesser:
    def __init__(self):
        self.llm = LLMFactory.create_llm().unwrap()

    def get_keywords(self, content, media_desc):
        keywords = self.llm.template_llmgen(
            KEYWORD_PROMPT,
            modifiable_params=["TWEET_CONTENT", "MEDIA_DESCRIPTION"],
            TWEET_CONTENT=content,
            MEDIA_DESCRIPTION=media_desc,
        ).unwrap()
        match = re.search(r"<keywords>(.*?)</keywords>", keywords, re.DOTALL)
        return match.group(1) if match else keywords
