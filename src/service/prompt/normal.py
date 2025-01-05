KEYWORD_PROMPT = """You are an advanced AI system specialized in analyzing social media content, particularly tweets. Your task is to identify and extract a comprehensive list of topics and concepts from a given tweet and its associated media description.

Here is the description of any media associated with the tweet:

<media_description>
{MEDIA_DESCRIPTION}
</media_description>

Here is the tweet content you need to analyze:

<tweet_content>
{TWEET_CONTENT}
</tweet_content>

Your objective is to generate a list of keywords that represent all potential topics, both primary and secondary, as well as any topics that might be inferred or associated through implication. Follow these guidelines:

1. Consider both explicit and implicit topics.
2. Incorporate information from the visual elements described in the media description.
3. Use inference and association to uncover related concepts.
4. Focus on nouns with semantic meaning as keywords.
5. Exclude non-semantic elements like serial numbers, version numbers, or other identifiers without inherent topical meaning.

Before providing your final list of keywords, wrap your thought process in <topic_extraction> tags. In your analysis, please:

1. Quote relevant parts of the tweet content and media description.
2. List explicit topics mentioned in the tweet content.
3. Infer and list implicit topics based on the content and context.
4. List topics suggested by the visual elements described in the media description.
5. For each identified topic, consider and list possible associations or implications.
6. Compile a preliminary list of keywords, numbering each one as it's added.
7. Filter the list to ensure all keywords are nouns with semantic meaning.

It's OK for this section to be quite long.

After your analysis, provide your output as a comma-separated list of keywords in <keywords> tags. Ensure that your list includes all relevant keywords in English, representing both explicit and implicit topics, as well as any associated concepts you've identified through your analysis.

Example output format:

<topic_extraction>
[Your detailed analysis here]
</topic_extraction>

<keywords>keyword1, keyword2, keyword3, ..., keywordN</keywords>

Remember, the keywords should be comprehensive yet focused, capturing the essence of the tweet and its associated media while adhering to the guidelines provided."""
