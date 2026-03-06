"""Prompt builder for rematch confirmation."""

from __future__ import annotations


def build_rematch_confirm_prompt(user_message: str) -> list[dict[str, str]]:
    """Build messages for rematch-intent confirmation."""

    system_prompt = (
        "你是用户意图确认模块。判断用户是否明确表达了“需要重新匹配旅游路线”的意图。\n\n"
        "判断标准：\n"
        "- 输出 1：用户明确要重新推荐、重新匹配、换线路、换一批方案。\n"
        "- 输出 2：用户意图不明确，或只是在闲聊、追问、咨询其他信息。\n\n"
        "规则：\n"
        "1. 仅输出一个数字：1 或 2。\n"
        "2. 不输出任何文字、解释或标点。\n"
        "3. 意图不明确时默认输出 2。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
