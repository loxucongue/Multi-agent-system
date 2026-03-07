"""Final response generation node."""

from __future__ import annotations

import inspect
from typing import Any

from app.graph.state import GraphState, STAGE_COLLECTING, STAGE_COMPARING, STAGE_RECOMMENDED
from app.graph.utils import normalize_int_list as _normalize_int_list_shared
from app.graph.utils import resolve_llm_client as _resolve_llm_client_shared
from app.graph.utils import to_int_or_none as _to_int_or_none_shared
from app.prompts.response_generation import build_response_prompt
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
    reuse_existing_text = _should_reuse_existing_text(intent=intent, tool_results=tool_results)
    response_tokens: list[str] = []
    response_streamed = False
    if existing_text and reuse_existing_text:
        response_text = existing_text
        llm_call_record = None
    else:
        response_text, response_tokens, response_streamed, llm_call_record = await _generate_text(
            intent,
            tool_results,
            user_message,
            state,
        )

    destination_mismatch = (
        intent == "route_recommend"
        and _is_route_recommend_destination_mismatch(tool_results=tool_results, state=state)
    )

    ui_actions = _build_ui_actions(intent, tool_results, state)
    cards = [] if destination_mismatch else _build_cards(intent, tool_results)
    state_patches = _build_state_patches(intent, tool_results, state)
    if destination_mismatch:
        ui_actions = []
        state_patches["active_route_id"] = None
        state_patches["candidate_route_ids"] = []
        state_patches["stage"] = STAGE_COLLECTING

    payload: dict[str, Any] = {
        "response_text": response_text,
        "ui_actions": ui_actions,
        "cards": cards,
        "state_patches": state_patches,
    }
    if response_streamed:
        payload["response_streamed"] = True
    elif response_tokens:
        payload["response_tokens"] = response_tokens
    if llm_call_record:
        payload["llm_calls"] = [llm_call_record]
    return payload


def _should_reuse_existing_text(intent: str, tool_results: dict[str, Any]) -> bool:
    """Whether response node should keep upstream response_text as final output."""

    if intent == "route_recommend":
        if (
            "route_details" in tool_results
            or "candidates" in tool_results
            or "candidates_without_id" in tool_results
            or "candidates_filtered_out" in tool_results
        ):
            return False
    return True


