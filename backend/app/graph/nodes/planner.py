"""Planner node: generate ordered task plan for multi-intent or complex requests."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.services.circuit_breaker import degradation_policy
from app.graph.utils import resolve_llm_client as _resolve_llm_client_shared
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_NODE_POOL: dict[str, str] = {
    "collect": "收集用户需求信息（目的地、天数、预算等），补全缺失槽位",
    "kb_search": "在知识库中检索匹配的旅游线路候选",
    "select": "从候选线路中筛选最匹配的1-3条",
    "db_detail": "从数据库获取线路详细信息（行程、价格、团期）",
    "followup": "回答用户对特定线路的追问（行程细节、费用、注意事项等）",
    "price": "查询线路的价格和团期信息",
    "visa": "查询目的地签证政策和材料要求",
    "external": "查询外部信息（天气、航班、交通等）",
    "rematch": "重置条件并重新匹配线路",
    "compare": "对比多条线路的差异",
    "chitchat": "回应闲聊、问候等非业务消息",
}

_INTENT_TO_DEFAULT_PLAN: dict[str, list[dict[str, str]]] = {
    "route_recommend": [
        {"node": "collect", "reason": "检查并收集用户需求"},
        {"node": "kb_search", "reason": "检索匹配线路"},
        {"node": "select", "reason": "筛选最优线路"},
        {"node": "db_detail", "reason": "获取线路详情"},
    ],
    "route_followup": [
        {"node": "followup", "reason": "回答线路追问"},
    ],
    "price_schedule": [
        {"node": "price", "reason": "查询价格团期"},
    ],
    "visa": [
        {"node": "visa", "reason": "查询签证信息"},
    ],
    "external_info": [
        {"node": "external", "reason": "查询外部信息"},
    ],
    "rematch": [
        {"node": "rematch", "reason": "重置匹配条件"},
    ],
    "compare": [
        {"node": "compare", "reason": "对比线路差异"},
    ],
    "chitchat": [
        {"node": "chitchat", "reason": "闲聊回应"},
    ],
}

_PLANNER_SCHEMA: dict[str, Any] = {
    "name": "task_plan",
    "schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step": {"type": "integer"},
                        "node": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["step", "node", "reason"],
                },
            },
            "strategy": {"type": "string"},
        },
        "required": ["tasks", "strategy"],
        "additionalProperties": False,
    },
}

_PLANNER_SYSTEM_PROMPT = """# 角色
你是旅游咨询系统的任务规划器（Task Planner）。

# 任务
根据用户的意图分类结果和提取的实体信息，生成一个有序的执行任务计划。每个任务对应系统中一个执行节点。

# 可用节点池
{node_descriptions}

# 工作流程
1. 分析用户的主意图和次要意图
2. 判断需要调用哪些节点、以什么顺序执行
3. 考虑节点间的依赖关系（如 kb_search 必须在 select 之前）
4. 输出有序的任务计划

# 关键约束
- 只能从上述节点池中选择，不得编造新节点
- route_recommend 流程必须按 collect → kb_search → select → db_detail 顺序
- 如果有次要意图，将其对应的节点追加在主流程之后
- 每个步骤必须有明确的 reason 说明为什么需要执行

