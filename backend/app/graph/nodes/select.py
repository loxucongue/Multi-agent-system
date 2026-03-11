"""LLM-based candidate selection node with rule-based scoring pre-filter."""

from __future__ import annotations

import json
import re
from typing import Any

from app.graph.state import GraphState
from app.graph.utils import ensure_profile as _ensure_profile_shared
from app.graph.utils import normalize_history as _normalize_history_shared
from app.graph.utils import resolve_llm_client as _resolve_llm_client_shared
from app.graph.utils import to_int_or_none as _to_int_or_none_shared
from app.graph.utils import extract_destinations_from_text as _extract_destinations_from_text_shared
from app.models.schemas import UserProfile
from app.services.circuit_breaker import degradation_policy
from app.services.llm_client import LLMClient
from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)
_SELECT_PROMPT_NODE_NAME = "route_select"

_MAX_CANDIDATES_TO_LLM = 10
_SCORE_THRESHOLD_SKIP_LLM = 7
_TOP_N_FOR_LLM = 5
_SELECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "selected_route_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "匹配度从高到低的线路ID，1～3个",
        },
        "reasoning": {
            "type": "string",
            "description": "筛选推理过程",
        },
    },
    "required": ["selected_route_ids", "reasoning"],
}

_SELECT_SYSTEM_PROMPT = """# 角色
你是旅行线路筛选专家。你的任务是从候选线路列表中，选出最符合用户需求的 1～3 条线路，并按匹配度从高到低排序。

# 输入信息
你会收到以下内容：
1. **user_profile**：用户画像 JSON，包含 destinations（目的地）、days_range（天数）、budget（预算）、travel_style（偏好风格）、departure_date（出发日期）、people（人数/人群）、origin（出发地）等字段，部分字段可能为空。
2. **candidates**：候选线路数组，每条包含 route_id、name、summary、tags、days、price_range、output（知识库原文摘要）等字段。
3. **user_message**：用户当前消息原文。
4. **conversation_history**：最近 3 轮对话记录。

# 筛选规则（按优先级）
1. **目的地硬匹配（P0）**：候选线路的 name、summary、tags、output 中必须包含用户目的地关键词或其常见别名/缩写（如"新加坡"可匹配"新马泰"、"狮城"、"Singapore"；"迪拜"可匹配"阿联酋"、"Dubai"、"UAE"）。不包含目的地关键词的线路直接排除，不得入选。
2. **天数匹配（P1）**：优先选择天数落在用户 days_range 内的线路。若用户说"一周左右"，允许 5～9 天。若无精确匹配，天数最接近的优先。
3. **预算匹配（P1）**：线路价格区间与用户 budget 有交集的优先。
4. **风格/人群匹配（P2）**：tags 或 summary 与用户 travel_style、people 有交集的加分。
5. **出发地/出发日期（P2）**：如果用户指定了 origin 或 departure_date，优先匹配。

# 输出要求
严格输出以下 JSON，不要输出任何其他文字：
{
  "selected_route_ids": [整数数组，1～3个，按匹配度降序],
  "reasoning": "简要说明筛选逻辑，每条被选中/排除的原因（中文，3～5句）"
}

# 限制
- 如果所有候选线路均不包含用户目的地关键词，返回 {"selected_route_ids": [], "reasoning": "所有候选线路均不匹配用户目的地需求"}。
- 不要编造线路信息，只能基于 candidates 中的数据判断。
- 如果 user_profile 中 destinations 为空，从 user_message 和 conversation_history 中推断目的地。
- 输出必须是合法 JSON。"""


