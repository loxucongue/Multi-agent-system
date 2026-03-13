"""One-off script to reparse all routes through existing admin APIs.

The script submits small batches to `/admin/routes/reparse` and waits until the
current batch finishes before sending the next one. This keeps in-flight parse
jobs bounded and avoids overwhelming the Coze workflow concurrency limit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from typing import Any

import httpx

DEFAULT_API_BASE = "http://127.0.0.1:8000"
DEFAULT_BATCH_SIZE = 5
DEFAULT_PAGE_SIZE = 100
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_WAIT_TIMEOUT = 1800.0
DEFAULT_STATUS_RETRIES = 3
DEFAULT_STATUS_RETRY_DELAY = 2.0
TERMINAL_STATUSES = {"done", "failed"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Submit all routes for reparse in bounded batches.")
    parser.add_argument("--api-base", default=os.getenv("REPARSE_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--username", default=os.getenv("REPARSE_ADMIN_USERNAME"))
    parser.add_argument("--password", default=os.getenv("REPARSE_ADMIN_PASSWORD"))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL)
    parser.add_argument("--wait-timeout", type=float, default=DEFAULT_WAIT_TIMEOUT)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--status-retries", type=int, default=DEFAULT_STATUS_RETRIES)
    parser.add_argument("--status-retry-delay", type=float, default=DEFAULT_STATUS_RETRY_DELAY)
    parser.add_argument(
        "--route-ids",
        default="",
        help="Comma-separated route ids to reparse instead of fetching all routes.",
    )
    parser.add_argument(
        "--failed-from-result-json",
        default="",
        help="Read failed route ids from a previous result json file.",
    )
    parser.add_argument("--result-json", default="")
    return parser


async def login(client: httpx.AsyncClient, api_base: str, username: str, password: str) -> str:
    response = await client.post(
        f"{api_base}/admin/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("login succeeded but access_token was missing")
    return token


async def fetch_all_route_ids(
    client: httpx.AsyncClient,
    api_base: str,
    headers: dict[str, str],
    page_size: int,
) -> list[int]:
    route_ids: list[int] = []
    page = 1
    total = None

    while True:
        response = await client.get(
            f"{api_base}/admin/routes/",
            params={"page": page, "page_size": page_size},
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()

        route_ids.extend(int(item["id"]) for item in payload.get("routes", []))
        total = int(payload.get("total", len(route_ids)))

        if len(route_ids) >= total or not payload.get("routes"):
            break
        page += 1

    return route_ids


def parse_route_ids_arg(raw_value: str) -> list[int]:
    if not raw_value.strip():
        return []
    route_ids: list[int] = []
    for chunk in raw_value.split(","):
        item = chunk.strip()
        if not item:
            continue
        route_ids.append(int(item))
    return route_ids


def load_failed_route_ids(result_json_path: str) -> list[int]:
    with open(result_json_path, "r", encoding="utf-8") as fp:
        payload = json.load(fp)

    failed_routes = payload.get("failed_routes", [])
    if not isinstance(failed_routes, list):
        raise RuntimeError(f"invalid failed_routes in result json: {result_json_path}")

    route_ids: list[int] = []
    for item in failed_routes:
        if not isinstance(item, dict) or "route_id" not in item:
            continue
        route_ids.append(int(item["route_id"]))
    return route_ids


def unique_route_ids(route_ids: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for route_id in route_ids:
        if route_id in seen:
            continue
        seen.add(route_id)
        result.append(route_id)
    return result


async def trigger_reparse_batch(
    client: httpx.AsyncClient,
    api_base: str,
    headers: dict[str, str],
    route_ids: list[int],
) -> tuple[list[int], list[dict[str, Any]]]:
    response = await client.post(
        f"{api_base}/admin/routes/reparse",
        json={"route_ids": route_ids},
        headers=headers,
    )
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("accepted", [])), list(payload.get("skipped", []))


async def fetch_parse_status(
    client: httpx.AsyncClient,
    api_base: str,
    headers: dict[str, str],
    route_id: int,
    status_retries: int,
    status_retry_delay: float,
) -> dict[str, Any]:
    attempts = max(status_retries, 1)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(
                f"{api_base}/admin/routes/{route_id}/parse-status",
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"unexpected parse-status payload for route {route_id}: {payload!r}")
            return payload
        except (httpx.HTTPError, RuntimeError) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            await asyncio.sleep(status_retry_delay)

    raise RuntimeError(f"failed to fetch parse-status for route {route_id}: {last_error}") from last_error


def build_summary(
    done_route_ids: list[int],
    failed_routes: list[dict[str, Any]],
    skipped_routes: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "done_count": len(done_route_ids),
        "failed_count": len(failed_routes),
        "skipped_count": len(skipped_routes),
        "done_route_ids": done_route_ids,
        "failed_routes": failed_routes,
        "skipped_routes": skipped_routes,
    }


def write_summary(path: str, summary: dict[str, Any]) -> None:
    if not path:
        return
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2)


async def wait_for_batch(
    client: httpx.AsyncClient,
    api_base: str,
    headers: dict[str, str],
    accepted_ids: list[int],
    poll_interval: float,
    wait_timeout: float,
    status_retries: int,
    status_retry_delay: float,
) -> list[dict[str, Any]]:
    statuses: dict[int, dict[str, Any]] = {}
    start = asyncio.get_running_loop().time()

    while True:
        results = await asyncio.gather(
            *[
                fetch_parse_status(
                    client,
                    api_base,
                    headers,
                    route_id,
                    status_retries,
                    status_retry_delay,
                )
                for route_id in accepted_ids
            ]
        )
        statuses = {route_id: payload for route_id, payload in zip(accepted_ids, results, strict=True)}

        if all(statuses[route_id].get("status") in TERMINAL_STATUSES for route_id in accepted_ids):
            break

        elapsed = asyncio.get_running_loop().time() - start
        if elapsed >= wait_timeout:
            raise TimeoutError(
                f"timed out waiting for batch after {wait_timeout:.0f}s: "
                f"{ {route_id: statuses[route_id].get('status') for route_id in accepted_ids} }"
            )

        counter = Counter(str(statuses[route_id].get("status", "unknown")) for route_id in accepted_ids)
        print(f"  waiting... {dict(counter)}")
        await asyncio.sleep(poll_interval)

    return [statuses[route_id] for route_id in accepted_ids]


async def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.username or not args.password:
        parser.error("username and password are required, pass via args or REPARSE_ADMIN_* env vars")

    if args.batch_size < 1:
        parser.error("batch-size must be >= 1")
    if args.page_size < 1:
        parser.error("page-size must be >= 1")
    if args.poll_interval <= 0:
        parser.error("poll-interval must be > 0")
    if args.wait_timeout <= 0:
        parser.error("wait-timeout must be > 0")
    if args.status_retries < 1:
        parser.error("status-retries must be >= 1")
    if args.status_retry_delay <= 0:
        parser.error("status-retry-delay must be > 0")

    api_base = args.api_base.rstrip("/")

    async with httpx.AsyncClient(timeout=args.request_timeout, trust_env=False) as client:
        token = await login(client, api_base, args.username, args.password)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        route_ids = parse_route_ids_arg(args.route_ids)
        if args.failed_from_result_json:
            route_ids.extend(load_failed_route_ids(args.failed_from_result_json))
        route_ids = unique_route_ids(route_ids)
        if not route_ids:
            route_ids = await fetch_all_route_ids(client, api_base, headers, args.page_size)
        if not route_ids:
            print("no routes found")
            return 0

        print(
            f"found {len(route_ids)} routes; submitting in batches of {args.batch_size}. "
            "Each batch waits for parse completion before continuing."
        )

        done_route_ids: list[int] = []
        failed_routes: list[dict[str, Any]] = []
        overall_skipped: list[dict[str, Any]] = []

        for index in range(0, len(route_ids), args.batch_size):
            batch = route_ids[index : index + args.batch_size]
            batch_no = index // args.batch_size + 1
            print(f"batch {batch_no}: submitting route_ids={batch}")

            accepted, skipped = await trigger_reparse_batch(client, api_base, headers, batch)
            overall_skipped.extend(skipped)
            print(f"  accepted={accepted}")
            if skipped:
                print(f"  skipped={skipped}")

            if not accepted:
                continue

            results = await wait_for_batch(
                client,
                api_base,
                headers,
                accepted,
                args.poll_interval,
                args.wait_timeout,
                args.status_retries,
                args.status_retry_delay,
            )
            counter = Counter(str(item.get("status", "unknown")) for item in results)
            for item in results:
                route_id = int(item.get("route_id"))
                status = str(item.get("status", "unknown"))
                message = str(item.get("message", ""))
                if status == "done":
                    done_route_ids.append(route_id)
                elif status == "failed":
                    failed_routes.append(
                        {
                            "route_id": route_id,
                            "reason": message or "unknown error",
                        }
                    )
            print(f"  finished={dict(counter)}")
            write_summary(
                args.result_json,
                build_summary(done_route_ids, failed_routes, overall_skipped),
            )

        summary = build_summary(done_route_ids, failed_routes, overall_skipped)

        print(
            "all batches complete: "
            f"done={summary['done_count']}, failed={summary['failed_count']}, skipped={summary['skipped_count']}"
        )
        if overall_skipped:
            print(f"skipped details={overall_skipped}")
        if failed_routes:
            print(f"failed details={failed_routes}")
        print(f"summary_json={json.dumps(summary, ensure_ascii=False)}")

        if args.result_json:
            write_summary(args.result_json, summary)
            print(f"result written to {args.result_json}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("cancelled by user", file=sys.stderr)
        raise SystemExit(130)