# 输出格式
严格输出 JSON：
{{"tasks": [{{"step": 1, "node": "节点名", "reason": "原因"}}], "strategy": "sequential"}}"""


async def planner_node(state: GraphState) -> dict[str, Any]:
    """Generate task plan. Fast path for single intent, LLM for multi-intent."""

    intent = str(state.get("last_intent") or "route_recommend")
    secondary_intent = state.get("secondary_intent")
    is_multi = bool(state.get("is_multi_intent"))

    # Fast path: single intent → use static mapping
    if not is_multi or not secondary_intent:
        plan = _build_static_plan(intent)
        return {
            "task_plan": plan,
            "task_cursor": 0,
            "task_results": {},
            "retry_counts": {},
        }

    # Multi-intent: try LLM planner, fall back to static merge
    if not degradation_policy.llm_available:
        plan = _build_merged_static_plan(intent, secondary_intent)
        return {
            "task_plan": plan,
            "task_cursor": 0,
            "task_results": {},
            "retry_counts": {},
        }

    plan = await _llm_plan(intent, secondary_intent, state)
    return {
        "task_plan": plan,
        "task_cursor": 0,
        "task_results": {},
        "retry_counts": {},
    }


def _build_static_plan(intent: str) -> list[dict[str, Any]]:
    """Build task plan from static intent-to-node mapping."""

    default_tasks = _INTENT_TO_DEFAULT_PLAN.get(intent, _INTENT_TO_DEFAULT_PLAN["route_recommend"])
    return [
        {"step": i + 1, "node": t["node"], "reason": t["reason"]}
        for i, t in enumerate(default_tasks)
    ]


def _build_merged_static_plan(primary: str, secondary: str) -> list[dict[str, Any]]:
    """Merge two static plans with deduplication and dependency ordering."""

    primary_tasks = _INTENT_TO_DEFAULT_PLAN.get(primary, [])
    secondary_tasks = _INTENT_TO_DEFAULT_PLAN.get(secondary, [])

    seen_nodes: set[str] = set()
    merged: list[dict[str, str]] = []
    for t in list(primary_tasks) + list(secondary_tasks):
        node = t["node"]
        if node not in seen_nodes:
            seen_nodes.add(node)
            merged.append(t)

    merged = _enforce_dependency_order(merged)

    plan = []
    for i, t in enumerate(merged):
        plan.append({"step": i + 1, "node": t["node"], "reason": t["reason"]})
    return plan


_NODE_DEPENDENCIES: dict[str, list[str]] = {
    "select": ["kb_search"],
    "db_detail": ["select"],
    "price": ["db_detail"],
    "followup": ["db_detail"],
    "compare": ["db_detail"],
}


def _enforce_dependency_order(tasks: list[dict[str, str]]) -> list[dict[str, str]]:
    """Topological re-order to satisfy node dependency constraints."""

    node_to_task = {t["node"]: t for t in tasks}
    nodes = [t["node"] for t in tasks]

    ordered: list[str] = []
    placed: set[str] = set()

    def _place(node: str) -> None:
        if node in placed:
            return
        for dep in _NODE_DEPENDENCIES.get(node, []):
            if dep in node_to_task:
                _place(dep)
        placed.add(node)
        ordered.append(node)

    for n in nodes:
        _place(n)

    return [node_to_task[n] for n in ordered]


async def _llm_plan(intent: str, secondary_intent: str, state: GraphState) -> list[dict[str, Any]]:
    """Use LLM to generate task plan for complex multi-intent requests."""

    node_descriptions = "\n".join(f"- {k}: {v}" for k, v in _NODE_POOL.items())
    system_prompt = _PLANNER_SYSTEM_PROMPT.format(node_descriptions=node_descriptions)

    user_message = str(state.get("current_user_message") or "")
    user_prompt = (
        f"主意图: {intent}\n"
        f"次要意图: {secondary_intent}\n"
        f"用户消息: {user_message}\n"
        "请生成任务计划。"
    )

    llm_client, should_close = _resolve_llm_client_shared()
    try:
        result = await llm_client.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            json_schema=_PLANNER_SCHEMA,
            temperature=0.1,
        )
        await degradation_policy.llm_breaker.record_success()

        tasks = result.get("tasks") or []
        validated = []
        for t in tasks:
            node = str(t.get("node") or "")
            if node in _NODE_POOL:
                validated.append({
                    "step": len(validated) + 1,
                    "node": node,
                    "reason": str(t.get("reason") or ""),
                })
        if validated:
            return validated
    except Exception as exc:
        await degradation_policy.llm_breaker.record_failure()
        _LOGGER.warning("planner llm failed, fallback to static merge: %s", exc)
    finally:
        if should_close:
            await llm_client.aclose()

    return _build_merged_static_plan(intent, secondary_intent)
