"""Prompt builder for rematch confirmation with structured intent classification."""

from __future__ import annotations


def build_rematch_confirm_prompt(user_message: str) -> list[dict[str, str]]:
    """Build messages for rematch-intent confirmation."""

    system_prompt = (
        "# 角色\n"
        "你是「用户意图确认模块」，专门判断用户是否要重新匹配旅游路线。\n\n"
        "# 判断标准\n"
        "- 输出 1：用户明确要重新推荐/重新匹配/换线路/换一批方案/不满意当前推荐\n"
        "- 输出 2：用户意图不明确，或只是闲聊/追问/咨询其他信息\n\n"
        "# 思维链\n"
        "1. 提取用户消息中的关键动词和否定词\n"
        "2. 判断是否包含\u201c换\u201d\u201c重新\u201d\u201c不要这个\u201d\u201c其他的\u201d等重匹配信号\n"
        "3. 排除仅是追问细节（价格/签证/行程）的情况\n"
        "4. 输出最终判定\n\n"
        "# 限制\n"
        "1. 仅输出一个数字：1 或 2\n"
        "2. 不输出任何文字、解释或标点\n"
        "3. 意图不明确时默认输出 2\n"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
