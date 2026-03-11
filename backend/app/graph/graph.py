"""LangGraph workflow assembly and execution helpers."""

from __future__ import annotations

import json
import time
from typing import Any

from langgraph.graph import END, START, StateGraph
from redis import asyncio as aioredis

from app.graph.nodes.chitchat import chitchat_node
from app.graph.nodes.collect import collect_requirements_node
from app.graph.nodes.compare import compare_node
from app.graph.nodes.db_detail import route_db_detail_node
from app.graph.nodes.dispatcher import dispatcher_node
from app.graph.nodes.external import external_api_node
from app.graph.nodes.followup import route_followup_node
from app.graph.nodes.kb_search import routes_kb_search_node
from app.graph.nodes.lead_check import lead_signal_check
from app.graph.nodes.planner import planner_node
from app.graph.nodes.price import price_schedule_node
from app.graph.nodes.rematch import rematch_reset_node
from app.graph.nodes.response import response_generation_node
from app.graph.nodes.router import router_intent_node
from app.graph.nodes.select import select_candidates_node
from app.graph.nodes.state_update import state_update_node
from app.graph.nodes.visa import visa_kb_search_node
from app.graph.state import GraphState, create_initial_state
from app.services.container import services
from app.utils.helpers import generate_run_id, generate_trace_id
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

NODE_ROUTER = "router"
NODE_COLLECT = "collect"
NODE_KB_SEARCH = "kb_search"
NODE_SELECT = "select"
NODE_DB_DETAIL = "db_detail"
NODE_FOLLOWUP = "followup"
NODE_PRICE = "price"
NODE_VISA = "visa"
NODE_EXTERNAL = "external"
NODE_REMATCH = "rematch"
NODE_COMPARE = "compare"
NODE_CHITCHAT = "chitchat"
NODE_RESPONSE = "response"
NODE_LEAD_CHECK = "lead_check"
NODE_STATE_UPDATE = "state_update"
NODE_PLANNER = "planner"
NODE_DISPATCHER = "dispatcher"
_MAX_EVENTS_PER_RUN = 1000


_TASK_NODE_MAP: dict[str, str] = {
    "collect": NODE_COLLECT,
    "kb_search": NODE_KB_SEARCH,
    "select": NODE_SELECT,
    "db_detail": NODE_DB_DETAIL,
    "followup": NODE_FOLLOWUP,
    "price": NODE_PRICE,
    "visa": NODE_VISA,
    "external": NODE_EXTERNAL,
    "rematch": NODE_REMATCH,
    "compare": NODE_COMPARE,
    "chitchat": NODE_CHITCHAT,
}


def _dispatch_task(state: GraphState) -> str:
    """Route to next execution node based on task_plan[task_cursor]."""

    plan = state.get("task_plan") or []
    cursor = state.get("task_cursor", 0)
    if cursor >= len(plan):
        return NODE_RESPONSE
    node_name = str(plan[cursor].get("node", ""))
    return _TASK_NODE_MAP.get(node_name, NODE_RESPONSE)


def _after_collect_in_plan(state: GraphState) -> str:
    """Route collect output: advance plan if slots ready, else respond."""

    if state.get("slots_ready", False):
        return NODE_DISPATCHER
    return NODE_RESPONSE


def _after_rematch_in_plan(state: GraphState) -> str:
    """Route rematch output: respond if human needed, else advance plan."""

    if state.get("request_human"):
        return NODE_RESPONSE
    return NODE_DISPATCHER


