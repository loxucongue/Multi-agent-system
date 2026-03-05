"""Admin prompt version management APIs."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.models.database import PromptVersion
from app.services.container import services
from app.utils.security import get_current_admin

router = APIRouter()


class PromptContentRequest(BaseModel):
    """Request body for creating a prompt version."""

    content: str = Field(..., min_length=1)


class PromptVersionResponse(BaseModel):
    """Prompt version response payload."""

    node_name: str
    version: int
    content: str
    is_active: bool
    created_at: datetime


@router.get('/', response_model=list[PromptVersionResponse])
async def list_active_prompts(_: str = Depends(get_current_admin)) -> list[PromptVersionResponse]:
    """List active prompt versions for all nodes."""

    await services.initialize()
    async with services.session_factory() as session:
        stmt = (
            select(PromptVersion)
            .where(PromptVersion.is_active == True)  # noqa: E712
            .order_by(PromptVersion.node_name.asc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        PromptVersionResponse(
            node_name=row.node_name,
            version=row.version,
            content=row.content,
            is_active=row.is_active,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get('/{node_name}', response_model=list[PromptVersionResponse])
async def list_prompt_versions(node_name: str, _: str = Depends(get_current_admin)) -> list[PromptVersionResponse]:
    """List all versions for one prompt node."""

    await services.initialize()
    async with services.session_factory() as session:
        stmt = (
            select(PromptVersion)
            .where(PromptVersion.node_name == node_name)
            .order_by(PromptVersion.version.desc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='prompt not found')

    return [
        PromptVersionResponse(
            node_name=row.node_name,
            version=row.version,
            content=row.content,
            is_active=row.is_active,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post('/{node_name}', response_model=PromptVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt_version(
    node_name: str,
    req: PromptContentRequest,
    _: str = Depends(get_current_admin),
) -> PromptVersionResponse:
    """Create a new inactive prompt version for a node."""

    await services.initialize()
    async with services.session_factory() as session:
        max_stmt = select(func.max(PromptVersion.version)).where(PromptVersion.node_name == node_name)
        max_result = await session.execute(max_stmt)
        current_max = max_result.scalar_one_or_none()
        new_version = (int(current_max) if current_max is not None else 0) + 1

        row = PromptVersion(
            node_name=node_name,
            version=new_version,
            content=req.content,
            is_active=False,
        )
        session.add(row)

        try:
            await session.commit()
            await session.refresh(row)
        except Exception:
            await session.rollback()
            raise

    return PromptVersionResponse(
        node_name=row.node_name,
        version=row.version,
        content=row.content,
        is_active=row.is_active,
        created_at=row.created_at,
    )


@router.put('/{node_name}/{version}/activate')
async def activate_prompt_version(
    node_name: str,
    version: int,
    _: str = Depends(get_current_admin),
) -> dict[str, str]:
    """Activate one prompt version and deactivate others in the same node."""

    await services.initialize()
    async with services.session_factory() as session:
        target_stmt = select(PromptVersion).where(
            PromptVersion.node_name == node_name,
            PromptVersion.version == version,
        )
        target_result = await session.execute(target_stmt)
        target = target_result.scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='prompt version not found')

        try:
            await session.execute(
                update(PromptVersion)
                .where(PromptVersion.node_name == node_name)
                .values(is_active=False)
            )
            await session.execute(
                update(PromptVersion)
                .where(PromptVersion.node_name == node_name, PromptVersion.version == version)
                .values(is_active=True)
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {'message': 'activated'}
