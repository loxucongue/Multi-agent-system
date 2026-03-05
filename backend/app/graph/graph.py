"""LangGraph workflow assembly and execution helpers."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.chitchat import chitchat_node
from app.graph.nodes.collect import collect_requirements_node
from app.graph.nodes.compare import compare_node
from app.graph.nodes.db_detail import route_db_detail_node
from app.graph.nodes.external import external_api_node
from app.graph.nodes.followup import route_followup_node
from app.graph.nodes.kb_search import routes_kb_search_node
from app.graph.nodes.lead_check import lead_signal_check
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


def check_slots_ready(state: GraphState) -> str:
    """Route collect node output by slot sufficiency."""

    if state.get("slots_ready", False):
        return NODE_KB_SEARCH
    return NODE_RESPONSE


def _route_by_intent(state: GraphState) -> str:
    intent = str(state.get("last_intent") or "route_recommend")
    mapping = {
        "route_recommend": NODE_COLLECT,
        "route_followup": NODE_FOLLOWUP,
        "price_schedule": NODE_PRICE,
        "visa": NODE_VISA,
        "external_info": NODE_EXTERNAL,
        "rematch": NODE_REMATCH,
        "compare": NODE_COMPARE,
        "chitchat": NODE_CHITCHAT,
    }
    return mapping.get(intent, NODE_COLLECT)


def _build_workflow() -> StateGraph:
    workflow = StateGraph(GraphState)

    workflow.add_node(NODE_ROUTER, router_intent_node)
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

    workflow.add_edge(START, NODE_ROUTER)

    workflow.add_conditional_edges(
        NODE_ROUTER,
        _route_by_intent,
        {
            NODE_COLLECT: NODE_COLLECT,
            NODE_FOLLOWUP: NODE_FOLLOWUP,
            NODE_PRICE: NODE_PRICE,
            NODE_VISA: NODE_VISA,
            NODE_EXTERNAL: NODE_EXTERNAL,
            NODE_REMATCH: NODE_REMATCH,
            NODE_COMPARE: NODE_COMPARE,
            NODE_CHITCHAT: NODE_CHITCHAT,
        },
    )

    workflow.add_edge(NODE_REMATCH, NODE_COLLECT)
    workflow.add_conditional_edges(
        NODE_COLLECT,
        check_slots_ready,
        {
            NODE_KB_SEARCH: NODE_KB_SEARCH,
            NODE_RESPONSE: NODE_RESPONSE,
        },
    )

    workflow.add_edge(NODE_KB_SEARCH, NODE_SELECT)
    workflow.add_edge(NODE_SELECT, NODE_DB_DETAIL)
    workflow.add_edge(NODE_DB_DETAIL, NODE_RESPONSE)

    workflow.add_edge(NODE_FOLLOWUP, NODE_RESPONSE)
    workflow.add_edge(NODE_PRICE, NODE_RESPONSE)
    workflow.add_edge(NODE_VISA, NODE_RESPONSE)
    workflow.add_edge(NODE_EXTERNAL, NODE_RESPONSE)
    workflow.add_edge(NODE_COMPARE, NODE_RESPONSE)
    workflow.add_edge(NODE_CHITCHAT, NODE_RESPONSE)

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

