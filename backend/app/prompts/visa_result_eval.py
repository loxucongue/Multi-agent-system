"""Prompt builder for visa KB result relevance evaluation with structured scoring."""

from __future__ import annotations

import json

from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt


async def build_visa_result_eval_prompt(
    user_message: str,
    country: str,
    query: str,
    answer: str,
    sources: list[str],
) -> list[dict[str, str]]:
    """Build messages for evaluating visa KB retrieval relevance."""

    system_prompt = (await get_active_prompt("visa_result_eval")) or DEFAULT_PROMPTS["visa_result_eval"]

    # Truncate long answer to avoid token waste
    answer_display = answer[:800] + "..." if len(answer) > 800 else answer
    sources_display = json.dumps(sources[:5], ensure_ascii=False) if sources else "[]"

    user_prompt = (
        f"## 用户消息\n{user_message}\n\n"
        f"## 目标国家/地区\n{country}\n\n"
        f"## 检索 query\n{query}\n\n"
        f"## 回答内容（截断）\n{answer_display}\n\n"
        f"## 来源\n{sources_display}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

