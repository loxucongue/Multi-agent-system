"""Final response generation node."""

from __future__ import annotations

import json
from typing import Any

from app.graph.state import GraphState, STAGE_COMPARING, STAGE_RECOMMENDED
from app.prompts.response_generation import build_response_prompt
from app.services.container import services
from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)


async def response_generation_node(state: GraphState) -> dict[str, Any]:
    """Orchestrate final text/ui/cards/state-patch generation from existing tool results."""

    intent = str(state.get("last_intent") or "")
    user_message = str(state.get("current_user_message") or "")
    tool_results = state.get("tool_results")
    if not isinstance(tool_results, dict):
        tool_results = {}

    existing_text = str(state.get("response_text") or "").strip()
    reuse_existing_text = _should_reuse_existing_text(
        intent=intent,
        tool_results=tool_results,
    )
    response_text = (
        existing_text
        if existing_text and reuse_existing_text
        else await _generate_text(intent, tool_results, user_message, state)
    )

    ui_actions = _build_ui_actions(intent, tool_results, state)
    cards = _build_cards(intent, tool_results)
    state_patches = _build_state_patches(intent, tool_results, state)

    return {
        "response_text": response_text,
        "ui_actions": ui_actions,
        "cards": cards,
        "state_patches": state_patches,
    }


def _should_reuse_existing_text(intent: str, tool_results: dict[str, Any]) -> bool:
    """Whether response node should keep upstream response_text as final output."""

    if intent == "route_recommend":
        if "route_details" in tool_results or "candidates" in tool_results or "candidates_raw" in tool_results:
            return False
    return True


async def _generate_text(
    intent: str,
    tool_results: dict[str, Any],
    user_message: str,
    state: GraphState,
) -> str:
    """Generate final text from structured data using streaming LLM output."""

    if str(state.get("error") or "").strip():
        return "抱歉，获取信息时遇到了问题，请稍后再试。"

    # deterministic fallback when node already indicates error
    if tool_results.get("error"):
        return _fallback_text_from_tool_results(intent, tool_results)

    if intent == "route_recommend":
        route_details = tool_results.get("route_details")
        candidates = tool_results.get("candidates")
        has_results = (
            isinstance(route_details, list)
            and bool(route_details)
        ) or (
            isinstance(candidates, list)
            and bool(candidates)
        )
        if not has_results:
            profile = state.get("user_profile")
            destinations: list[str] = []
            if hasattr(profile, "destinations") and isinstance(profile.destinations, list):
                destinations = [str(item).strip() for item in profile.destinations if str(item).strip()]
            elif isinstance(profile, dict):
                raw_destinations = profile.get("destinations")
                if isinstance(raw_destinations, list):
                    destinations = [str(item).strip() for item in raw_destinations if str(item).strip()]

            if destinations:
                dest = "、".join(destinations)
                return f"抱歉，暂未找到与「{dest}」相关的线路。您可以换个目的地或调整条件，我重新为您匹配。"
            return "抱歉，暂未匹配到合适的线路。您可以告诉我想去的目的地和大致天数，我再为您查找。"

    serializable_state = _state_for_prompt(state)
    messages = await build_response_prompt(
        intent=intent,
        tool_results=tool_results,
        user_message=user_message,
        state=serializable_state,
    )

    secondary_intent = state.get("secondary_intent")
    if secondary_intent:
        messages.append(
            {
                "role": "system",
                "content": (
                    "请在回答末尾增加一句简短引导，回应用户提到的次要意图："
                    f"{secondary_intent}。引导语自然，不要模板化。"
                ),
            }
        )

    # hard constraint to avoid hallucination
    messages.append(
        {
            "role": "system",
            "content": "必须仅依据 tool_results 中已有字段作答；没有的数据直接说明未提供。",
        }
    )

    llm_client, should_close = _resolve_llm_client()
    chunks: list[str] = []
    try:
        async for delta in llm_client.chat_stream(messages=messages, temperature=0.5):
            if delta:
                chunks.append(delta)
    except Exception as exc:
        _LOGGER.warning(f"response generation stream failed, fallback text used: {exc}")
        return _fallback_text_from_tool_results(intent, tool_results)
    finally:
        if should_close:
            await llm_client.aclose()

    merged = "".join(chunks).strip()
    if merged:
        return merged
    return _fallback_text_from_tool_results(intent, tool_results)


def _build_ui_actions(intent: str, tool_results: dict[str, Any], state: GraphState) -> list[dict[str, Any]]:
    """Build UI directives for frontend based on intent and data."""

    actions: list[dict[str, Any]] = []

    if intent == "route_recommend":
        active_route_id = _to_int_or_none(state.get("active_route_id"))
        if active_route_id is not None:
            actions.append({"action": "show_active_route", "payload": {"route_id": active_route_id}})

        candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))
        if candidate_route_ids:
            actions.append(
                {
                    "action": "show_candidates",
                    "payload": {"route_ids": candidate_route_ids},
                }
            )

    elif intent == "compare":
        compare_data = tool_results.get("compare_data")
        if isinstance(compare_data, dict):
            actions.append({"action": "show_compare", "payload": compare_data})

    elif intent == "price_schedule":
        # no extra ui action required
        pass

    return actions


