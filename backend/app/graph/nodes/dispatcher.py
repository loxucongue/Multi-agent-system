"""Dispatcher node: lightweight task cursor controller with retry logic."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_MAX_RETRIES_PER_TASK = 2


async def dispatcher_node(state: GraphState) -> dict[str, Any]:
    """Advance task_cursor or trigger retry based on current task result."""

    task_plan = state.get("task_plan") or []
    cursor = state.get("task_cursor", 0)
    task_results = dict(state.get("task_results") or {})
    retry_counts = dict(state.get("retry_counts") or {})

    if cursor >= len(task_plan):
        return {
            "task_cursor": cursor,
            "task_results": task_results,
            "retry_counts": retry_counts,
        }

    current_task = task_plan[cursor]
    current_node = current_task.get("node", "")
    current_result = task_results.get(cursor)

    if current_result is None:
        return {
            "task_cursor": cursor,
            "task_results": task_results,
            "retry_counts": retry_counts,
        }

    success = bool(current_result.get("success", True))
    if success:
        new_cursor = cursor + 1
        _LOGGER.info(
            "dispatcher: task %s/%s node=%s succeeded, advancing cursor",
            cursor + 1, len(task_plan), current_node,
        )
        return {
            "task_cursor": new_cursor,
            "task_results": task_results,
            "retry_counts": retry_counts,
        }

    current_retries = retry_counts.get(cursor, 0)
    if current_retries < _MAX_RETRIES_PER_TASK:
        retry_counts[cursor] = current_retries + 1
        task_results.pop(cursor, None)
        _LOGGER.info(
            "dispatcher: task %s node=%s failed, retry %s/%s",
            cursor + 1, current_node, current_retries + 1, _MAX_RETRIES_PER_TASK,
        )
        return {
            "task_cursor": cursor,
            "task_results": task_results,
            "retry_counts": retry_counts,
        }

    _LOGGER.warning(
        "dispatcher: task %s node=%s exhausted retries, advancing to next",
        cursor + 1, current_node,
    )
    new_cursor = cursor + 1
    return {
        "task_cursor": new_cursor,
        "task_results": task_results,
        "retry_counts": retry_counts,
    }


def get_current_task_node(state: GraphState) -> str:
    """Return the node name for the current task, or 'done' if plan is complete."""

    task_plan = state.get("task_plan") or []
    cursor = state.get("task_cursor", 0)

    if cursor >= len(task_plan):
        return "done"

    current_task = task_plan[cursor]
    return str(current_task.get("node", "done"))
