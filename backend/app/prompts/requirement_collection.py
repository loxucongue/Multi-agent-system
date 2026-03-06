"""Prompt builder for requirement collection turns."""

from __future__ import annotations

import json
from typing import Any

from app.services.prompt_service import get_active_prompt


async def build_collect_prompt(
    user_message: str,
    user_profile: dict[str, Any],
    missing_slots: list[str],
) -> list[dict[str, str]]:
    """Build messages that guide the model to ask focused follow-up questions."""

    default_system_prompt = (
        "你是旅游需求收集助手。"
        "必要槽位是 destination（在数据结构中对应 destinations 列表至少 1 项）。"
        "可选槽位有 days_range、budget_range、depart_date_range、people、style_prefs、origin_city。"
        "你需要输出 1~3 个追问问题，优先补齐必要槽位，避免重复询问已知信息。"
        "只允许输出 JSON："
        "{\"questions\":[\"...\"],\"suggested_state_patch\":{\"user_profile\":{}},\"slots_ready\":bool,\"reasoning\":\"...\"}。"
        "若槽位已足够，可 questions 返回空数组且 slots_ready=true。"
    )
    system_prompt = (await get_active_prompt("requirement_collection")) or default_system_prompt

    user_prompt = (
        f"用户最新消息:\n{user_message}\n\n"
        f"当前用户画像:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
        f"缺失槽位:\n{json.dumps(missing_slots, ensure_ascii=False)}\n\n"
        "请按要求只输出 JSON。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

