"""Prompt builder for requirement collection turns."""

from __future__ import annotations

import json
from typing import Any

from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt


async def build_collect_prompt(
    user_message: str,
    user_profile: dict[str, Any],
    missing_slots: list[str],
) -> list[dict[str, str]]:
    """Build messages that guide the model to ask focused follow-up questions."""

    default_system_prompt = DEFAULT_PROMPTS["requirement_collection"]
    system_prompt = (await get_active_prompt("requirement_collection")) or default_system_prompt

    user_prompt = (
        f"用户最新消息:\n{user_message}\n\n"
        f"当前用户画像:\n{json.dumps(user_profile, ensure_ascii=False, default=str)}\n\n"
        f"缺失槽位:\n{json.dumps(missing_slots, ensure_ascii=False, default=str)}\n\n"
        "请按要求只输出 JSON。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
