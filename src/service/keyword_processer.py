from typing import Dict
import regex as re

from .helper import get
from .llm import LLMFactory
from .prompt.normal import KEYWORD_PROMPT


class KeywordProcesser:
    def __init__(self):
        self.llm = LLMFactory.create_llm().unwrap()

    def get_keywords(self, content, media_desc):
        prompt = KEYWORD_PROMPT.format(
            TWEET_CONTENT=content,
            MEDIA_DESCRIPTIONS=media_desc,
        )
        keywords = self.llm.generate_content(prompt)
        return re.sub(r"^<[^>]+>|<[^>]+>$", "", keywords)
