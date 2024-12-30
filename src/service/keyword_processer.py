import regex as re

from .llm import LLMFactory
from .prompt.normal import KEYWORD_PROMPT


class KeywordProcesser:
    def __init__(self):
        self.llm = LLMFactory.create_llm().unwrap()

    def get_keywords(self, content, media_desc):
        try:
            prompt = KEYWORD_PROMPT.format(
                TWEET_CONTENT=content,
                MEDIA_DESCRIPTION=media_desc,
            )
            keywords = self.llm.generate_content(prompt)
        except Exception:
            prompt = KEYWORD_PROMPT.format(
                TWEET_CONTENT=content[:-2],
                MEDIA_DESCRIPTION=media_desc[:-2],
            )
            keywords = self.llm.generate_content(prompt)
        match = re.search(r"<keywords>(.*?)</keywords>", keywords, re.DOTALL)
        return match.group(1) if match else keywords
