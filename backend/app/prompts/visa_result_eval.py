"""Prompt builder for visa KB result relevance evaluation."""

from __future__ import annotations

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
    user_prompt = (
        f"用户消息：{user_message}\n"
        f"目标国家/地区：{country}\n"
        f"检索 query：{query}\n"
        f"回答内容：{answer}\n"
        f"来源：{sources}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

