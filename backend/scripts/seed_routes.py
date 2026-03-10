"""Import route data from Excel/CSV into routes and route_pricing tables.

Usage:
    python -m scripts.seed_routes --file /path/to/routes.xlsx
"""

from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import async_session_factory
from app.models.database import Route, RoutePricing


_DEFAULT_SUPPLIER = "未知供应商"
_DEFAULT_TEXT = ""
_PRICE_ZERO = Decimal("0")

_REQUIRED_COLUMNS = [
    "file_name",
    "file_url",
    "suppliers",
    "tour_period",
    "price",
    "features",
    "basic_info",
    "highlights",
    "itinerary_days",
    "cost_included",
    "notices",
    "rag_abstract",
    "cost_excluded",
]


@dataclass(slots=True)
class ImportStats:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))  # handles NaN/NaT
    except Exception:
        return False


def _as_text(value: Any, default: str = _DEFAULT_TEXT) -> str:
    if _is_empty(value):
        return default
    text = str(value).strip()
    return text or default


def _to_tags(rag_abstract: Any) -> list[str]:
    text = _as_text(rag_abstract)
    if not text:
        return []
    parts = re.split(r"[，,、|\s]+", text)
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        token = part.strip()
        if not token:
            continue
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _to_itinerary_json(itinerary_days: Any) -> list[dict[str, Any]]:
    text = _as_text(itinerary_days)
    if not text:
        return [{"day": 1, "content": "暂无行程信息"}]

    marker_pattern = re.compile(r"(第\s*(\d+)\s*天|Day\s*(\d+))", re.IGNORECASE)
    matches = list(marker_pattern.finditer(text))
    if not matches:
        return [{"day": 1, "content": text}]

    segments: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        day_num: int | None = None
        if match.group(2):
            day_num = int(match.group(2))
        elif match.group(3):
            day_num = int(match.group(3))
        segments.append(
            {
                "day": day_num if day_num is not None else idx + 1,
                "content": content or f"第{idx + 1}天",
            }
        )

    return segments or [{"day": 1, "content": text}]


def _to_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return _PRICE_ZERO


def _parse_price(price_value: Any) -> tuple[Decimal, Decimal]:
    if _is_empty(price_value):
        return _PRICE_ZERO, _PRICE_ZERO

    if isinstance(price_value, (int, float, Decimal)):
        raw = str(price_value)
        parsed = _to_decimal(raw)
        return parsed, parsed

    text = _as_text(price_value)
    if not text:
        return _PRICE_ZERO, _PRICE_ZERO

    compact = text.replace(",", "").replace("，", "")
    numbers = re.findall(r"\d+(?:\.\d+)?", compact)
    if not numbers:
        return _PRICE_ZERO, _PRICE_ZERO

    has_range = bool(re.search(r"[-~—–至到]", compact)) and len(numbers) >= 2
    if has_range:
        low = _to_decimal(numbers[0])
        high = _to_decimal(numbers[1])
        if low > high:
            low, high = high, low
        return low, high

    value = _to_decimal(numbers[0])
    return value, value


def _read_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
    elif suffix == ".csv":
        frame = pd.read_csv(path)
    else:
        raise ValueError(f"unsupported file type: {suffix}")
    return frame.where(pd.notna(frame), None)