def _build_workflow() -> StateGraph:
    """Build the planner-dispatcher graph with execution node pool."""

    workflow = StateGraph(GraphState)

    workflow.add_node(NODE_ROUTER, router_intent_node)
    workflow.add_node(NODE_PLANNER, planner_node)
    workflow.add_node(NODE_DISPATCHER, dispatcher_node)
    workflow.add_node(NODE_COLLECT, collect_requirements_node)
    workflow.add_node(NODE_KB_SEARCH, routes_kb_search_node)
    workflow.add_node(NODE_SELECT, select_candidates_node)
    workflow.add_node(NODE_DB_DETAIL, route_db_detail_node)
    workflow.add_node(NODE_FOLLOWUP, route_followup_node)
    workflow.add_node(NODE_PRICE, price_schedule_node)
    workflow.add_node(NODE_VISA, visa_kb_search_node)
    workflow.add_node(NODE_EXTERNAL, external_api_node)
    workflow.add_node(NODE_REMATCH, rematch_reset_node)
    workflow.add_node(NODE_COMPARE, compare_node)
    workflow.add_node(NODE_CHITCHAT, chitchat_node)
    workflow.add_node(NODE_RESPONSE, response_generation_node)
    workflow.add_node(NODE_LEAD_CHECK, lead_signal_check)
    workflow.add_node(NODE_STATE_UPDATE, state_update_node)

    # Entry: START → Router → Planner
    workflow.add_edge(START, NODE_ROUTER)
    workflow.add_edge(NODE_ROUTER, NODE_PLANNER)

    # Planner and Dispatcher both dispatch to the next task node
    _all_task_targets = {
        NODE_COLLECT: NODE_COLLECT,
        NODE_KB_SEARCH: NODE_KB_SEARCH,
        NODE_SELECT: NODE_SELECT,
        NODE_DB_DETAIL: NODE_DB_DETAIL,
        NODE_FOLLOWUP: NODE_FOLLOWUP,
        NODE_PRICE: NODE_PRICE,
        NODE_VISA: NODE_VISA,
        NODE_EXTERNAL: NODE_EXTERNAL,
        NODE_REMATCH: NODE_REMATCH,
        NODE_COMPARE: NODE_COMPARE,
        NODE_CHITCHAT: NODE_CHITCHAT,
        NODE_RESPONSE: NODE_RESPONSE,
    }
    workflow.add_conditional_edges(NODE_PLANNER, _dispatch_task, _all_task_targets)
    workflow.add_conditional_edges(NODE_DISPATCHER, _dispatch_task, _all_task_targets)

    # Collect: slots ready → dispatcher (advance), not ready → response (ask questions)
    workflow.add_conditional_edges(
        NODE_COLLECT,
        _after_collect_in_plan,
        {NODE_DISPATCHER: NODE_DISPATCHER, NODE_RESPONSE: NODE_RESPONSE},
    )

    # Rematch: request_human → response, else → dispatcher (advance)
    workflow.add_conditional_edges(
        NODE_REMATCH,
        _after_rematch_in_plan,
        {NODE_DISPATCHER: NODE_DISPATCHER, NODE_RESPONSE: NODE_RESPONSE},
    )

    # All other execution nodes → Dispatcher (to advance cursor)
    for node in [
        NODE_KB_SEARCH, NODE_SELECT, NODE_DB_DETAIL, NODE_FOLLOWUP,
        NODE_PRICE, NODE_VISA, NODE_EXTERNAL, NODE_COMPARE, NODE_CHITCHAT,
    ]:
        workflow.add_edge(node, NODE_DISPATCHER)

    # Response chain
    workflow.add_edge(NODE_RESPONSE, NODE_LEAD_CHECK)
    workflow.add_edge(NODE_LEAD_CHECK, NODE_STATE_UPDATE)
    workflow.add_edge(NODE_STATE_UPDATE, END)

    return workflow


workflow = _build_workflow()
graph = workflow.compile()


async def run_graph(session_id: str, user_message: str) -> dict[str, Any]:
    """Load persisted session state and run one LangGraph turn."""

    await services.initialize()

    session_state = await services.session_service.get_session_state(session_id)
    if session_state is None:
        raise ValueError(f"session not found or expired: {session_id}")

    trace_id = generate_trace_id()
    run_id = generate_run_id()

    initial_state = create_initial_state(
        session_state=session_state,
        user_message=user_message,
        trace_id=trace_id,
        run_id=run_id,
    )
    initial_state["session_id"] = session_id

    result = await graph.ainvoke(initial_state)
    return dict(result)


