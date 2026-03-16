"""Final response generation node with structured template framework."""

from __future__ import annotations

import inspect
from typing import Any

from app.graph.state import GraphState, STAGE_COLLECTING, STAGE_COMPARING, STAGE_RECOMMENDED
from app.graph.utils import normalize_int_list as _normalize_int_list_shared
from app.graph.utils import resolve_llm_client as _resolve_llm_client_shared
from app.graph.utils import to_int_or_none as _to_int_or_none_shared
from app.graph.utils import extract_profile_destinations as _extract_profile_destinations_shared
from app.prompts.response_generation import build_response_prompt
from app.services.circuit_breaker import degradation_policy
from app.services.llm_client import LLMClient
from app.utils.logger import get_logger
from app.utils.route_content import extract_highlight_tags, flatten_text, infer_route_days

_LOGGER = get_logger(__name__)

_INTENT_MAX_TOKENS: dict[str, int] = {
    "chitchat": 150,
    "route_followup": 500,
    "route_recommend": 600,
    "price_schedule": 400,
    "visa": 500,
    "compare": 600,
    "external_info": 300,
    "rematch": 200,
}


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
    """Generate final text: try structured template first, LLM as enhancement.

    For data-heavy intents (route_recommend, price_schedule, compare), build
    a template body from tool_results and only use LLM for an opening line.
    For conversational intents (chitchat, followup), use full LLM generation.
    """

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

    template_text = _try_build_template(intent, tool_results, state)
    if template_text:
        opening = await _generate_opening_line(intent, user_message, state)
        merged_text = f"{opening}\n\n{template_text}" if opening else template_text
        return merged_text, [], False, {
            "node": "response",
            "status": "template",
            "input": {"intent": intent, "has_opening": bool(opening)},
            "output": _truncate_text(merged_text),
        }

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

    max_tokens = _INTENT_MAX_TOKENS.get(intent, 500)
    llm_client, should_close = _resolve_llm_client()
    chunks: list[str] = []
    streamed_via_callback = False
    token_emitter = state.get("token_emitter")
    try:
        async for delta in llm_client.chat_stream(messages=messages, temperature=0.5, max_tokens=max_tokens):
            if delta:
                text = str(delta)
                chunks.append(text)
                if callable(token_emitter):
                    maybe_result = token_emitter(text)
                    if inspect.isawaitable(maybe_result):
                        await maybe_result
                    streamed_via_callback = True
        await degradation_policy.llm_breaker.record_success()
    except Exception as exc:
        await degradation_policy.llm_breaker.record_failure()
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


def _try_build_template(intent: str, tool_results: dict[str, Any], state: GraphState) -> str | None:
    """Build structured response body from data. Returns None if data insufficient."""

    if intent == "route_recommend":
        return _template_route_recommend(tool_results)
    if intent == "price_schedule":
        return _template_price_schedule(tool_results)
    if intent == "compare":
        return _template_compare(tool_results)
    if intent == "visa":
        return _template_visa(tool_results)
    if intent == "external_info":
        return _template_external_info(tool_results)
    return None


def _template_route_recommend(tool_results: dict[str, Any]) -> str | None:
    """Template for route recommendation: structured route cards."""
    route_details = tool_results.get("route_details")
    if not isinstance(route_details, list) or not route_details:
        return None

    parts: list[str] = []
    for idx, detail in enumerate(route_details, 1):
        if not isinstance(detail, dict):
            continue
        name = str(detail.get("name") or "未命名线路")
        days = detail.get("days") or "?"
        raw_highlights = detail.get("highlights") or detail.get("summary") or []
        highlights = "；".join(extract_highlight_tags(raw_highlights, limit=4))
        features = str(detail.get("features") or "")
        tags = detail.get("tags")
        tag_str = "、".join(str(t) for t in tags) if isinstance(tags, list) and tags else ""

        lines = [f"**{idx}. {name}**（{days}天）"]
        if highlights:
            lines.append(f"  亮点：{highlights[:200]}")
        if features:
            lines.append(f"  特色：{features[:150]}")
        if tag_str:
            lines.append(f"  标签：{tag_str}")
        age_limit = str(detail.get("age_limit") or "")
        certificate_limit = str(detail.get("certificate_limit") or "")
        if age_limit:
            lines.append(f"  年龄限制：{age_limit[:100]}")
        if certificate_limit:
            lines.append(f"  证件要求：{certificate_limit[:100]}")
        parts.append("\n".join(lines))

    if not parts:
        return None
    body = "\n\n".join(parts)
    return f"{body}\n\n💡 您可以回复线路编号查看详细行程，或询问价格和团期。"


