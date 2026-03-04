"""General helper functions."""

from __future__ import annotations

from uuid import uuid4


def generate_trace_id() -> str:
    """Generate trace id in format: tr_{uuid4 short}."""

    return f"tr_{uuid4().hex[:8]}"


def generate_run_id() -> str:
    """Generate run id in format: run_{uuid4 short}."""

    return f"run_{uuid4().hex[:8]}"
