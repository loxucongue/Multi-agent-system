"""Prompt builder for visa query rewriting with structured retry guidance."""

from __future__ import annotations


def build_visa_query_rewrite_prompt(
    user_message: str,
    history: list[dict[str, str]],
    attempt: int = 1,
    previous_query: str | None = None,
    previous_result_summary: str | None = None,
) -> list[dict[str, str]]:
    """Build messages for concise visa KB query rewriting."""

    system_prompt = (
        "# 角色\n"
        "你是「签证检索关键词提取专家」，将用户签证问题转化为精准检索 query。\n\n"
        "# 任务\n"
        "输出格式：「[目的地国家] [签证类型/核心要求]」的极简关键词。\n"
        "示例：日本 旅游签证材料、泰国 落地签流程、新加坡 电子签证。\n\n"
        "# 规则\n"
        "1. 优先取用户明确提及的国家；若未明确，从上下文推断\n"
        "2. 若完全无法推断国家，输出「[目的地] 签证要求」\n"
        "3. 禁止添加用户未提及的信息\n"
        "4. 仅输出关键词字符串，不输出解释\n"
        "5. 重试轮次必须换角度（如增加签证细分类型、换同义词）\n"
    )

    user_prompt = f"用户问题：{user_message}"
    if history:
        recent = history[-2:]
        history_text = "\n".join(
            f"用户：{turn.get('user', '')}\n助手：{turn.get('assistant', '')}"
            for turn in recent
        )
        user_prompt = f"历史对话：\n{history_text}\n\n当前用户问题：{user_message}"

    if attempt > 1:
        user_prompt = (
            f"{user_prompt}\n\n"
            f"上一轮 query：{previous_query or '-'}\n"
            f"上一轮结果摘要：{previous_result_summary or '-'}\n"
            "请从不同角度重写 query（换同义词/细化签证类型/扩大国家范围）。"
        )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
