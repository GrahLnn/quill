KEYWORD_PROMPT = """You are tasked with generating keywords (tags) based on tweet content and related media descriptions. Your goal is to create domain-specific keywords that focus on the core theme and industry attributes of the content.

First, carefully read the following tweet content:
<tweet_content>
{TWEET_CONTENT}
</tweet_content>

Now, review the related media descriptions:
<media_descriptions>
{MEDIA_DESCRIPTIONS}
</media_descriptions>

To generate appropriate keywords, follow these steps:

1. Analyze the tweet content and media descriptions thoroughly.
2. Identify the main topic or theme of the tweet.
3. Determine the industry or domain the content relates to.
4. Look for specific terms, concepts, or jargon related to that industry.
5. Consider any prominent features, actions, or ideas mentioned in the content.
6. Think about potential audience interests related to the content.

When creating your keywords:
- Focus on domain-specific terms that accurately represent the content.
- Prioritize words that capture the core theme and industry attributes.
- Include both broad and specific terms to cover different aspects of the content.
- Avoid generic words that don't add value to understanding the content's focus.
- Ensure each keyword is relevant and adds unique information.

Format your response as follows:
1. List your keywords, separated by commas.
2. Enclose your entire list of keywords within <keywords> tags.
3. Aim for 5-10 keywords, depending on the complexity and depth of the content.

For example:
<keywords>artificial intelligence, machine learning, data analytics, predictive modeling, AI ethics</keywords>

Remember, the keywords should be concise yet informative, allowing someone to quickly understand the main focus and industry relevance of the tweet content."""