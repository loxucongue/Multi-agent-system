"""Dispatcher node: lightweight task cursor controller with retry logic."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_MAX_RETRIES_PER_TASK = 2


async def dispatcher_node(state: GraphState) -> dict[str, Any]:
    """Advance task_cursor after the previous execution node completed."""

    task_plan = state.get("task_plan") or []
    cursor = state.get("task_cursor", 0)

    if cursor >= len(task_plan):
        _LOGGER.info("dispatcher: plan already complete (cursor=%s)", cursor)
        return {"task_cursor": cursor}

    current_node = task_plan[cursor].get("node", "unknown")
    new_cursor = cursor + 1
    _LOGGER.info(
        "dispatcher: task %s/%s node=%s done, cursor %s -> %s",
        cursor + 1, len(task_plan), current_node, cursor, new_cursor,
    )
    return {"task_cursor": new_cursor}


def get_current_task_node(state: GraphState) -> str:
    """Return the node name for the current task, or 'done' if plan is complete."""

    task_plan = state.get("task_plan") or []
    cursor = state.get("task_cursor", 0)

    if cursor >= len(task_plan):
        return "done"

    current_task = task_plan[cursor]
    return str(current_task.get("node", "done"))
