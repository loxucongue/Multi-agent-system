"""Prompt builder for route KB result relevance evaluation."""

from __future__ import annotations

from typing import Any


def build_kb_result_eval_prompt(
    user_message: str,
    user_profile: dict[str, Any],
    query: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build messages for evaluating route KB retrieval relevance."""

    system_prompt = (
        "你是旅游线路检索结果评估专家。\n"
        "判断检索结果是否与用户需求相关。\n"
        "输出 JSON：{\"relevant\": true/false, \"reasoning\": \"...\"}\n"
        "判断标准：至少有 1 条候选线路的目的地或主题与用户需求匹配，即为 relevant=true。\n"
        "不要输出任何 JSON 之外的内容。"
    )

    user_prompt = (
        f"用户消息：{user_message}\n"
        f"用户画像：{user_profile}\n"
        f"检索 query：{query}\n"
        f"候选结果：{candidates}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
