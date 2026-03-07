"""State persistence and audit node."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.graph.state import GraphState
from app.graph.utils import to_int_or_none as _to_int_or_none_shared
from app.services.container import services


async def state_update_node(state: GraphState) -> dict[str, Any]:
    """Append turn, persist session state, write audit log, and return latest version/turns."""

    session_id = str(state.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required for state_update_node")

    trace_id = str(state.get("trace_id") or "-")
    run_id = str(state.get("run_id") or "-")
    intent = str(state.get("last_intent") or "")
    user_message = str(state.get("current_user_message") or "")
    response_text = str(state.get("response_text") or "")
    tool_results = _ensure_dict(state.get("tool_results"))
    state_patches = _ensure_dict(state.get("state_patches"))

    current_turns = _normalize_turns(state.get("context_turns", []))
    next_turns = list(current_turns)
    next_turns.append({"user": user_message, "assistant": response_text})

    session_service, audit_service = _resolve_services()

    persist_patch = dict(state_patches)
    persist_patch["context_turns"] = next_turns

    persisted_state = await session_service.update_session_state(
        session_id=session_id,
        state_patch=persist_patch,
    )

    await _write_audit_log(
        audit_service=audit_service,
        trace_id=trace_id,
        run_id=run_id,
        session_id=session_id,
        intent=intent,
        user_message=user_message,
        response_text=response_text,
        tool_results=tool_results,
        state=state,
    )

    return {
        "state_version": persisted_state.state_version,
        "context_turns": persisted_state.context_turns,
    }


async def _write_audit_log(
    audit_service: Any,
    trace_id: str,
    run_id: str,
    session_id: str,
    intent: str,
    user_message: str,
    response_text: str,
    tool_results: dict[str, Any],
    state: GraphState,
) -> None:
    route_id = _to_int_or_none(state.get("route_id"))
    if route_id is None:
        route_id = _to_int_or_none(state.get("target_route_id"))
    if route_id is None:
        route_id = _to_int_or_none(state.get("active_route_id"))
    if route_id is None:
        route_id = _to_int_or_none(tool_results.get("route_id"))

    coze_logid = _extract_first_str(_ensure_dict(state), ("coze_logid",))
    if coze_logid is None:
        coze_logid = _extract_first_str(tool_results, ("coze_logid", "logid"))
    if coze_logid is None:
        coze_logid = _extract_nested_str(tool_results, ("detail", "logid"))

    coze_debug_url = _extract_first_str(_ensure_dict(state), ("coze_debug_url",))
    if coze_debug_url is None:
        coze_debug_url = _extract_first_str(tool_results, ("coze_debug_url", "debug_url"))

    topk_results = _extract_topk_results(state=state, tool_results=tool_results)

    search_query = _extract_str(_ensure_dict(state), "search_query") or user_message or None
    api_params = _extract_api_params(state=state, tool_results=tool_results)
    db_query_summary = _extract_str(_ensure_dict(state), "db_query_summary") or _build_db_query_summary(tool_results)
    api_latency_ms = _to_int_or_none(state.get("api_latency_ms"))
    if api_latency_ms is None:
        api_latency_ms = _to_int_or_none(tool_results.get("api_latency_ms"))
    token_usage = _ensure_dict(state.get("token_usage")) or _ensure_dict(tool_results.get("token_usage"))
    error_stack = _extract_str(_ensure_dict(state), "error_stack") or _extract_str(_ensure_dict(state), "error")
    final_answer_summary = _extract_str(_ensure_dict(state), "final_answer_summary") or response_text or None

    await audit_service.log_request(
        trace_id=trace_id,
        run_id=run_id,
        session_id=session_id,
        intent=intent or "unknown",
        search_query=search_query,
        topk_results=topk_results,
        route_id=route_id,
        db_query_summary=db_query_summary,
        api_params=api_params,
        api_latency_ms=api_latency_ms,
        final_answer_summary=final_answer_summary,
        token_usage=token_usage or None,
        error_stack=error_stack,
        coze_logid=coze_logid,
        coze_debug_url=coze_debug_url,
    )


def _resolve_services() -> tuple[Any, Any]:
    try:
        return services.session_service, services.audit_service
    except Exception as exc:
        raise RuntimeError("service container is not initialized for state update node") from exc


def _normalize_turns(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    turns: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        turns.append(
            {
                "user": str(item.get("user", "")),
                "assistant": str(item.get("assistant", "")),
            }
        )
    return turns


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _extract_first_str(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_nested_str(data: dict[str, Any], path: tuple[str, ...]) -> str | None:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, str) and current.strip():
        return current.strip()
    return None


def _extract_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_api_params(state: GraphState, tool_results: dict[str, Any]) -> dict[str, Any] | None:
    params: dict[str, Any] = {}
    if isinstance(state.get("api_params"), dict):
        params.update(state["api_params"])
    elif isinstance(tool_results.get("params"), dict):
        params.update(tool_results["params"])
    elif isinstance(tool_results.get("api_params"), dict):
        params.update(tool_results["api_params"])

    llm_calls = state.get("llm_calls")
    if isinstance(llm_calls, list) and llm_calls:
        params["llm_calls"] = llm_calls

    return params or None


def _extract_topk_results(state: GraphState, tool_results: dict[str, Any]) -> Any:
    state_topk = state.get("topk_results")
    if isinstance(state_topk, (list, dict)):
        return state_topk

    for key in ("candidates", "route_details", "compare_data", "sources"):
        if key in tool_results:
            return tool_results.get(key)
    return None


def _build_db_query_summary(tool_results: dict[str, Any]) -> str | None:
    if not tool_results:
        return None
    keys = sorted(tool_results.keys())
    return f"tool_results keys={','.join(keys)} at={datetime.utcnow().isoformat()}"


def _to_int_or_none(value: Any) -> int | None:
    return _to_int_or_none_shared(value)
