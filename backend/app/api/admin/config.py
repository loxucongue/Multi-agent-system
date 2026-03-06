"""Admin system configuration management APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select

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
    await services.config_service.set_value(key=key, value=req.value, description=req.description)
    return {'key': key, 'value': req.value}


@router.delete('/{key}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(key: str) -> Response:
    """Delete one config item by key."""

    await services.initialize()
    deleted = await services.config_service.delete_key(key)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='config not found')

    return Response(status_code=status.HTTP_204_NO_CONTENT)