def _template_price_schedule(tool_results: dict[str, Any]) -> str | None:
    """Template for price and schedule response."""
    price = tool_results.get("price")
    schedule = tool_results.get("schedule")
    if not isinstance(price, dict) and not isinstance(schedule, dict):
        return None

    parts: list[str] = []
    if isinstance(price, dict):
        price_updated = tool_results.get("price_updated_at") or "未知时间"
        adult = price.get("adult_price") or price.get("price_range") or "请咨询"
        child = price.get("child_price")
        lines = [f"**💰 价格信息**（更新于 {price_updated}）", f"  成人价：{adult}"]
        if child:
            lines.append(f"  儿童价：{child}")
        cost_excluded = price.get("cost_excluded")
        if cost_excluded:
            lines.append(f"  费用不含：{cost_excluded}")
        parts.append("\n".join(lines))

    if isinstance(schedule, dict):
        schedule_updated = tool_results.get("schedule_updated_at") or "未知时间"
        dates = schedule.get("dates") or schedule.get("upcoming") or []
        if isinstance(dates, list) and dates:
            date_str = "、".join(str(d) for d in dates[:5])
            parts.append(f"**📅 最近团期**（更新于 {schedule_updated}）\n  {date_str}")
        else:
            parts.append(f"**📅 团期**（更新于 {schedule_updated}）\n  暂无可用团期，建议联系顾问确认")

    if not parts:
        return None
    return "\n\n".join(parts)


def _template_compare(tool_results: dict[str, Any]) -> str | None:
    """Template for route comparison."""
    compare_data = tool_results.get("compare_data")
    if not isinstance(compare_data, dict):
        return None
    routes = compare_data.get("routes")
    if not isinstance(routes, list) or len(routes) < 2:
        return None

    header = "| 维度 | " + " | ".join(str(r.get("name") or f"线路{i+1}") for i, r in enumerate(routes)) + " |"
    sep = "|---" * (len(routes) + 1) + "|"
    dimensions = ["days", "price_range", "highlights", "tags"]
    dim_labels = {"days": "天数", "price_range": "价格", "highlights": "亮点", "tags": "标签"}
    rows: list[str] = []
    for dim in dimensions:
        cells = []
        for r in routes:
            val = r.get(dim)
            if isinstance(val, list):
                val = "、".join(str(v) for v in val)
            cells.append(str(val or "-")[:60])
        rows.append(f"| {dim_labels.get(dim, dim)} | " + " | ".join(cells) + " |")

    if not rows:
        return None
    return f"{header}\n{sep}\n" + "\n".join(rows)


def _template_visa(tool_results: dict[str, Any]) -> str | None:
    """Template for visa query results — output structured answer directly."""
    answer = tool_results.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    return None


def _template_external_info(tool_results: dict[str, Any]) -> str | None:
    """Template for external info results — output structured answer directly."""
    output = tool_results.get("output")
    if isinstance(output, str) and output.strip():
        return output.strip()
    return None


async def _generate_opening_line(intent: str, user_message: str, state: GraphState) -> str:
    """Generate a concise, personalized opening line via LLM (max 50 tokens)."""
    if not degradation_policy.llm_available:
        return _static_opening(intent)
    try:
        llm_client, should_close = _resolve_llm_client()
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是旅游顾问。根据用户消息，用一句话（不超过30字）热情、自然地开场。"
                        "不要重复用户的话，不要提及具体线路数据，仅表达理解和引导。"
                    ),
                },
                {"role": "user", "content": user_message[:200]},
            ]
            text = await llm_client.chat(messages=messages, temperature=0.7, max_tokens=50)
            await degradation_policy.llm_breaker.record_success()
            return str(text or "").strip()
        finally:
            if should_close:
                await llm_client.aclose()
    except Exception as exc:
        await degradation_policy.llm_breaker.record_failure()
        _LOGGER.warning("opening line generation failed: %s", exc)
        return _static_opening(intent)


def _static_opening(intent: str) -> str:
    """Fallback static opening when LLM unavailable."""
    openings = {
        "route_recommend": "根据您的需求，我为您精选了以下线路：",
        "price_schedule": "以下是您关注线路的最新价格和团期：",
        "compare": "以下是您选择的线路对比：",
        "visa": "以下是您所咨询目的地的签证信息：",
        "external_info": "以下是为您查到的相关信息：",
    }
    return openings.get(intent, "")


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
    itinerary_json = detail.get("itinerary_json")
    days = infer_route_days(itinerary_json, detail.get("base_info"))
    highlight_tags = extract_highlight_tags(detail.get("highlights"), limit=3)

    return {
        "id": route_id,
        "route_id": route_id,
        "name": str(detail.get("name") or ""),
        "supplier": str(detail.get("supplier") or ""),
        "summary": str(detail.get("summary") or ""),
        "tags": detail.get("tags") if isinstance(detail.get("tags"), list) else [],
        "doc_url": detail.get("doc_url"),
        "days": days,
        "highlight_tags": highlight_tags,
        "highlights": detail.get("highlights") if isinstance(detail.get("highlights"), list) else [],
        "features": str(detail.get("features") or ""),
    }


def _extract_profile_destinations(state: GraphState) -> list[str]:
    return _extract_profile_destinations_shared(state)


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
        flatten_text(detail.get("base_info")),
        str(detail.get("features") or ""),
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
