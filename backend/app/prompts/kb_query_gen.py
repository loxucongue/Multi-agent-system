"""Prompt builder for route KB query generation."""

from __future__ import annotations

from typing import Any

from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt


async def build_kb_query_gen_prompt(
    user_profile: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]],
    attempt: int,
    previous_query: str | None,
    previous_result_summary: str | None,
) -> list[dict[str, str]]:
    """Build messages for generating a precise route KB query."""

    system_prompt = (await get_active_prompt("kb_query_gen")) or DEFAULT_PROMPTS["kb_query_gen"]

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

