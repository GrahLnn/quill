from typing import Dict

import regex as re

from ...service.helper import get


def at_who(text):
    """
    获取文本中的@提及信息及其位置
    :param text: 文本内容
    :return: 列表，每项包含 (用户名, [开始位置, 结束位置])
    """
    mentions = []
    for match in re.finditer(r"@(\w+)", text):
        username = match.group(0)  # 完整匹配（包含@）
        start = match.start()
        end = match.end()
        mentions.append({"name": username, "indices": [start, end]})
    return mentions


def rm_mention(tw: Dict):
    mentions = [d.get("name") for d in at_who(get(tw, "content.text"))]
    mentions.append(f"@{get(tw, 'author.screen_name')}")
    if "replies" in tw:
        for reply in tw["replies"]:
            for convitem in reply.get("conversation", []):
                mentions.append(f"@{get(convitem, 'author.screen_name')}")
                reply_mentions = at_who(get(convitem, "content.text"))
                mention_end = None
                for i, men in enumerate(reply_mentions):
                    if reply_mentions[0]["indices"][0] != 0:
                        break
                    if i == 0 and men.get("name") in mentions:
                        # if i == 0:
                        mention_end = men["indices"][1]
                    elif (
                        mention_end and men["indices"][0] - mention_end == 1
                    ):  # repost user in mention but i can't identify
                        mention_end = men["indices"][1]
                    else:
                        break
                if mention_end:
                    convitem["content"]["text"] = convitem["content"]["text"][
                        mention_end + 1 :
                    ]
