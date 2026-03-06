"""Prompt builder for route KB result relevance evaluation."""

from __future__ import annotations

from typing import Any

from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt


async def build_kb_result_eval_prompt(
    user_message: str,
    user_profile: dict[str, Any],
    query: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build messages for evaluating route KB retrieval relevance."""

    system_prompt = (await get_active_prompt("kb_result_eval")) or DEFAULT_PROMPTS["kb_result_eval"]
    user_prompt = (
        f"用户消息：{user_message}\n"
        f"用户画像：{user_profile}\n"
        f"检索 query：{query}\n"
        f"候选结果：{candidates}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

