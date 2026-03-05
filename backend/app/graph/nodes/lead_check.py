"""Lead-signal detection node."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState

_STRONG_INTEREST_REASON = "您对该路线表现出较强兴趣，留下手机号顾问会为您确认最新信息"
_HUMAN_REASON = "留下手机号，我们的专属顾问将尽快联系您"

_INTEREST_INTENTS = {"price_schedule", "compare"}
_MESSAGE_SIGNAL_PATTERN = re.compile(
    r"(报名|下单|名额|就这个|想定|加微信|给\s*报价|给个\s*报价)",
    flags=re.IGNORECASE,
)


async def lead_signal_check(state: GraphState) -> dict[str, Any]:
    """Detect lead-collection trigger signal and append collect_phone UI action."""

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

    last_intent = str(state.get("last_intent") or "")
    current_user_message = str(state.get("current_user_message") or "")
    followup_count = _to_int_or_zero(state.get("followup_count"))

    should_trigger = (
        last_intent in _INTEREST_INTENTS
        or _MESSAGE_SIGNAL_PATTERN.search(current_user_message) is not None
        or followup_count >= 2
    )
    if not should_trigger:
        return {}

    return {
        "ui_actions": [
            {
                "action": "collect_phone",
                "payload": {"reason": _STRONG_INTEREST_REASON},
            }
        ]
    }


def _to_int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