async def run_graph_streaming(
    session_id: str,
    user_message: str,
    run_id: str,
    trace_id: str,
    redis_client: aioredis.Redis,
) -> None:
    """Execute graph and stream node outputs into Redis events list."""

    events_key = f"events:{run_id}"
    done_key = f"done:{run_id}"

    async def _push(event_type: str, data: Any) -> None:
        payload = json.dumps({"event": event_type, "data": data}, ensure_ascii=False, default=str)
        await redis_client.rpush(events_key, payload)
        await redis_client.ltrim(events_key, -_MAX_EVENTS_PER_RUN, -1)
        await redis_client.expire(events_key, 300)

    try:
        await services.initialize()
        session_state = await services.session_service.get_session_state(session_id)
        if session_state is None:
            await _push("error", {"message": f"session not found: {session_id}"})
            return

        initial_state = create_initial_state(
            session_state=session_state,
            user_message=user_message,
            trace_id=trace_id,
            run_id=run_id,
        )
        initial_state["session_id"] = session_id
        
        async def _emit_token(delta: str) -> None:
            text = str(delta or "")
            if text:
                await _push("token", {"text": text, "node": NODE_RESPONSE})

        initial_state["token_emitter"] = _emit_token

        final_state: dict[str, Any] = dict(initial_state)
        node_timings: list[dict[str, Any]] = []
        run_started_at = time.monotonic()
        last_node_end = run_started_at
        async for event in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue

                node_end = time.monotonic()
                node_start = last_node_end
                last_node_end = node_end
                node_timings.append(
                    {
                        "node": node_name,
                        "start_ms": int((node_start - run_started_at) * 1000),
                        "end_ms": int((node_end - run_started_at) * 1000),
                        "duration_ms": int((node_end - node_start) * 1000),
                    }
                )

                final_state.update(node_output)

                if (
                    node_name == NODE_RESPONSE
                    and "response_text" in node_output
                    and node_output["response_text"]
                ):
                    if not bool(node_output.get("response_streamed")):
                        token_chunks = node_output.get("response_tokens")
                        if isinstance(token_chunks, list) and token_chunks:
                            for chunk in token_chunks:
                                text = str(chunk or "")
                                if text:
                                    await _push("token", {"text": text, "node": node_name})
                        else:
                            await _push("token", {"text": node_output["response_text"], "node": node_name})

                if node_name == NODE_COLLECT and node_output.get("slots_ready"):
                    await _push("interim", "正在为您匹配线路，请稍等...")

                if "ui_actions" in node_output:
                    for action in node_output.get("ui_actions") or []:
                        await _push("ui_action", action)

                cards = node_output.get("cards") or []
                if cards:
                    await _push("cards", cards)

                patches = node_output.get("state_patches") or {}
                if patches:
                    await _push("state_patch", patches)

        await _push("done", {"trace_id": trace_id, "run_id": run_id})
        await redis_client.set(done_key, "1", ex=300)
        await _persist_node_timing_audit(
            session_id=session_id,
            trace_id=trace_id,
            run_id=run_id,
            node_timings=node_timings,
        )
    except Exception as exc:
        _LOGGER.exception("graph streaming error run_id=%s", run_id)
        try:
            await _push("error", {"message": str(exc)})
        except Exception:
            pass
        try:
            await _persist_node_timing_audit(
                session_id=session_id,
                trace_id=trace_id,
                run_id=run_id,
                node_timings=node_timings if "node_timings" in locals() else [],
                error_message=str(exc),
            )
        except Exception:
            pass


async def _persist_node_timing_audit(
    *,
    session_id: str,
    trace_id: str,
    run_id: str,
    node_timings: list[dict[str, Any]],
    error_message: str | None = None,
) -> None:
    if not node_timings:
        return
    try:
        await services.audit_service.log_request(
            trace_id=trace_id,
            run_id=run_id,
            session_id=session_id,
            intent="node_timing",
            api_params={"node_timings": node_timings},
            api_latency_ms=sum(int(item.get("duration_ms", 0) or 0) for item in node_timings),
            final_answer_summary="graph node timing metrics",
            error_stack=error_message,
        )
    except Exception as exc:
        _LOGGER.warning("failed to persist node timing audit run_id=%s err=%s", run_id, exc)
