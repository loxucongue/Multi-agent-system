"""Prompt builder for route KB query generation."""

from __future__ import annotations

from typing import Any


def build_kb_query_gen_prompt(
    user_profile: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]],
    attempt: int,
    previous_query: str | None,
    previous_result_summary: str | None,
) -> list[dict[str, str]]:
    """Build messages for generating a precise route KB query."""

    system_prompt = (
        "你是旅游线路检索关键词专家。\n"
        "任务：根据用户画像和对话历史，生成一条精准的中文知识库检索 query。\n"
        "要求：\n"
        "1. query 尽量短，但保留目的地、天数、预算、风格等关键信息。\n"
        "2. 不要输出解释，不要输出 JSON，只输出一行纯文本 query。\n"
        "3. 如果这是重试轮次，需要根据上一轮 query 和结果摘要换角度重写，不要简单重复。\n"
    )

    history_text = "\n".join(
        f"用户：{item.get('user', '')}\n助手：{item.get('assistant', '')}" for item in history[-3:]
    )
    user_parts = [
        f"用户当前消息：{user_message}",
        f"用户画像：{user_profile}",
        f"当前轮次：{attempt}",
    ]
    if history_text:
        user_parts.append(f"最近对话：\n{history_text}")
    if attempt > 1:
        user_parts.append(f"上一轮 query：{previous_query or '-'}")
        user_parts.append(f"上一轮结果摘要：{previous_result_summary or '-'}")
        user_parts.append("请结合上一轮结果，从不同角度重写 query。")

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
