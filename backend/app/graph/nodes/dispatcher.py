"""Dispatcher node: task cursor controller with retry and result snapshot."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_MAX_RETRIES_PER_TASK = 2

_TASK_FAILURE_SIGNALS: dict[str, list[str]] = {
    "kb_search": ["candidates"],
    "select": ["candidate_route_ids"],
    "db_detail": ["route_details", "route_detail"],
}


def _is_task_failed(node_name: str, state: GraphState) -> bool:
    """Check if the just-completed task produced meaningful output."""
    required_keys = _TASK_FAILURE_SIGNALS.get(node_name)
    if not required_keys:
        return False
    tool_results = state.get("tool_results")
    if not isinstance(tool_results, dict):
        return True
    for key in required_keys:
        val = tool_results.get(key)
        if isinstance(val, list) and val:
            return False
        if isinstance(val, dict) and val:
            return False
    return True


def _snapshot_task_results(cursor: int, state: GraphState) -> dict[int, dict[str, Any]]:
    """Copy current tool_results into task_results keyed by cursor index."""
    existing = dict(state.get("task_results") or {})
    tool_results = state.get("tool_results")
    if isinstance(tool_results, dict) and tool_results:
        existing[cursor] = dict(tool_results)
    return existing


async def dispatcher_node(state: GraphState) -> dict[str, Any]:
    """Advance cursor, snapshot results, and retry on failure if within budget."""

    task_plan = state.get("task_plan") or []
    cursor = state.get("task_cursor", 0)

    if cursor >= len(task_plan):
        _LOGGER.info("dispatcher: plan already complete (cursor=%s)", cursor)
        return {"task_cursor": cursor}

    current_node = task_plan[cursor].get("node", "unknown")
    retry_counts = dict(state.get("retry_counts") or {})
    current_retries = retry_counts.get(cursor, 0)

    if _is_task_failed(current_node, state) and current_retries < _MAX_RETRIES_PER_TASK:
        retry_counts[cursor] = current_retries + 1
        _LOGGER.warning(
            "dispatcher: task %s/%s node=%s failed, retry %s/%s (cursor stays %s)",
            cursor + 1, len(task_plan), current_node,
            retry_counts[cursor], _MAX_RETRIES_PER_TASK, cursor,
        )
        return {"retry_counts": retry_counts}

    task_results = _snapshot_task_results(cursor, state)
    new_cursor = cursor + 1
    _LOGGER.info(
        "dispatcher: task %s/%s node=%s done, cursor %s -> %s",
        cursor + 1, len(task_plan), current_node, cursor, new_cursor,
    )
    return {
        "task_cursor": new_cursor,
        "task_results": task_results,
    }


def get_current_task_node(state: GraphState) -> str:
    """Return the node name for the current task, or 'done' if plan is complete."""

    task_plan = state.get("task_plan") or []
    cursor = state.get("task_cursor", 0)

    if cursor >= len(task_plan):
        return "done"

    current_task = task_plan[cursor]
    return str(current_task.get("node", "done"))
