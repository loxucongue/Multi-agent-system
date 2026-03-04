"""Prompt builder for requirement collection turns."""

from __future__ import annotations

import json
from typing import Any


def build_collect_prompt(
    user_message: str,
    user_profile: dict[str, Any],
    missing_slots: list[str],
) -> list[dict[str, str]]:
    """Build messages that guide the model to ask focused follow-up questions."""

    system_prompt = (
        "你是旅游需求收集助手。目标是在不打扰用户的前提下补齐槽位并生成追问。"
        "必要槽位：destination；可选槽位：days/budget/depart_date/people/style_prefs。"
        "已知信息不要重复问，问题口语化、简短、可直接回答；优先补destination。"
        "请输出且仅输出JSON："
        "{\"questions\":[\"问题1\",\"问题2\"],\"suggested_state_patch\":{\"user_profile\":{}},"
        "\"slots_ready\":bool,\"reasoning\":\"...\"}。"
        "questions数量1~3；若已无缺失可返回空数组并给slots_ready=true。"
        "不得编造用户未提供的信息。"
    )

    user_prompt = (
        f"用户最新消息:\n{user_message}\n\n"
        f"当前用户画像:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
        f"缺失槽位:\n{json.dumps(missing_slots, ensure_ascii=False)}\n\n"
        "请按要求输出JSON。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
