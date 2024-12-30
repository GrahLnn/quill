KEYWORD_PROMPT = """You are tasked with analyzing information from a tweet, including its textual content and any visual elements described. Your goal is to identify all potential topics, both primary and secondary, as well as any topics that might be inferred or associated through implication.

Follow these guidelines in your analysis:
1. Don't rely solely on explicitly stated topics. Use inference and association to uncover implicit topics.
2. Incorporate the visual element descriptions into your analysis. UI elements (such as buttons, windows, layout) described may suggest related topics.
3. Integrate keywords from all relevant topics you identify.

Here is the information to analyze:

Tweet content:
<tweet_content>
{TWEET_CONTENT}
</tweet_content>

Media description:
<media_description>
{MEDIA_DESCRIPTION}
</media_description>

Process the information as follows:
1. Carefully read both the tweet content and media description.
2. Identify explicit topics mentioned in the text.
3. Infer implicit topics based on the content and context.
4. Consider any visual elements described and what topics they might suggest.
5. Think about possible associations or implications from all identified topics.
6. Compile a list of keywords that represent all the topics you've identified.

After your analysis, provide your output as a keyword array. Use the following format:

<keywords>keyword1, keyword2, keyword3, keyword4, keyword5, ..., keywordN</keywords>

Ensure that your array includes all relevant keywords, representing both explicit and implicit topics, as well as any associated concepts you've identified through your analysis."""