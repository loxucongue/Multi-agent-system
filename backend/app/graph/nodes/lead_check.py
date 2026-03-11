"""Lead-signal detection node with cumulative scoring model."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState

_HUMAN_REASON = "留下手机号，我们的专属顾问将尽快联系您"
_SOFT_REASON = "您对该方案很感兴趣，留下手机号我们的顾问会为您锁定最新名额和优惠"
_HARD_REASON = "基于您的咨询深度，建议留下手机号，顾问第一时间为您确认报价和团期"

_SOFT_THRESHOLD = 40
_HARD_THRESHOLD = 60
_COOLDOWN_DELTA = 20

_SCORE_TABLE: dict[str, int] = {
    "intent_price_schedule": 20,
    "intent_compare": 15,
    "intent_route_followup": 10,
    "message_booking_signal": 25,
    "message_contact_signal": 20,
    "followup_ge_2": 15,
    "followup_ge_3": 10,
    "has_active_route": 10,
    "profile_complete": 5,
    "viewed_route_details": 5,
}

_BOOKING_SIGNAL_PATTERN = re.compile(
    r"(报名|下单|名额|就这个|想定|预[定订]|锁定|确认报[名价]|怎么报|怎么付|能下单)",
    flags=re.IGNORECASE,
)
_CONTACT_SIGNAL_PATTERN = re.compile(
    r"(加微信|加\s*wx|联系\s*方式|电话|给\s*报价|给个\s*报价|怎么联系|对接\s*顾问)",
    flags=re.IGNORECASE,
)


async def lead_signal_check(state: GraphState) -> dict[str, Any]:
    """Detect lead-collection trigger via cumulative scoring model.

    Scoring is additive across dimensions. Soft threshold (40) shows gentle prompt;
    hard threshold (60) shows strong prompt. Score persists in lead_score for next turn.
    """

    if str(state.get("lead_status") or "") == "captured":
        return {}

    if bool(state.get("request_human")):
        return {
            "ui_actions": [
                {
                    "action": "collect_phone",
                    "payload": {"reason": _HUMAN_REASON},
                }
            ],
            "request_human": False,
        }

    previous_score = _to_int_or_zero(state.get("lead_score"))
    delta = _compute_score_delta(state)
    total_score = previous_score + delta

    already_triggered = str(state.get("lead_status") or "") == "triggered"

    if total_score >= _HARD_THRESHOLD:
        if already_triggered and delta < _COOLDOWN_DELTA:
            return {"lead_score": total_score}
        return {
            "lead_score": total_score,
            "lead_status": "triggered",
            "ui_actions": [
                {
                    "action": "collect_phone",
                    "payload": {"reason": _HARD_REASON, "urgency": "high"},
                }
            ],
        }

    if total_score >= _SOFT_THRESHOLD:
        if already_triggered and delta < _COOLDOWN_DELTA:
            return {"lead_score": total_score}
        return {
            "lead_score": total_score,
            "lead_status": "triggered",
            "ui_actions": [
                {
                    "action": "collect_phone",
                    "payload": {"reason": _SOFT_REASON, "urgency": "low"},
                }
            ],
        }

    return {"lead_score": total_score}


def _compute_score_delta(state: GraphState) -> int:
    """Compute incremental score for this turn only."""
    score = 0
    intent = str(state.get("last_intent") or "")
    message = str(state.get("current_user_message") or "")
    followup_count = _to_int_or_zero(state.get("followup_count"))

    if intent == "price_schedule":
        score += _SCORE_TABLE["intent_price_schedule"]
    elif intent == "compare":
        score += _SCORE_TABLE["intent_compare"]
    elif intent == "route_followup":
        score += _SCORE_TABLE["intent_route_followup"]

    if _BOOKING_SIGNAL_PATTERN.search(message):
        score += _SCORE_TABLE["message_booking_signal"]
    if _CONTACT_SIGNAL_PATTERN.search(message):
        score += _SCORE_TABLE["message_contact_signal"]

    if followup_count >= 3:
        score += _SCORE_TABLE["followup_ge_2"] + _SCORE_TABLE["followup_ge_3"]
    elif followup_count >= 2:
        score += _SCORE_TABLE["followup_ge_2"]

    if state.get("active_route_id") is not None:
        score += _SCORE_TABLE["has_active_route"]

    profile = state.get("user_profile")
    if _is_profile_complete(profile):
        score += _SCORE_TABLE["profile_complete"]

    tool_results = state.get("tool_results")
    if isinstance(tool_results, dict) and tool_results.get("route_details"):
        score += _SCORE_TABLE["viewed_route_details"]

    return score


def _is_profile_complete(profile: Any) -> bool:
    """Check if user profile has at least 3 filled dimensions."""
    if profile is None:
        return False
    if hasattr(profile, "model_dump"):
        profile = profile.model_dump()
    if not isinstance(profile, dict):
        return False

    filled = 0
    if profile.get("destinations"):
        filled += 1
    if profile.get("days_range"):
        filled += 1
    if profile.get("budget_range"):
        filled += 1
    if profile.get("depart_date_range"):
        filled += 1
    if profile.get("people"):
        filled += 1
    if profile.get("style_prefs"):
        filled += 1
    return filled >= 3


def _to_int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
