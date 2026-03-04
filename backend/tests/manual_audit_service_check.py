"""Manual smoke test for AuditService write/query flow."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.database import async_session_factory, engine
from app.services.audit_service import AuditService
from app.utils.helpers import generate_run_id, generate_trace_id


async def main() -> None:
    service = AuditService(async_session_factory)
    trace_id = generate_trace_id()
    run_id = generate_run_id()
    session_id = "manual-audit-session"

    await service.log_request(
        trace_id=trace_id,
        run_id=run_id,
        session_id=session_id,
        intent="route_search",
        search_query="联系我 13800138000",
        topk_results=[{"phone": "13900139000"}],
        route_id=1,
        db_query_summary="query ok",
        api_params={"contact": "13700137000"},
        api_latency_ms=123,
        final_answer_summary="A" * 520,
        token_usage={"total_tokens": 111},
    )

    logs = await service.get_logs_by_trace_id(trace_id)
    assert len(logs) >= 1

    row = logs[-1]
    assert row.trace_id == trace_id
    assert row.run_id == run_id
    assert row.session_id == session_id
    assert row.search_query is not None and "138****8000" in row.search_query
    assert isinstance(row.topk_results, list) and row.topk_results[0]["phone"] == "139****9000"
    assert isinstance(row.api_params, dict) and row.api_params["contact"] == "137****7000"
    assert row.final_answer_summary is not None and len(row.final_answer_summary) == 500

    print("manual audit check passed")
    print(
        {
            "trace_id": row.trace_id,
            "run_id": row.run_id,
            "masked_search_query": row.search_query,
            "summary_len": len(row.final_answer_summary or ""),
        }
    )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