async def _generate_text(
    intent: str,
    tool_results: dict[str, Any],
    user_message: str,
    state: GraphState,
) -> tuple[str, list[str], bool, dict[str, Any] | None]:
    """Generate final text from structured data using streaming LLM output."""

    if str(state.get("error") or "").strip():
        return "抱歉，处理请求时遇到问题，请稍后重试。", [], False, None

    if tool_results.get("error"):
        return _fallback_text_from_tool_results(intent, tool_results), [], False, None

    if intent == "route_recommend":
        route_details = tool_results.get("route_details")
        candidates = tool_results.get("candidates")
        candidates_without_id = tool_results.get("candidates_without_id")
        candidates_filtered_out = tool_results.get("candidates_filtered_out")

        if _is_route_recommend_destination_mismatch(tool_results=tool_results, state=state):
            destinations = _extract_profile_destinations(state)
            destination_text = "、".join(destinations) if destinations else "您当前提到的目的地"
            _LOGGER.warning(
                "route_recommend destination mismatch, destination=%s tool_keys=%s",
                destinations,
                list(tool_results.keys()),
            )
            return (
                f"抱歉，当前匹配到的线路与「{destination_text}」不完全一致，"
                "我正在重新为您筛选。您也可以补充出发时间或预算，让匹配更精准。"
            ), [], False, None

        has_results = (
            isinstance(route_details, list) and bool(route_details)
        ) or (
            isinstance(candidates, list) and bool(candidates)
        )

        if not has_results:
            if isinstance(candidates_without_id, list) and candidates_without_id:
                return "我找到了相关线路，但数据格式异常，正在修复。请稍后重试或换个关键词。", [], False, None

            if isinstance(candidates_filtered_out, list) and candidates_filtered_out:
                return "暂时没有筛选到符合您当前条件的线路。您可以补充预算、出发时间或偏好，我马上重新匹配。", [], False, None

            profile = state.get("user_profile")
            destinations: list[str] = []
            if hasattr(profile, "destinations") and isinstance(profile.destinations, list):
                destinations = [str(item).strip() for item in profile.destinations if str(item).strip()]
            elif isinstance(profile, dict):
                raw_destinations = profile.get("destinations")
                if isinstance(raw_destinations, list):
                    destinations = [str(item).strip() for item in raw_destinations if str(item).strip()]

            if destinations:
                return f"抱歉，暂未找到与「{'、'.join(destinations)}」相关的线路。您可以调整条件后我再为您匹配。", [], False, None
            return "抱歉，暂未匹配到合适的线路。请告诉我目的地和天数，我继续为您查找。", [], False, None

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
                    "请在回答末尾追加一句自然引导，回应用户提到的次要意图："
                    f"{secondary_intent}。引导语要自然，不要模板化。"
                ),
            }
        )

    messages.append(
        {
            "role": "system",
            "content": "必须仅依据 tool_results 中已有字段作答；没有的数据直接说明未提供。",
        }
    )

    llm_client, should_close = _resolve_llm_client()
    chunks: list[str] = []
    streamed_via_callback = False
    token_emitter = state.get("token_emitter")
    try:
        async for delta in llm_client.chat_stream(messages=messages, temperature=0.5):
            if delta:
                text = str(delta)
                chunks.append(text)
                if callable(token_emitter):
                    maybe_result = token_emitter(text)
                    if inspect.isawaitable(maybe_result):
                        await maybe_result
                    streamed_via_callback = True
    except Exception as exc:
        _LOGGER.warning("response generation stream failed, fallback text used: %s", exc)
        return _fallback_text_from_tool_results(intent, tool_results), [], False, {
            "node": "response",
            "status": "fallback",
            "error": str(exc),
            "input": _truncate_messages(messages),
        }
    finally:
        if should_close:
            await llm_client.aclose()

    merged = "".join(chunks).strip()
    if merged:
        llm_call_record = {
            "node": "response",
            "status": "success",
            "input": _truncate_messages(messages),
            "output": _truncate_text(merged),
        }
        if streamed_via_callback:
            return merged, [], True, llm_call_record
        return merged, chunks, False, llm_call_record
    return _fallback_text_from_tool_results(intent, tool_results), [], False, {
        "node": "response",
        "status": "fallback",
        "input": _truncate_messages(messages),
    }


def _build_ui_actions(intent: str, tool_results: dict[str, Any], state: GraphState) -> list[dict[str, Any]]:
    """Build UI directives for frontend based on intent and data."""

    actions: list[dict[str, Any]] = []

    if intent == "route_recommend":
        active_route_id = _to_int_or_none(state.get("active_route_id"))
        if active_route_id is not None:
            actions.append({"action": "show_active_route", "payload": {"route_id": active_route_id}})

        candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))
        if candidate_route_ids:
            actions.append({"action": "show_candidates", "payload": {"route_ids": candidate_route_ids}})

    elif intent == "compare":
        compare_data = tool_results.get("compare_data")
        if isinstance(compare_data, dict):
            actions.append({"action": "show_compare", "payload": compare_data})

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
    return _resolve_llm_client_shared()


def _state_for_prompt(state: GraphState) -> dict[str, Any]:
    payload = dict(state)
    user_profile = payload.get("user_profile")
    if hasattr(user_profile, "model_dump"):
        payload["user_profile"] = user_profile.model_dump()
    return payload


def _to_route_card(detail: dict[str, Any]) -> dict[str, Any]:
    route_id = _to_int_or_none(detail.get("id") or detail.get("route_id"))
    return {
        "id": route_id,
        "route_id": route_id,
        "name": str(detail.get("name") or ""),
        "summary": str(detail.get("summary") or ""),
        "tags": detail.get("tags") if isinstance(detail.get("tags"), list) else [],
        "doc_url": detail.get("doc_url"),
        "highlights": str(detail.get("highlights") or ""),
    }


