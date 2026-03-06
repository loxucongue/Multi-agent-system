"""Prompt builder for visa query rewriting."""

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
        "你是签证问题检索关键词提取专家。\n"
        "任务：将用户的签证相关问题精简为“目的地国家 + 签证核心要求”的检索关键词。\n"
        "规则：\n"
        "1. 仅输出格式为“[目的地国家] [签证类型/核心要求]”的极简关键词，如“日本 旅游签证材料”“泰国 落地签流程”。\n"
        "2. 结合上下文确定目的地国家，优先取用户明确提及的国家。\n"
        "3. 若用户未明确国家，从上下文推断；若完全无法推断，输出“[目的地] 签证要求”。\n"
        "4. 禁止添加用户未提及的信息。\n"
        "5. 仅输出关键词字符串，不输出任何解释。\n"
        "6. 若是重试轮次，必须根据上一轮 query 和结果摘要换个检索角度，不要重复上一轮。\n"
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
            "请根据以上信息重写 query。"
        )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
