"""Session state management service with MySQL + Redis cache."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.database import Session
from app.models.schemas import SessionState
from app.utils.logger import get_logger

_SESSION_TTL_DAYS = 7
_SESSION_TTL_SECONDS = _SESSION_TTL_DAYS * 24 * 60 * 60


class SessionService:
    """会话状态服务。"""

    def __init__(self, session: AsyncSession, redis: aioredis.Redis | None = None) -> None:
        self._session = session
        self._redis = redis
        self._logger = get_logger(__name__)
        self._context_turns_limit = max(1, settings.SESSION_CONTEXT_TURNS)

    async def create_session(self) -> str:
        """创建新会话并写入 MySQL + Redis。"""

        session_id = str(uuid4())
        state = SessionState()

        row = Session(
            id=session_id,
            state_json=state.model_dump(mode="json"),
            state_version=state.state_version,
            expires_at=datetime.utcnow() + timedelta(days=_SESSION_TTL_DAYS),
        )
        self._session.add(row)

        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        await self._set_cache(session_id, state)
        return session_id

    async def get_session_state(self, session_id: str) -> SessionState | None:
        """读取会话状态。优先 Redis，miss 则回源 MySQL。"""

        cached = await self._get_cache(session_id)
        if cached is not None:
            return cached

        row = await self._get_session_row(session_id)
        if row is None:
            return None

        if self._is_expired(row.expires_at):
            await self._delete_cache(session_id)
            return None

        state = self._row_to_state(row)
        await self._set_cache(session_id, state)
        return state

    async def update_session_state(self, session_id: str, state_patch: dict[str, Any]) -> SessionState:
        """合并更新状态并同步写入 MySQL + Redis（state_version + 1）。"""

        row = await self._get_session_row(session_id)
        if row is None or self._is_expired(row.expires_at):
            raise ValueError(f"session not found or expired: {session_id}")

        current_state = self._row_to_state(row)
        merged = self._deep_merge_dict(current_state.model_dump(mode="python"), state_patch)
        merged["state_version"] = current_state.state_version + 1
        next_state = SessionState.model_validate(merged)

        row.state_json = next_state.model_dump(mode="json")
        row.state_version = next_state.state_version
        row.expires_at = datetime.utcnow() + timedelta(days=_SESSION_TTL_DAYS)

        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        await self._set_cache(session_id, next_state)
        return next_state

    async def append_turn(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        """追加一轮 user+assistant 对话到 context_turns。"""

        row = await self._get_session_row(session_id)
        if row is None or self._is_expired(row.expires_at):
            raise ValueError(f"session not found or expired: {session_id}")

        current = self._row_to_state(row)
        turns = list(current.context_turns)
        turns.append({"user": user_msg, "assistant": assistant_msg})
        await self.update_session_state(session_id, {"context_turns": turns})

    async def get_context_turns(self, session_id: str, n: int) -> list[dict[str, str]]:
        """读取最近 n 轮上下文；实际 n 使用系统配置值。"""

        _ = n  # keep signature compatibility; limit comes from system settings
        state = await self.get_session_state(session_id)
        if state is None:
            return []

        return state.context_turns[-self._context_turns_limit :]

    async def is_session_valid(self, session_id: str) -> bool:
        """检查会话是否存在且未过期。"""

        stmt = select(Session.expires_at).where(Session.id == session_id)
        result = await self._session.execute(stmt)
        expires_at = result.scalar_one_or_none()
        if expires_at is None:
            return False
        return not self._is_expired(expires_at)

    def _cache_key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def _get_cache(self, session_id: str) -> SessionState | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(self._cache_key(session_id))
            if raw is None:
                return None
            return SessionState.model_validate_json(raw)
        except Exception:
            self._logger.debug(f"redis get failed for {self._cache_key(session_id)}")
            return None

    async def _set_cache(self, session_id: str, state: SessionState) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(self._cache_key(session_id), state.model_dump_json(), ex=_SESSION_TTL_SECONDS)
        except Exception:
            self._logger.debug(f"redis set failed for {self._cache_key(session_id)}")

    async def _delete_cache(self, session_id: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(self._cache_key(session_id))
        except Exception:
            self._logger.debug(f"redis delete failed for {self._cache_key(session_id)}")

    async def _get_session_row(self, session_id: str) -> Session | None:
        stmt = select(Session).where(Session.id == session_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def _row_to_state(self, row: Session) -> SessionState:
        payload: dict[str, Any] = dict(row.state_json or {})
        payload["state_version"] = row.state_version
        return SessionState.model_validate(payload)

    def _is_expired(self, expires_at: datetime) -> bool:
        return expires_at <= datetime.utcnow()

    def _deep_merge_dict(self, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            current_value = merged.get(key)
            if isinstance(current_value, dict) and isinstance(value, dict):
                merged[key] = self._deep_merge_dict(current_value, value)
            else:
                merged[key] = value
        return merged
