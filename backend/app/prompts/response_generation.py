"""Prompt builder for final response generation with intent-specific constraints."""

from __future__ import annotations

import json
from typing import Any

from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt

_SCENE_INSTRUCTIONS: dict[str, str] = {
    "route_recommend": (
        "用热情专业的语气介绍主推线路。结构：开场白→逐条列出线路（名称/天数/亮点摘要）→"
        "末尾引导查看价格团期或追问细节。不要重复 tool_results 原始 JSON。"
    ),
    "route_followup": (
        "根据 tool_results 中的具体字段（行程/费用/注意事项等）详细回答。"
        "禁止编造 tool_results 未返回的信息。若某字段缺失，明确告知用户并建议联系顾问。"
    ),
    "visa": (
        "结构化列出签证材料、办理周期、注意事项。"
        "末尾必须加风险提示：「以上信息仅供参考，最终以领馆/使馆官方要求为准，建议出行前再次确认。」"
    ),
    "price_schedule": (
        "回答必须包含价格区间和最近团期，必须附带更新时间（如「价格更新于2026-03-04」），"
        "不得省略更新时间。若价格或团期数据缺失，明确说明并建议联系顾问。"
    ),
    "external_info": (
        "回答必须注明数据来源和获取时间（如「数据来自xxx，获取于2026-03-04」），"
        "不确定的信息用「建议出行前再次确认」。"
    ),
    "compare": (
        "用横向对比方式逐维度说明各线路差异（天数、价格、亮点、适合人群），"
        "不要简单罗列，末尾给出选择建议。"
    ),
    "chitchat": "保持友好简短（不超过50字），回答末尾自然引导回旅游咨询。",
    "rematch": (
        "先确认用户新的偏好变化，再给出下一步建议；"
        "若数据不足，明确提示将按新条件重新匹配。"
    ),
}


async def build_response_prompt(
    intent: str,
    tool_results: dict[str, Any] | None,
    user_message: str,
    state: dict[str, Any],
) -> list[dict[str, str]]:
    """Build response-generation messages with intent-specific instructions."""

    scene_instruction = _SCENE_INSTRUCTIONS.get(
        intent,
        "请基于工具结果给出准确、简洁、可执行的回复，不要编造信息。",
    )
    secondary_intent = state.get("secondary_intent")
    secondary_hint = ""
    if secondary_intent:
        secondary_hint = (
            f"\n\n追加要求：在回答末尾追加一句自然引导语，提示用户可继续咨询：{secondary_intent}"
        )

    default_system_prompt = DEFAULT_PROMPTS["response_generation"]
    system_prompt = (await get_active_prompt("response_generation")) or default_system_prompt
    full_system = f"{system_prompt}\n\n# 场景指令\n{scene_instruction}{secondary_hint}"

    state_payload = _state_for_response(state)

    tool_results_compact = _compact_tool_results(tool_results or {})

    user_prompt = (
        f"## intent\n{intent}\n\n"
        f"## 用户消息\n{user_message}\n\n"
        f"## 工具结果\n{json.dumps(tool_results_compact, ensure_ascii=False, default=str)}\n\n"
        f"## 会话状态\n{json.dumps(state_payload, ensure_ascii=False, default=str)}\n\n"
        "请只输出最终回复文本。"
    )

    return [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_prompt},
    ]


def _state_for_response(state: dict[str, Any]) -> dict[str, Any]:
    keep_keys = {
        "stage",
        "active_route_id",
        "candidate_route_ids",
        "lead_status",
        "last_intent",
        "secondary_intent",
        "user_profile",
        "conversation_summary",
    }
    return {k: v for k, v in state.items() if k in keep_keys}


def _compact_tool_results(tool_results: dict[str, Any]) -> dict[str, Any]:
    """Truncate large tool_results fields to stay within token budget."""
    compacted = dict(tool_results)
    for key in ("candidates", "route_details"):
        items = compacted.get(key)
        if isinstance(items, list) and len(items) > 5:
            compacted[key] = items[:5]
            compacted[f"{key}_truncated"] = True
    return compacted
