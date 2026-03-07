"""Route knowledge-base search node."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.graph.utils import ensure_profile as _ensure_profile_shared
from app.graph.utils import normalize_history as _normalize_history_shared
from app.graph.utils import resolve_llm_client as _resolve_llm_client_shared
from app.models.schemas import UserProfile
from app.prompts.kb_query_gen import build_kb_query_gen_prompt
from app.prompts.kb_result_eval import build_kb_result_eval_prompt
from app.services.container import services
from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)
_DAY_SUFFIX = "天"
_MAX_ATTEMPTS = 3
_KB_EVAL_SCHEMA: dict[str, Any] = {
    "name": "kb_result_eval",
    "schema": {
        "type": "object",
        "properties": {
            "relevant": {"type": "boolean"},
            "reasoning": {"type": "string"},
        },
        "required": ["relevant", "reasoning"],
        "additionalProperties": True,
    },
}


async def routes_kb_search_node(state: GraphState) -> dict[str, Any]:
    """Search route candidates from KB with an agentic retry loop."""

    profile = _ensure_profile(state.get("user_profile"))
    user_message = str(state.get("current_user_message") or "").strip()
    trace_id = str(state.get("trace_id") or "-")
    session_id = str(state.get("session_id") or "")
    history = _normalize_history(state.get("context_turns"))

    workflow_service, route_service = _resolve_search_services()
    llm_client, should_close = _resolve_llm_client()

    previous_query: str | None = None
    previous_result_summary: str | None = None

    try:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            query = await _generate_route_query(
                llm_client=llm_client,
                profile=profile,
                user_message=user_message,
                history=history,
                attempt=attempt,
                previous_query=previous_query,
                previous_result_summary=previous_result_summary,
            )
            if not query:
                query = _fallback_query_for_attempt(profile, attempt, previous_query)
            if not query:
                _LOGGER.info("route_kb_search trace_id=%s attempt=%s skipped empty query", trace_id, attempt)
                continue

            _LOGGER.info("route_kb_search trace_id=%s attempt=%s query=%r", trace_id, attempt, query)
            candidates = await _search_candidates(workflow_service, query, trace_id, session_id)
            if not candidates:
                _LOGGER.info("route_kb_search trace_id=%s attempt=%s candidates=0", trace_id, attempt)
                previous_query = query
                previous_result_summary = None
                continue

            previous_result_summary = _summarize_candidates(candidates)
            relevant, reasoning = await _evaluate_candidates_relevance(
                llm_client=llm_client,
                user_message=user_message,
                profile=profile,
                query=query,
                candidates=candidates,
            )
            _LOGGER.info(
                "route_kb_search trace_id=%s attempt=%s relevant=%s reasoning=%s candidates=%s",
                trace_id,
                attempt,
                relevant,
                reasoning,
                len(candidates),
            )
            if relevant:
                candidates = await _resolve_candidate_route_ids(route_service, candidates, trace_id)
                return {"tool_results": {"candidates": candidates}}

            previous_query = query

        hot_routes = await route_service.get_hot_routes()
        candidates = [_hot_route_to_candidate(route) for route in hot_routes]
        candidates = await _resolve_candidate_route_ids(route_service, candidates, trace_id)
        return {"tool_results": {"candidates": candidates}}
    finally:
        if should_close:
            await llm_client.aclose()


def _resolve_search_services() -> tuple[Any, Any]:
    try:
        return services.workflow_service, services.route_service
    except Exception as exc:
        raise RuntimeError("service container is not initialized for kb search node") from exc


def _resolve_llm_client() -> tuple[LLMClient, bool]:
    return _resolve_llm_client_shared()


def _ensure_profile(value: Any) -> UserProfile:
    return _ensure_profile_shared(value)


async def _generate_route_query(
    llm_client: LLMClient,
    profile: UserProfile,
    user_message: str,
    history: list[dict[str, str]],
    attempt: int,
    previous_query: str | None,
    previous_result_summary: str | None,
) -> str | None:
    try:
        messages = await build_kb_query_gen_prompt(
            user_profile=profile.model_dump(),
            user_message=user_message,
            history=history,
            attempt=attempt,
            previous_query=previous_query,
            previous_result_summary=previous_result_summary,
        )
        text = await llm_client.chat(messages=messages, temperature=0.1, max_tokens=96)
        return _normalize_query(text)
    except Exception as exc:
        _LOGGER.warning("route kb query generation failed attempt=%s: %s", attempt, exc)
        return None


def _fallback_query_for_attempt(profile: UserProfile, attempt: int, previous_query: str | None) -> str:
    primary_query = _build_primary_query(profile)
    if attempt == 1:
        return primary_query

    destination_only_query = _build_destination_query(profile)
    if destination_only_query and destination_only_query != previous_query:
        return destination_only_query

    return primary_query


def _normalize_query(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("\r", "\n").strip()
    if "\n" in text:
        text = text.splitlines()[0].strip()
    return text.strip("\"' ") or None


def _build_primary_query(profile: UserProfile) -> str:
    destinations = " ".join([v for v in profile.destinations if str(v).strip()]).strip()

    days_range = (profile.days_range or "").strip()
    days_part = ""
    if days_range:
        days_part = days_range if days_range.endswith(_DAY_SUFFIX) else f"{days_range}{_DAY_SUFFIX}"

    style_part = " ".join([v for v in profile.style_prefs if str(v).strip()]).strip()
    budget_part = (profile.budget_range or "").strip()

    parts = [destinations, days_part, style_part, budget_part]
    return " ".join([part for part in parts if part]).strip()


def _build_destination_query(profile: UserProfile) -> str:
    return " ".join([v for v in profile.destinations if str(v).strip()]).strip()


async def _search_candidates(workflow_service: Any, query: str, trace_id: str, session_id: str) -> list[dict[str, Any]]:
    try:
        result = await workflow_service.run_route_search(query=query, trace_id=trace_id, session_id=session_id)
    except Exception as exc:
        _LOGGER.warning("route kb search failed query=%r: %s", query, exc)
        return []

    raw_candidates = getattr(result, "candidates", None)
    if not isinstance(raw_candidates, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_candidates:
        if hasattr(item, "model_dump"):
            payload = item.model_dump()
        elif isinstance(item, dict):
            payload = dict(item)
        else:
            continue
        normalized.append(payload)

    return normalized


async def _evaluate_candidates_relevance(
    llm_client: LLMClient,
    user_message: str,
    profile: UserProfile,
    query: str,
    candidates: list[dict[str, Any]],
) -> tuple[bool, str]:
    try:
        messages = await build_kb_result_eval_prompt(
            user_message=user_message,
            user_profile=profile.model_dump(),
            query=query,
            candidates=candidates,
        )
        result = await llm_client.chat_json(messages=messages, json_schema=_KB_EVAL_SCHEMA, temperature=0.1)
        relevant = bool(result.get("relevant", False))
        reasoning = str(result.get("reasoning") or "").strip() or "llm_eval"
        return relevant, reasoning
    except Exception as exc:
        reasoning = f"fallback_eval:{exc}"
        return _basic_relevance_check(profile, candidates), reasoning


def _basic_relevance_check(profile: UserProfile, candidates: list[dict[str, Any]]) -> bool:
    if not candidates:
        return False

    keywords = {
        *(str(item).strip() for item in profile.destinations if str(item).strip()),
        *(str(item).strip() for item in profile.style_prefs if str(item).strip()),
        str(profile.days_range or "").strip(),
    }
    keywords = {item for item in keywords if item}
    if not keywords:
        return True

    for candidate in candidates:
        text_parts = [
            str(candidate.get("output") or ""),
            str(candidate.get("document_id") or ""),
        ]
        hot_route = candidate.get("hot_route")
        if isinstance(hot_route, dict):
            text_parts.extend(
                [
                    str(hot_route.get("name") or ""),
                    str(hot_route.get("summary") or ""),
                ]
            )
        combined = " ".join(text_parts)
        if any(keyword in combined for keyword in keywords):
            return True
    return False


def _summarize_candidates(candidates: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in candidates[:3]:
        if not isinstance(item, dict):
            continue
        hot_route = item.get("hot_route")
        if isinstance(hot_route, dict):
            name = str(hot_route.get("name") or "").strip()
            summary = str(hot_route.get("summary") or "").strip()
            merged = " ".join(part for part in (name, summary) if part)
        else:
            merged = str(item.get("output") or "").strip()
        if merged:
            parts.append(merged[:120])
    return " | ".join(parts)


def _normalize_history(value: Any) -> list[dict[str, str]]:
    return _normalize_history_shared(value)


def _hot_route_to_candidate(route_card: Any) -> dict[str, Any]:
    payload = route_card.model_dump() if hasattr(route_card, "model_dump") else dict(route_card)
    route_id = payload.get("id")
    route_id_str = _to_int_str_or_none(route_id)
    return {
        "document_id": f"hot_route_{route_id}",
        "route_id": route_id_str,
        "output": str(payload.get("summary") or ""),
        "hot_route": payload,
    }


async def _resolve_candidate_route_ids(
    route_service: Any,
    candidates: list[dict[str, Any]],
    trace_id: str,
) -> list[dict[str, Any]]:
    """Map URL-like route_id values into DB integer route ids."""

    url_route_ids: list[str] = []
    for candidate in candidates:
        route_id = candidate.get("route_id")
        if isinstance(route_id, str) and route_id.startswith("http"):
            url_route_ids.append(route_id)

    if not url_route_ids:
        return candidates

    url_to_id = await route_service.resolve_route_ids_by_doc_urls(url_route_ids)
    _LOGGER.info(
        "route_id mapping trace_id=%s urls=%s mapped=%s",
        trace_id,
        len(url_route_ids),
        len(url_to_id),
    )
    if url_to_id:
        preview = list(url_to_id.items())[:5]
        _LOGGER.info("route_id mapping preview trace_id=%s preview=%s", trace_id, preview)

    resolved: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        route_id = item.get("route_id")
        if isinstance(route_id, str) and route_id.startswith("http"):
            db_id = url_to_id.get(route_id)
            if db_id is not None:
                item["route_id"] = str(db_id)
            else:
                stripped = route_id.strip().rstrip("/")
                db_id = url_to_id.get(stripped)
                if db_id is not None:
                    item["route_id"] = str(db_id)
                else:
                    _LOGGER.warning(
                        "route_id url not found in routes table trace_id=%s url=%s",
                        trace_id,
                        route_id,
                    )
                    item["route_id"] = None
        resolved.append(item)

    missing_count = sum(1 for item in resolved if item.get("route_id") is None)
    if missing_count:
        _LOGGER.warning(
            "route_id mapping unresolved trace_id=%s missing=%s total=%s",
            trace_id,
            missing_count,
            len(resolved),
        )

    return resolved


def _to_int_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(int(value))
    except (TypeError, ValueError):
        _LOGGER.warning("hot route id is not int-convertible, id=%s", value)
        return None
