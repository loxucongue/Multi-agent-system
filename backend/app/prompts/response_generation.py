"""Prompt builder for final response generation."""

from __future__ import annotations

import json
from typing import Any

from app.services.prompt_service import get_active_prompt

_SCENE_INSTRUCTIONS: dict[str, str] = {
    "route_recommend": "请用热情专业的语气介绍主推线路，列出名称/天数/亮点摘要，末尾引导用户查看价格团期或追问细节。",
    "route_followup": "请根据工具返回的具体字段（行程/费用/注意事项等）详细回答，不得编造工具未返回的信息。",
    "visa": "请结构化列出签证材料、办理周期、注意事项。末尾必须加风险提示：以上信息仅供参考，最终以领馆/使馆官方要求为准。",
    "price_schedule": "回答必须包含价格区间和最近团期，必须附带更新时间（如 价格更新于2026-03-04），不得省略更新时间。",
    "external_info": "回答必须注明数据来源和获取时间（如 数据来自xxx，获取于2026-03-04），不确定的信息用 建议出行前再次确认。",
    "compare": "请用横向对比方式逐维度说明各线路差异，不要简单罗列，末尾给出选择建议。",
    "chitchat": "保持友好简短，回答末尾自然引导回旅游咨询。",
    "rematch": "请先确认用户新的偏好变化，再给出下一步建议；若数据不足，明确提示将按新条件重新匹配。",
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
            "若 state.secondary_intent 不为空，请在回答末尾追加一句自然引导语，"
            f"提示用户可继续咨询该次要意图（{secondary_intent}）。"
        )

    default_system_prompt = (
        "你是旅游顾问回复生成器。根据 intent、tool_results、用户消息、state 生成中文回复。"
        "严禁编造 tool_results 未提供的数据；若信息不足，明确说明缺失项。"
        "价格/团期必须带更新时间；签证回答必须包含风险提示。"
        f"场景指令：{scene_instruction} {secondary_hint}"
    )
    system_prompt = (await get_active_prompt("response_generation")) or default_system_prompt

    state_payload = _state_for_response(state)
    user_prompt = (
        f"intent: {intent}\n"
        f"用户消息:\n{user_message}\n\n"
        f"工具结果:\n{json.dumps(tool_results or {}, ensure_ascii=False)}\n\n"
        f"会话状态:\n{json.dumps(state_payload, ensure_ascii=False)}\n\n"
        "请只输出最终回复文本。"
    )

    return [
        {"role": "system", "content": system_prompt},
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
    }
    return {k: v for k, v in state.items() if k in keep_keys}

