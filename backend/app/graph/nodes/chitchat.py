"""Chitchat node."""

from __future__ import annotations

from app.graph.state import GraphState
from app.graph.utils import resolve_llm_client as _resolve_llm_client_shared
from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)
_GUIDE_SUFFIX = "您想去哪里旅游呢？"


async def chitchat_node(state: GraphState) -> dict[str, str]:
    """Generate polite small-talk response and guide user back to travel intent."""

    user_message = str(state.get("current_user_message") or "").strip()
    llm_client, should_close = _resolve_llm_client()
    system_prompt = (await get_active_prompt("chitchat")) or DEFAULT_PROMPTS["chitchat"]

    response_text = ""
    try:
        response_text = await llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=400,
        )
    except Exception as exc:
        _LOGGER.warning("chitchat llm call failed, fallback used: %s", exc)
        response_text = f"抱歉，先照顾好自己最重要。{_GUIDE_SUFFIX}"
    finally:
        if should_close:
            await llm_client.aclose()

    return {"response_text": _normalize_response(response_text)}


def _resolve_llm_client() -> tuple[object, bool]:
    return _resolve_llm_client_shared()


def _normalize_response(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return f"我在这儿陪着您。{_GUIDE_SUFFIX}"

    if _GUIDE_SUFFIX not in normalized:
        if not normalized.endswith(("。", "！", "？", ".", "!", "?")):
            normalized += "。"
        normalized += _GUIDE_SUFFIX
    return normalized
