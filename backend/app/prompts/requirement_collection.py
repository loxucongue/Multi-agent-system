"""Prompt builder for requirement collection with progressive slot guidance."""

from __future__ import annotations

import json
from typing import Any

from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt

_SLOT_DESCRIPTIONS: dict[str, str] = {
    "destinations": "目的地（必填）",
    "days_range": "天数范围（如5-7天）",
    "budget_range": "预算范围（如5000-8000）",
    "depart_date_range": "出发日期区间",
    "people": "出行人群（如情侣/亲子/朋友）",
    "style_prefs": "旅行风格偏好（如休闲/深度/冒险）",
    "origin_city": "出发城市",
}


async def build_collect_prompt(
    user_message: str,
    user_profile: dict[str, Any],
    missing_slots: list[str],
) -> list[dict[str, str]]:
    """Build messages that guide the model to ask focused follow-up questions."""

    default_system_prompt = DEFAULT_PROMPTS["requirement_collection"]
    system_prompt = (await get_active_prompt("requirement_collection")) or default_system_prompt

    slot_detail = "\n".join(
        f"  - {slot}: {_SLOT_DESCRIPTIONS.get(slot, slot)}"
        for slot in missing_slots
    )

    user_prompt = (
        f"## 用户最新消息\n{user_message}\n\n"
        f"## 当前用户画像\n{json.dumps(user_profile, ensure_ascii=False, default=str)}\n\n"
        f"## 缺失槽位及说明\n{slot_detail}\n\n"
        "请按要求只输出 JSON，不要输出其他文字。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
