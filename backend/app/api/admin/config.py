"""Admin system configuration management APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.models.database import SystemConfig
from app.services.container import services
from app.utils.security import get_current_admin

router = APIRouter(dependencies=[Depends(get_current_admin)])


class ConfigUpsertRequest(BaseModel):
    """Request payload for config upsert."""

    value: str
    description: str | None = None


@router.get('/')
async def list_configs() -> list[dict[str, Any]]:
    """List all system config items ordered by key."""

    await services.initialize()
    async with services.session_factory() as session:
        stmt = select(SystemConfig).order_by(SystemConfig.key.asc())
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            'key': row.key,
            'value': row.value,
            'description': row.description,
            'updated_at': row.updated_at.isoformat() if isinstance(row.updated_at, datetime) else str(row.updated_at),
        }
        for row in rows
    ]


@router.put('/{key}')
async def upsert_config(key: str, req: ConfigUpsertRequest) -> dict[str, str]:
    """Create or update one config item by key."""

    await services.initialize()
    stmt = mysql_insert(SystemConfig).values(
        key=key,
        value=req.value,
        description=req.description,
    )
    stmt = stmt.on_duplicate_key_update(
        value=req.value,
        description=req.description,
        updated_at=func.now(),
    )

    async with services.session_factory() as session:
        try:
            await session.execute(stmt)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {'key': key, 'value': req.value}


@router.delete('/{key}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(key: str) -> Response:
    """Delete one config item by key."""

    await services.initialize()
    async with services.session_factory() as session:
        stmt = delete(SystemConfig).where(SystemConfig.key == key)
        result = await session.execute(stmt)
        if int(result.rowcount or 0) == 0:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='config not found')

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return Response(status_code=status.HTTP_204_NO_CONTENT)
