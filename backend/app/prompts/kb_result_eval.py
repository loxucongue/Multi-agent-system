"""Prompt builder for route KB result relevance evaluation."""

from __future__ import annotations

import json
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

    destinations = user_profile.get("destinations") or []
    dest_str = "、".join(str(d) for d in destinations) if destinations else "未明确"

    candidate_summaries: list[str] = []
    for idx, c in enumerate(candidates[:5], 1):
        name = ""
        if isinstance(c, dict):
            hot = c.get("hot_route")
            if isinstance(hot, dict):
                name = str(hot.get("name") or "")
            name = name or str(c.get("output") or "")[:100]
        candidate_summaries.append(f"  {idx}. {name}")

    user_prompt = (
        f"## 用户消息\n{user_message}\n\n"
        f"## 用户目的地\n{dest_str}\n\n"
        f"## 检索 query\n{query}\n\n"
        f"## 候选结果（前5条摘要）\n" + "\n".join(candidate_summaries) + "\n\n"
        "请判断候选结果是否与用户目的地相关，仅输出 JSON。"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

