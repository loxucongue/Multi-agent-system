"""Prompt loading helpers for runtime prompt version resolution."""

from __future__ import annotations

from sqlalchemy import select

from app.models.database import PromptVersion
from app.services.container import services
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)


async def get_active_prompt(node_name: str) -> str | None:
    """Return active prompt content for node_name, or None on miss/failure."""

    try:
        await services.initialize()
        async with services.session_factory() as session:
            stmt = (
                select(PromptVersion.content)
                .where(
                    PromptVersion.node_name == node_name,
                    PromptVersion.is_active == True,  # noqa: E712
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    except Exception as exc:
        _LOGGER.warning(f"failed to load active prompt node={node_name}: {exc}")
        return None