def _check_required_columns(frame: pd.DataFrame) -> None:
    missing = [col for col in _REQUIRED_COLUMNS if col not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")


async def _load_existing_routes(session: AsyncSession, doc_urls: list[str]) -> dict[str, Route]:
    if not doc_urls:
        return {}

    stmt = select(Route).where(Route.doc_url.in_(doc_urls))
    result = await session.execute(stmt)
    rows = result.scalars().all()

    mapping: dict[str, Route] = {}
    for route in rows:
        mapping[str(route.doc_url)] = route
    return mapping


async def _load_existing_pricing(session: AsyncSession, route_ids: list[int]) -> dict[int, RoutePricing]:
    if not route_ids:
        return {}

    stmt = select(RoutePricing).where(RoutePricing.route_id.in_(route_ids))
    result = await session.execute(stmt)
    rows = result.scalars().all()

    mapping: dict[int, RoutePricing] = {}
    for pricing in rows:
        mapping[int(pricing.route_id)] = pricing
    return mapping


async def import_routes(file_path: Path) -> ImportStats:
    frame = _read_file(file_path)
    _check_required_columns(frame)

    stats = ImportStats()

    doc_urls = [_as_text(v) for v in frame["file_url"].tolist() if _as_text(v)]

    async with async_session_factory() as session:
        route_by_doc_url = await _load_existing_routes(session, doc_urls)
        pricing_by_route_id = await _load_existing_pricing(
            session,
            [int(route.id) for route in route_by_doc_url.values()],
        )

        for row_idx, row in frame.iterrows():
            line_no = int(row_idx) + 2  # Excel row number with header
            try:
                file_url = _as_text(row.get("file_url"))
                if not file_url:
                    stats.skipped += 1
                    continue

                name = _as_text(row.get("file_name"), default=file_url)
                supplier = _as_text(row.get("suppliers"), default=_DEFAULT_SUPPLIER)
                base_info = _as_text(row.get("tour_period"))
                summary = _as_text(row.get("basic_info"))
                highlights = _as_text(row.get("highlights"))
                itinerary_json = _to_itinerary_json(row.get("itinerary_days"))
                included = _as_text(row.get("cost_included"))
                notice = _as_text(row.get("notices"))
                tags = _to_tags(row.get("rag_abstract"))
                features = _as_text(row.get("features")) or None
                cost_excluded = _as_text(row.get("cost_excluded")) or None
                price_min, price_max = _parse_price(row.get("price"))

                async with session.begin_nested():
                    route = route_by_doc_url.get(file_url)
                    if route is None:
                        route = Route(
                            name=name,
                            supplier=supplier,
                            tags=tags,
                            summary=summary,
                            highlights=highlights,
                            base_info=base_info,
                            itinerary_json=itinerary_json,
                            notice=notice,
                            included=included,
                            features=features,
                            cost_excluded=cost_excluded,
                            doc_url=file_url,
                            is_hot=False,
                            sort_weight=0,
                        )
                        session.add(route)
                        await session.flush()
                        route_by_doc_url[file_url] = route
                        stats.created += 1
                    else:
                        route.name = name
                        route.supplier = supplier
                        route.tags = tags
                        route.summary = summary
                        route.highlights = highlights
                        route.base_info = base_info
                        route.itinerary_json = itinerary_json
                        route.notice = notice
                        route.included = included
                        route.features = features
                        route.cost_excluded = cost_excluded
                        stats.updated += 1

                    route_id = int(route.id)
                    pricing = pricing_by_route_id.get(route_id)
                    if pricing is None:
                        pricing = RoutePricing(
                            route_id=route_id,
                            price_min=price_min,
                            price_max=price_max,
                            currency="CNY",
                        )
                        session.add(pricing)
                        await session.flush()
                        pricing_by_route_id[route_id] = pricing
                    else:
                        pricing.price_min = price_min
                        pricing.price_max = price_max
                        pricing.currency = "CNY"

            except Exception as exc:
                stats.errors.append(f"row={line_no} error={exc}")
                continue

        await session.commit()

    return stats


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed routes from Excel/CSV.")
    parser.add_argument("--file", required=True, help="Path to .xlsx/.xls/.csv route source file")
    return parser


async def _main_async(file_path: Path) -> int:
    stats = await import_routes(file_path)
    print(f"created: {stats.created}")
    print(f"updated: {stats.updated}")
    print(f"skipped: {stats.skipped}")
    print(f"errors: {stats.errors or []}")
    return 0 if not stats.errors else 1


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.exists():
        print(f"file not found: {file_path}")
        return 2

    try:
        return asyncio.run(_main_async(file_path))
    except Exception as exc:
        print(f"fatal error: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
