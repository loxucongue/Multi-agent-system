"""Prompt builder for final response generation."""

from __future__ import annotations

import json
from typing import Any

_SCENE_INSTRUCTIONS: dict[str, str] = {
    "route_recommend": "请用热情专业的语气介绍主推线路，列出名称/天数/亮点摘要，末尾引导用户查看价格团期或追问细节。",
    "route_followup": "请根据工具返回的具体字段（行程/费用/注意事项等）详细回答，不得编造工具未返回的信息。",
    "visa": "请结构化列出签证材料、办理周期、注意事项。末尾必须加风险提示：以上信息仅供参考，最终以领馆/使馆官方要求为准。",
    "price_schedule": "回答必须包含价格区间和最近团期，必须附带更新时间（如价格更新于2026-03-04），不得省略更新时间。",
    "external_info": "回答必须注明数据来源和获取时间（如数据来自xxx，获取于2026-03-04），不确定的信息用建议出行前再次确认。",
    "compare": "请用横向对比的方式逐维度说明各线路的差异，不要简单罗列每条线路的信息。末尾给出选择建议。",
    "chitchat": "保持友好简短，回答末尾自然地引导回旅游咨询（如对了，您有出游计划吗？想去哪里玩呢？）。",
    "rematch": "请先确认用户新的偏好变化，再给出下一步建议；若工具结果不足，明确提示将根据新条件重新匹配。",
}


def build_response_prompt(
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
            "若state.secondary_intent不为空，请在回答末尾追加一句引导语，"
            "提示用户该次要意图也可继续咨询（语气自然，不要生硬模板化）。"
        )

    system_prompt = (
        "你是旅游顾问回复生成器。根据intent、tool_results、用户消息、state生成最终中文回复。"
        "严禁编造工具未返回的数据；价格团期必须带更新时间；签证需带风险提示。"
        "若信息不足，明确说明缺失并给下一步建议。只输出最终回复文本，不输出JSON或解释。\n"
        f"场景指令：{scene_instruction}\n"
        f"{secondary_hint}"
    )

    state_payload = _state_for_response(state)
    user_prompt = (
        f"intent: {intent}\n"
        f"用户消息:\n{user_message}\n\n"
        f"工具结果:\n{json.dumps(tool_results or {}, ensure_ascii=False)}\n\n"
        f"会话状态:\n{json.dumps(state_payload, ensure_ascii=False)}"
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
