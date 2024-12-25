BASIC_TRANSLATION_PROMPT = """Your task is to provide a professional translation to {target_lang} of PART of a text.

To reiterate, you should translate only this part and ALL of the text shown here:
{text}

Guidelines for the translation:
1. Translate ALL content provided.
2. Maintain paragraph structure and line breaks.
3. Preserve all markdown, image links, LaTeX code, and titles.
4. Do not omit or remove any lines from the provided content.
5. Even if it is a single title or a title containing incomplete paragraphs, it still needs to be translated.
6. Do not include source text.
7. Source text are from tweet.

Output only the new translation and nothing else.
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

IMPROVE_TRANSLATION_PROMPT = """Your task is to carefully read, then improve, a translation to {target_lang}, taking into account a set of expert suggestions and constructive criticisms. Below, the source text, initial translation, and expert suggestions are provided.

The part of the source text that needs translation is as follows:
{text}

The corresponding translation is:
{round_1}

The expert suggestions for improving the translation are:
{round_2}

Taking into account the expert suggestions, rewrite the translation to improve it, paying attention to:

1. Accuracy (by correcting errors of addition, mistranslation, omission, or untranslated text).
2. Fluency (by applying {target_lang} grammar, spelling, and punctuation rules, and ensuring there are no unnecessary repetitions).
3. Style (by ensuring the translation reflects the style of the source text).
4. Terminology (ensuring consistency and appropriateness for context).
5. Retaining all markdown, image links, LaTeX code, paragraph structure, and titles.
6. Ensuring that even single lines or incomplete paragraphs are translated.
7. Avoiding pinyin annotations.
8. Preserving any emojis and links(don't change the link format) present in the source text.
9. Do not include source text.
10. Source text are from tweet.

Output only the new translation and nothing else.
"""
