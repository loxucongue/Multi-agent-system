"""Prompt loading helpers for runtime prompt version resolution."""

from __future__ import annotations

from sqlalchemy import func, select, update

from app.models.database import PromptVersion
from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)


async def get_active_prompt(node_name: str) -> str | None:
    """Return active prompt content for node_name, or None on miss/failure."""

    try:
        from app.services.container import services

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
                _LOGGER.info(f"prompt seeds ensured created={created} activated={activated}")
    except Exception as exc:
        _LOGGER.warning(f"failed to seed default prompts: {exc}")
