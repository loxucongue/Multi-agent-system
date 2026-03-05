"""Manual smoke test for graph streaming events written to Redis."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.database import engine
from app.config.redis import redis_client
from app.graph.graph import run_graph_streaming
from app.services.container import services
from app.utils.helpers import generate_run_id, generate_trace_id


async def main() -> None:
    await services.initialize()

    session_id = await services.session_service.create_session()
    run_id = generate_run_id()
    trace_id = generate_trace_id()

    await run_graph_streaming(
        session_id=session_id,
        user_message="我想去日本玩6天",
        run_id=run_id,
        trace_id=trace_id,
        redis_client=redis_client,
    )

    events_key = f"events:{run_id}"
    done_key = f"done:{run_id}"

    events = await redis_client.lrange(events_key, 0, -1)
    print(f"run_id={run_id}")
    print(f"events_count={len(events)}")
    if events:
        last_raw = events[-1].decode("utf-8") if isinstance(events[-1], bytes) else str(events[-1])
        print(f"last_event={last_raw}")
        parsed = json.loads(last_raw)
        assert parsed.get("event") == "done", "last event must be done"

    done = await redis_client.get(done_key)
    done_val = done.decode("utf-8") if isinstance(done, bytes) else str(done)
    print(f"done_flag={done_val}")

    assert len(events) >= 1, "events list should have at least one event"
    assert done_val == "1", "done flag should be 1"

    await redis_client.aclose()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