def _extract_profile_destinations(state: GraphState) -> list[str]:
    profile = state.get("user_profile")
    destinations: list[str] = []

    if hasattr(profile, "destinations") and isinstance(profile.destinations, list):
        destinations = [str(item).strip() for item in profile.destinations if str(item).strip()]
    elif isinstance(profile, dict):
        raw_destinations = profile.get("destinations")
        if isinstance(raw_destinations, list):
            destinations = [str(item).strip() for item in raw_destinations if str(item).strip()]

    deduped: list[str] = []
    seen: set[str] = set()
    for destination in destinations:
        if destination in seen:
            continue
        seen.add(destination)
        deduped.append(destination)
    return deduped


def _is_route_recommend_destination_mismatch(tool_results: dict[str, Any], state: GraphState) -> bool:
    route_details = tool_results.get("route_details")
    if not isinstance(route_details, list) or not route_details:
        return False

    destinations = _extract_profile_destinations(state)
    if not destinations:
        return False

    for detail in route_details:
        if not isinstance(detail, dict):
            continue
        if _route_detail_matches_destinations(detail, destinations):
            return False
    return True


def _route_detail_matches_destinations(detail: dict[str, Any], destinations: list[str]) -> bool:
    text_parts = [
        str(detail.get("name") or ""),
        str(detail.get("summary") or ""),
        str(detail.get("base_info") or ""),
        " ".join(str(tag) for tag in detail.get("tags", []) if str(tag).strip())
        if isinstance(detail.get("tags"), list)
        else "",
    ]
    combined = " ".join(text_parts)
    return any(destination in combined for destination in destinations)


def _fallback_text_from_tool_results(intent: str, tool_results: dict[str, Any]) -> str:
    if intent == "route_recommend":
        cards = tool_results.get("route_details")
        if isinstance(cards, list) and cards:
            names = [str(item.get("name")) for item in cards if isinstance(item, dict) and item.get("name")]
            if names:
                return "我为您整理了这些线路：" + "、".join(names)
        return "我已整理好推荐线路，您可以先看右侧候选方案。"

    if intent == "price_schedule":
        price_updated_at = tool_results.get("price_updated_at") or "未知时间"
        schedule_updated_at = tool_results.get("schedule_updated_at") or "未知时间"
        if isinstance(tool_results.get("price"), dict) or isinstance(tool_results.get("schedule"), dict):
            return f"价格更新时间：{price_updated_at}；团期更新时间：{schedule_updated_at}。"
        return "暂时未查到该线路的价格和团期信息。"

    if intent == "compare":
        compare_data = tool_results.get("compare_data")
        if isinstance(compare_data, dict):
            routes = compare_data.get("routes")
            if isinstance(routes, list) and routes:
                names = [str(item.get("name")) for item in routes if isinstance(item, dict) and item.get("name")]
                if names:
                    return "已为您整理对比：" + "、".join(names)
        return "暂时无法生成对比结果。"

    if intent == "visa":
        answer = tool_results.get("answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
        return "签证信息已整理完成。"

    if intent == "external_info":
        output = tool_results.get("output")
        if isinstance(output, str) and output.strip():
            return output.strip()
        return "外部信息查询完成。"

    return "我已根据当前信息为您整理好结果。"


def _normalize_int_list(values: Any) -> list[int]:
    return _normalize_int_list_shared(values)


def _to_int_or_none(value: Any) -> int | None:
    return _to_int_or_none_shared(value)


def _truncate_messages(messages: list[dict[str, Any]], max_chars: int = 800) -> list[dict[str, str]]:
    truncated: list[dict[str, str]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if len(content) > max_chars:
            content = f"{content[:max_chars]}..."
        truncated.append({"role": role, "content": content})
    return truncated


def _truncate_text(text: str, max_chars: int = 1600) -> str:
    value = str(text or "")
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}..."