def _build_cards(intent: str, tool_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Build card payloads from tool_results (no additional data fetch)."""

    cards: list[dict[str, Any]] = []

    route_details = tool_results.get("route_details")
    if isinstance(route_details, list):
        for item in route_details:
            if isinstance(item, dict):
                cards.append(_to_route_card(item))
        return cards

    route_detail = tool_results.get("route_detail")
    if isinstance(route_detail, dict):
        cards.append(_to_route_card(route_detail))
        return cards

    if intent == "route_recommend":
        candidates = tool_results.get("candidates")
        if isinstance(candidates, list):
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                hot_route = item.get("hot_route")
                if isinstance(hot_route, dict):
                    cards.append(_to_route_card(hot_route))
        return cards

    return cards


def _build_state_patches(intent: str, tool_results: dict[str, Any], state: GraphState) -> dict[str, Any]:
    """Build persisted state patch from current node output context."""

    patches: dict[str, Any] = {}
    user_profile = state.get("user_profile")
    if hasattr(user_profile, "model_dump"):
        patches["user_profile"] = user_profile.model_dump()
    elif isinstance(user_profile, dict):
        patches["user_profile"] = user_profile

    if intent == "route_recommend":
        active_route_id = _to_int_or_none(state.get("active_route_id"))
        candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))
        if candidate_route_ids:
            patches["candidate_route_ids"] = candidate_route_ids
        if active_route_id is not None:
            patches["active_route_id"] = active_route_id
            patches["stage"] = STAGE_RECOMMENDED

    elif intent == "route_followup":
        selected_route_id = _to_int_or_none(tool_results.get("selected_route_id"))
        if selected_route_id is None:
            route_detail = tool_results.get("route_detail")
            if isinstance(route_detail, dict):
                selected_route_id = _to_int_or_none(route_detail.get("id"))
        if selected_route_id is not None:
            patches["active_route_id"] = selected_route_id

    elif intent == "price_schedule":
        route_id = _to_int_or_none(tool_results.get("route_id"))
        if route_id is not None:
            patches["active_route_id"] = route_id

    elif intent == "compare":
        patches["stage"] = STAGE_COMPARING

    if bool(state.get("request_human")) and str(state.get("lead_status") or "none") == "none":
        patches["lead_status"] = "triggered"

    return patches


def _resolve_llm_client() -> tuple[LLMClient, bool]:
    try:
        return services.llm_client, False
    except Exception:
        return LLMClient(), True


def _state_for_prompt(state: GraphState) -> dict[str, Any]:
    payload = dict(state)
    user_profile = payload.get("user_profile")
    if hasattr(user_profile, "model_dump"):
        payload["user_profile"] = user_profile.model_dump()
    return payload


def _to_route_card(detail: dict[str, Any]) -> dict[str, Any]:
    route_id = _to_int_or_none(detail.get("id") or detail.get("route_id"))
    return {
        "route_id": route_id,
        "name": str(detail.get("name") or ""),
        "summary": str(detail.get("summary") or ""),
        "tags": detail.get("tags") if isinstance(detail.get("tags"), list) else [],
        "doc_url": detail.get("doc_url"),
        "highlights": str(detail.get("highlights") or ""),
    }


def _fallback_text_from_tool_results(intent: str, tool_results: dict[str, Any]) -> str:
    if intent == "route_recommend":
        cards = tool_results.get("route_details")
        if isinstance(cards, list) and cards:
            names = [str(item.get("name")) for item in cards if isinstance(item, dict) and item.get("name")]
            if names:
                return "我为您整理了这些线路：" + "、".join(names)
        return "我已整理好推荐线路，您可以先看看候选方案。"

    if intent == "price_schedule":
        price = tool_results.get("price")
        schedule = tool_results.get("schedule")
        if isinstance(price, dict) or isinstance(schedule, dict):
            return (
                f"这条线路价格更新于 {tool_results.get('price_updated_at') or '未知时间'}，"
                f"团期更新于 {tool_results.get('schedule_updated_at') or '未知时间'}。"
            )
        return "暂时未查到该线路的价格和团期信息。"

    if intent == "compare":
        compare_data = tool_results.get("compare_data")
        if isinstance(compare_data, dict):
            routes = compare_data.get("routes")
            if isinstance(routes, list) and routes:
                names = [str(item.get("name")) for item in routes if isinstance(item, dict)]
                return "已为您整理对比：" + "、".join([n for n in names if n])
        return "暂时无法生成对比结果。"

    if intent == "visa":
        answer = tool_results.get("answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
        return "签证信息已为您整理完成。"

    if intent == "external_info":
        output = tool_results.get("output")
        if isinstance(output, str) and output.strip():
            return output.strip()
        return "外部信息已查询完成。"

    return "我已根据当前信息为您整理好结果。"


def _normalize_int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    normalized: list[int] = []
    for value in values:
        parsed = _to_int_or_none(value)
        if parsed is not None:
            normalized.append(parsed)
    return normalized


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
