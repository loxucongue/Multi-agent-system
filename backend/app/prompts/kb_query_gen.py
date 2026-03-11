"""Prompt builder for route KB query generation with CoT retry guidance."""

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

    destinations = user_profile.get("destinations") or []
    days_range = user_profile.get("days_range") or ""
    style_prefs = user_profile.get("style_prefs") or []
    budget_range = user_profile.get("budget_range") or ""

    profile_summary = (
        f"目的地: {'、'.join(str(d) for d in destinations) if destinations else '未知'} | "
        f"天数: {days_range or '未指定'} | "
        f"风格: {'、'.join(str(s) for s in style_prefs) if style_prefs else '未指定'} | "
        f"预算: {budget_range or '未指定'}"
    )

    history_text = "\n".join(
        f"用户：{item.get('user', '')}\n助手：{item.get('assistant', '')}" for item in history[-3:]
    )
    user_parts = [
        f"## 用户画像摘要\n{profile_summary}",
        f"## 用户当前消息\n{user_message}",
        f"## 当前尝试轮次\n第 {attempt} 轮",
    ]
    if history_text:
        user_parts.append(f"## 最近对话\n{history_text}")
    if attempt > 1:
        user_parts.append(f"## 上一轮 query\n{previous_query or '-'}")
        user_parts.append(f"## 上一轮结果摘要\n{previous_result_summary or '-'}")
        user_parts.append(
            "## 重试策略提示\n"
            "请从以下角度之一调整：放宽天数约束、使用目的地别名、补充行程风格关键词。"
        )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]

