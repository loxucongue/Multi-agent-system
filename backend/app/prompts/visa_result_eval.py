"""Prompt builder for visa KB result relevance evaluation."""

from __future__ import annotations


def build_visa_result_eval_prompt(
    user_message: str,
    country: str,
    query: str,
    answer: str,
    sources: list[str],
) -> list[dict[str, str]]:
    """Build messages for evaluating visa KB retrieval relevance."""

    system_prompt = (
        "你是签证检索结果评估专家。\n"
        "判断当前检索结果是否真正回答了用户的签证问题。\n"
        "输出 JSON：{\"relevant\": true/false, \"reasoning\": \"...\"}\n"
        "若结果与目标国家、签证主题明显不匹配，则 relevant=false。\n"
        "不要输出任何 JSON 之外的内容。"
    )

    user_prompt = (
        f"用户消息：{user_message}\n"
        f"目标国家/地区：{country}\n"
        f"检索 query：{query}\n"
        f"回答内容：{answer}\n"
        f"来源：{sources}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
