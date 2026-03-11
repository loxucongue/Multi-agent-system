"""Prompt loading helpers with A/B weighted selection support."""

from __future__ import annotations

import asyncio
import random
import time

from sqlalchemy import func, select, update

from app.models.database import PromptVersion
from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)
_PROMPT_CACHE_TTL_SECONDS = 60.0
_PROMPT_CACHE: dict[str, tuple[float, list[tuple[str, int, int]]]] = {}
_PROMPT_CACHE_LOCK = asyncio.Lock()


async def get_active_prompt(node_name: str) -> str | None:
    """Return active prompt content for node_name via weighted random selection.

    When multiple active prompt versions exist for the same node, selects one
    based on traffic_weight (higher weight = more likely). This enables A/B testing.
    """

    now = time.monotonic()
    cached = _PROMPT_CACHE.get(node_name)
    if cached and cached[0] > now:
        return _weighted_select(cached[1])

    try:
        from app.services.container import services

        await services.initialize()
        async with services.session_factory() as session:
            stmt = (
                select(PromptVersion.content, PromptVersion.traffic_weight, PromptVersion.id)
                .where(
                    PromptVersion.node_name == node_name,
                    PromptVersion.is_active == True,  # noqa: E712
                )
                .order_by(PromptVersion.traffic_weight.desc())
            )
            result = await session.execute(stmt)
            rows = result.all()

        versions: list[tuple[str, int, int]] = []
        for row in rows:
            content, weight, vid = row
            if content and str(content).strip():
                versions.append((str(content), int(weight or 100), int(vid)))

        async with _PROMPT_CACHE_LOCK:
            _PROMPT_CACHE[node_name] = (time.monotonic() + _PROMPT_CACHE_TTL_SECONDS, versions)

        return _weighted_select(versions)
    except Exception as exc:
        _LOGGER.warning(f"failed to load active prompt node={node_name}: {exc}")
        stale = _PROMPT_CACHE.get(node_name)
        if stale:
            return _weighted_select(stale[1])
        return None


def _weighted_select(versions: list[tuple[str, int, int]]) -> str | None:
    """Select one prompt version based on traffic_weight."""
    if not versions:
        return None
    if len(versions) == 1:
        return versions[0][0]
    total = sum(v[1] for v in versions)
    if total <= 0:
        return versions[0][0]
    r = random.randint(1, total)
    cumulative = 0
    for content, weight, _ in versions:
        cumulative += weight
        if r <= cumulative:
            return content
    return versions[0][0]


async def invalidate_prompt_cache(node_name: str | None = None) -> None:
    """Invalidate in-memory prompt cache (one node or all)."""

    async with _PROMPT_CACHE_LOCK:
        if node_name is None:
            _PROMPT_CACHE.clear()
            return
        _PROMPT_CACHE.pop(node_name, None)


async def ensure_prompt_seeds() -> None:
    """Ensure all default prompt nodes exist with an active v1 seed."""

    try:
        from app.services.container import services

        async with services.session_factory() as session:
            created = 0
            activated = 0
            for node_name, content in DEFAULT_PROMPTS.items():
                result = await session.execute(
                    select(
                        func.count(PromptVersion.id),
                        func.max(PromptVersion.version),
                        func.max(PromptVersion.is_active),
                    )
                    .where(PromptVersion.node_name == node_name)
                )
                count, max_version, has_active = result.one()

                if not count:
                    session.add(
                        PromptVersion(
                            node_name=node_name,
                            version=1,
                            content=content,
                            is_active=True,
                        )
                    )
                    created += 1
                    continue

                if has_active:
                    continue

                target_version = int(max_version or 1)
                await session.execute(
                    update(PromptVersion)
                    .where(PromptVersion.node_name == node_name)
                    .values(is_active=False)
                )
                await session.execute(
                    update(PromptVersion)
                    .where(
                        PromptVersion.node_name == node_name,
                        PromptVersion.version == target_version,
                    )
                    .values(is_active=True)
                )
                activated += 1

            if created or activated:
                await session.commit()
                await invalidate_prompt_cache()
                _LOGGER.info(f"prompt seeds ensured created={created} activated={activated}")
    except Exception as exc:
        _LOGGER.warning(f"failed to seed default prompts: {exc}")
