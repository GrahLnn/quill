BASIC_TRANSLATION_PROMPT = """You are a professional translator tasked with translating a portion of text into a specified target language. Follow these instructions carefully:

<context>
{context}
</context>

1. Here is the text you need to translate:
<text_to_translate>
{text}
</text_to_translate>

2. Translate the above text into {target_lang}.

3. Follow these guidelines for your translation:
   a. Translate ALL content provided in the text_to_translate section.
   b. Maintain the original paragraph structure and line breaks.
   c. Preserve all markdown, image links, LaTeX code, and titles exactly as they appear in the original text.
   d. Do not omit or remove any lines from the provided content.
   e. Translate even single titles or titles containing incomplete paragraphs.
   f. Do not include the source text in your output.
   g. Keep in mind that the source text from tweets, so maintain any relevant style or tone.
   h. Do not use additional markdown symbols if not in original text, but feel free to use Unicode to make it more readable.

4. Output only the new translation in {target_lang}. Do not include any additional comments, explanations, or the original text.

5. Enclose your translation in <translation> tags.

Begin your translation now.
"""

REFLECTION_TRANSLATION_PROMPT = """Your task is to carefully read a source text and part of a translation of that text to {target_lang}, and then give constructive criticism and helpful suggestions for improving the translation.

The final style and tone of the translation should match the style of {target_lang} colloquially spoken.

The part of the source text that needs translation is as follows:
{text}

The corresponding translation is:
{round_1}

When writing suggestions, pay attention to whether there are ways to improve the translation's:
1. accuracy (by correcting errors of addition, mistranslation, omission, or untranslated text, and ensuring the content is consistent),
2. fluency (by applying {target_lang} grammar, spelling, and punctuation rules, and ensuring there are no unnecessary repetitions),
3. style (by ensuring the translation reflects the style of the source text and considers any cultural context),
4. terminology (by ensuring terminology use is consistent, reflects the source text domain, and uses equivalent idioms in {target_lang}).

Write a list of specific, helpful, and constructive suggestions for improving the translation. Each suggestion should address one specific part of the translation. Output only the suggestions and nothing else.
"""

IMPROVE_TRANSLATION_PROMPT = """You are tasked with improving a translation based on expert suggestions. Here are the inputs you will be working with:
<context>
{context}
</context>

<source_text>
{source_text}
</source_text>

<initial_translation>
{initial_translation}
</initial_translation>

<expert_suggestions>
{expert_suggestions}
</expert_suggestions>

The target language for this translation is {target_lang}.

First, carefully read and analyze the expert suggestions. Consider how each suggestion can be applied to improve the translation in terms of accuracy, fluency, style, and terminology.

Next, rewrite the translation, incorporating the expert suggestions and adhering to the following guidelines:

1. Ensure accuracy by correcting any errors of addition, mistranslation, omission, or untranslated text.
2. Improve fluency by applying proper {target_lang} grammar, spelling, and punctuation rules. Eliminate any unnecessary repetitions.
3. Maintain the style of the source text in your improved translation.
4. Use consistent and contextually appropriate terminology throughout the translation.
5. Preserve all markdown, image links, LaTeX code, paragraph structure, and titles from the initial translation.
6. Translate even single lines or incomplete paragraphs.
7. Do not include pinyin annotations.
8. Retain any emojis and links present in the source text. Do not alter the format of links.
9. Do not include any source text in your output.
10. Keep in mind that the source text is from a tweet, so maintain an appropriate tone and style.

Your output should consist solely of the improved translation, without any additional commentary or explanations. Present your translation in the following format:

<improved_translation>
[Your improved translation goes here]
</improved_translation>

Ensure that your improved translation addresses all the expert suggestions and adheres to the guidelines provided above.
"""