async def select_candidates_node(state: GraphState) -> dict[str, Any]:
    """Select candidate route ids with rule-based scoring + optional LLM refinement.

    Optimization: compute a rule-based match score per candidate first.
    If top candidate scores >= _SCORE_THRESHOLD_SKIP_LLM, skip LLM entirely.
    Otherwise send Top-N to LLM for refined selection.
    """

    tool_results = state.get("tool_results")
    tool_results_dict = dict(tool_results) if isinstance(tool_results, dict) else {}
    raw_candidates = tool_results_dict.get("candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) else []

    excluded_ids = set(_normalize_int_list(state.get("excluded_route_ids")))
    filtered_candidates = _exclude_candidates(candidates, excluded_ids)

    if not filtered_candidates:
        if candidates:
            return {
                "candidate_route_ids": [],
                "active_route_id": None,
                "tool_results": {
                    **tool_results_dict,
                    "candidates_without_id": candidates,
                    "parse_warning": "route_id解析失败，请检查知识库文档格式",
                    "select_reasoning": "候选线路缺少可用 route_id，无法完成筛选",
                },
            }
        return {
            "candidate_route_ids": [],
            "active_route_id": None,
            "tool_results": {
                **tool_results_dict,
                "select_reasoning": "无候选线路（过滤排除后为空）",
            },
        }

    user_profile = _ensure_user_profile(state.get("user_profile"))
    user_message = str(state.get("current_user_message") or "")

    scored_candidates = _score_candidates(filtered_candidates, user_profile, user_message)
    scored_candidates.sort(key=lambda x: x[1], reverse=True)

    top_score = scored_candidates[0][1] if scored_candidates else 0
    _LOGGER.info(
        "select rule_scores top=%s count=%s",
        top_score,
        len(scored_candidates),
    )

    if top_score >= _SCORE_THRESHOLD_SKIP_LLM or not degradation_policy.llm_available:
        selected_ids = [item[0]["route_id"] for item in scored_candidates[:3] if item[1] > 0]
        reasoning = f"规则评分命中（top_score={top_score}），跳过LLM"
        if not degradation_policy.llm_available:
            reasoning = f"LLM降级，规则评分选择（top_score={top_score}）"
        active_route_id = selected_ids[0] if selected_ids else None
        return {
            "candidate_route_ids": selected_ids,
            "active_route_id": active_route_id,
            "tool_results": {
                **tool_results_dict,
                "select_reasoning": reasoning,
            },
        }

    llm_input_candidates = [item[0] for item in scored_candidates[:_TOP_N_FOR_LLM]]
    valid_ids = {item["route_id"] for item in llm_input_candidates}

    conversation_history = _build_conversation_history(state)
    user_prompt = _build_select_user_prompt(
        user_profile=user_profile.model_dump(),
        candidates=llm_input_candidates,
        user_message=user_message,
        history=conversation_history,
    )

    selected_ids: list[int] = []
    reasoning = ""
    llm_record: dict[str, Any] | None = None
    llm_client, should_close = _resolve_llm_client()
    try:
        system_prompt = await _resolve_select_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        result = await llm_client.chat_json(
            messages=messages,
            json_schema=_SELECT_SCHEMA,
            temperature=0.1,
        )
        await degradation_policy.llm_breaker.record_success()

        raw_ids = result.get("selected_route_ids") or []
        reasoning = str(result.get("reasoning") or "").strip()
        selected_ids = _normalize_int_list(raw_ids)
        selected_ids = [route_id for route_id in selected_ids if route_id in valid_ids][:3]
        llm_record = {
            "node": "select",
            "status": "success",
            "input": {"candidate_count": len(llm_input_candidates), "user_message": user_message},
            "output": {"selected_route_ids": selected_ids, "reasoning": reasoning},
        }
        _LOGGER.info(
            "select llm chose route_ids=%s reasoning=%s",
            selected_ids,
            reasoning[:200],
        )
    except Exception as exc:
        await degradation_policy.llm_breaker.record_failure()
        _LOGGER.exception("select llm failed, fallback to rule scores: %s", exc)
        selected_ids = [item[0]["route_id"] for item in scored_candidates[:3] if item[1] > 0]
        reasoning = f"LLM fallback: rule_score select route_ids={selected_ids}"
        llm_record = {
            "node": "select",
            "status": "fallback",
            "error": str(exc),
            "output": {"selected_route_ids": selected_ids, "reasoning": reasoning},
        }
    finally:
        if should_close:
            await llm_client.aclose()

    if not selected_ids:
        destination_only_ids = _select_by_destination_only(
            candidates=[item[0] for item in scored_candidates],
            user_profile=user_profile.model_dump(),
        )
        if destination_only_ids:
            selected_ids = destination_only_ids
            destination_reasoning = "目的地兜底命中：候选中包含用户目的地关键词，已放宽其他条件。"
            reasoning = f"{reasoning}；{destination_reasoning}" if reasoning else destination_reasoning

    active_route_id = selected_ids[0] if selected_ids else None

    payload: dict[str, Any] = {
        "candidate_route_ids": selected_ids,
        "active_route_id": active_route_id,
        "tool_results": {
            **tool_results_dict,
            "select_reasoning": reasoning or "LLM未返回有效筛选结果",
        },
    }
    if llm_record is not None:
        payload["llm_calls"] = [llm_record]
    return payload


def _score_candidates(
    candidates: list[dict[str, Any]],
    profile: UserProfile,
    user_message: str,
) -> list[tuple[dict[str, Any], int]]:
    """Rule-based multi-dimension scoring: destination +3, days +2, budget +2, style +1."""

    destinations = [str(d).strip().lower() for d in (profile.destinations or []) if str(d).strip()]
    if not destinations:
        destinations = _extract_destinations_from_text(user_message)

    days_range_str = str(profile.days_range or "").strip()
    budget_range_str = str(profile.budget_range or "").strip()
    style_prefs = [str(s).strip().lower() for s in (profile.style_prefs or []) if str(s).strip()]
    people = str(profile.people or "").strip().lower()

    scored: list[tuple[dict[str, Any], int]] = []
    for candidate in candidates:
        score = 0
        text = " ".join([
            str(candidate.get("name") or ""),
            str(candidate.get("summary") or ""),
            str(candidate.get("output") or ""),
            " ".join(str(tag) for tag in (candidate.get("tags") or []) if str(tag).strip()),
        ]).lower()

        if destinations and any(_safe_destination_match(d, text) for d in destinations):
            score += 3

        if days_range_str:
            candidate_days = candidate.get("days")
            if candidate_days is not None:
                if _days_in_range(candidate_days, days_range_str):
                    score += 2

        if budget_range_str:
            price_range = str(candidate.get("price_range") or "")
            if price_range and _budget_overlaps(price_range, budget_range_str):
                score += 2

        if style_prefs and any(s in text for s in style_prefs):
            score += 1
        if people and people in text:
            score += 1

        scored.append((candidate, score))
    return scored


_SHORT_KEYWORD_EXCLUDE = {"日", "天", "人", "月", "号", "去", "到", "想", "看", "要", "有", "了", "的"}


def _safe_destination_match(keyword: str, text: str) -> bool:
    """Match destination keyword, with false-positive guard for short keywords."""
    if not keyword:
        return False
    if len(keyword) <= 1 and keyword in _SHORT_KEYWORD_EXCLUDE:
        return False
    return keyword in text


def _days_in_range(candidate_days: Any, days_range: str) -> bool:
    """Check if candidate days falls within user's requested range."""
    try:
        c_days = int(candidate_days)
    except (TypeError, ValueError):
        return False
    nums = re.findall(r"\d+", days_range)
    if len(nums) >= 2:
        return int(nums[0]) <= c_days <= int(nums[1])
    if len(nums) == 1:
        target = int(nums[0])
        return abs(c_days - target) <= 2
    return False


def _budget_overlaps(price_range: str, budget_range: str) -> bool:
    """Check if price range overlaps with user budget range."""
    price_nums = re.findall(r"\d+", price_range.replace(",", ""))
    budget_nums = re.findall(r"\d+", budget_range.replace(",", ""))
    if not price_nums or not budget_nums:
        return False
    try:
        p_min, p_max = int(price_nums[0]), int(price_nums[-1])
        b_min, b_max = int(budget_nums[0]), int(budget_nums[-1])
        return p_min <= b_max and b_min <= p_max
    except (ValueError, IndexError):
        return False


def _exclude_candidates(candidates: list[dict[str, Any]], excluded_ids: set[int]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        route_id = _safe_int(candidate.get("route_id"))
        if route_id is None:
            continue
        if route_id in excluded_ids:
            continue
        filtered.append(_normalize_candidate(candidate, route_id))
    return filtered


def _normalize_candidate(candidate: dict[str, Any], route_id: int) -> dict[str, Any]:
    hot_route = candidate.get("hot_route")
    hot_route_dict = hot_route if isinstance(hot_route, dict) else {}
    tags = candidate.get("tags")
    if not isinstance(tags, list):
        tags = hot_route_dict.get("tags")
    normalized_tags = [str(item).strip() for item in tags] if isinstance(tags, list) else []

    return {
        "route_id": route_id,
        "name": str(candidate.get("name") or hot_route_dict.get("name") or ""),
        "summary": str(candidate.get("summary") or hot_route_dict.get("summary") or ""),
        "tags": [tag for tag in normalized_tags if tag],
        "days": candidate.get("days") or hot_route_dict.get("days"),
        "price_range": candidate.get("price_range") or hot_route_dict.get("price_range") or "",
        "output": str(candidate.get("output") or "")[:500],
    }


def _build_select_user_prompt(
    user_profile: dict[str, Any],
    candidates: list[dict[str, Any]],
    user_message: str,
    history: list[dict[str, str]],
) -> str:
    """Build user message payload for select LLM call."""

    recent = history[-6:] if len(history) > 6 else history
    parts = [
        f"## 用户画像\n```json\n{json.dumps(user_profile, ensure_ascii=False, indent=2)}\n```",
        f"## 用户当前消息\n{user_message}",
        f"## 候选线路（共 {len(candidates)} 条）\n```json\n{json.dumps(candidates, ensure_ascii=False, indent=2)}\n```",
        f"## 最近对话记录\n```json\n{json.dumps(recent, ensure_ascii=False, indent=2)}\n```",
    ]
    return "\n\n".join(parts)


def _fallback_keyword_select(
    candidates: list[dict[str, Any]],
    user_profile: dict[str, Any],
    user_message: str,
) -> list[int]:
    """Fallback selector: destination hard match + simple scoring."""

    destinations = user_profile.get("destinations")
    if not isinstance(destinations, list):
        destinations = []
    destination_keywords = [str(item).strip().lower() for item in destinations if str(item).strip()]

    if not destination_keywords:
        destination_keywords = _extract_destinations_from_text(user_message)
    if not destination_keywords:
        destination_keywords = [str(user_message or "").strip().lower()]

    scored: list[tuple[int, int]] = []
    for candidate in candidates:
        route_id = _safe_int(candidate.get("route_id"))
        if route_id is None:
            continue
        text = " ".join(
            [
                str(candidate.get("name") or ""),
                str(candidate.get("summary") or ""),
                str(candidate.get("output") or ""),
                " ".join(str(tag) for tag in (candidate.get("tags") or []) if str(tag).strip()),
            ]
        ).lower()
        destination_score = sum(3 for keyword in destination_keywords if keyword and keyword in text)
        if destination_score == 0:
            continue
        scored.append((route_id, destination_score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return [route_id for route_id, _ in scored[:3]]


def _select_by_destination_only(
    candidates: list[dict[str, Any]],
    user_profile: dict[str, Any],
) -> list[int]:
    """Select up to 3 routes by destination-only matching."""

    destinations = user_profile.get("destinations")
    if not isinstance(destinations, list):
        return []
    destination_keywords = [str(item).strip().lower() for item in destinations if str(item).strip()]
    if not destination_keywords:
        return []

    selected: list[int] = []
    for candidate in candidates:
        route_id = _safe_int(candidate.get("route_id"))
        if route_id is None:
            continue
        text = " ".join(
            [
                str(candidate.get("name") or ""),
                str(candidate.get("summary") or ""),
                str(candidate.get("output") or ""),
                " ".join(str(tag) for tag in (candidate.get("tags") or []) if str(tag).strip()),
            ]
        ).lower()
        if any(keyword in text for keyword in destination_keywords):
            selected.append(route_id)
        if len(selected) >= 3:
            break

    return selected


def _extract_destinations_from_text(text: str) -> list[str]:
    return _extract_destinations_from_text_shared(text)


def _build_conversation_history(state: GraphState) -> list[dict[str, str]]:
    context_turns = _normalize_history(state.get("context_turns"))
    if context_turns:
        return context_turns[-3:]

    messages = state.get("messages")
    if not isinstance(messages, list):
        return []

    history: list[dict[str, str]] = []
    user_buffer = ""
    for message in messages:
        role = str(getattr(message, "type", "") or getattr(message, "role", "")).strip().lower()
        content = str(getattr(message, "content", "")).strip()
        if not content:
            continue
        if role in {"human", "user"}:
            user_buffer = content
            continue
        if role in {"ai", "assistant"}:
            history.append({"user": user_buffer, "assistant": content})
            user_buffer = ""
    return history[-3:]


def _resolve_llm_client() -> tuple[LLMClient, bool]:
    return _resolve_llm_client_shared()


async def _resolve_select_system_prompt() -> str:
    try:
        active_prompt = await get_active_prompt(_SELECT_PROMPT_NODE_NAME)
        if isinstance(active_prompt, str) and active_prompt.strip():
            return active_prompt
    except Exception as exc:
        _LOGGER.warning("load route_select prompt failed, fallback to default: %s", exc)

    default_prompt = DEFAULT_PROMPTS.get(_SELECT_PROMPT_NODE_NAME)
    if isinstance(default_prompt, str) and default_prompt.strip():
        return default_prompt
    return _SELECT_SYSTEM_PROMPT


def _ensure_user_profile(value: Any) -> UserProfile:
    return _ensure_profile_shared(value)


def _normalize_history(value: Any) -> list[dict[str, str]]:
    return _normalize_history_shared(value)


def _normalize_int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    normalized: list[int] = []
    for value in values:
        parsed = _safe_int(value)
        if parsed is not None:
            normalized.append(parsed)
    return normalized


def _safe_int(value: Any) -> int | None:
    return _to_int_or_none_shared(value)
