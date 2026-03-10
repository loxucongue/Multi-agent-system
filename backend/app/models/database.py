"""SQLAlchemy ORM models for application persistence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Route(Base):
    """Route master data."""

    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier: Mapped[str] = mapped_column(String(100), nullable=False)
    tags: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    highlights: Mapped[str] = mapped_column(Text, nullable=False)
    base_info: Mapped[str] = mapped_column(Text, nullable=False)
    itinerary_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    notice: Mapped[str] = mapped_column(Text, nullable=False)
    included: Mapped[str] = mapped_column(Text, nullable=False)
    features: Mapped[str | None] = mapped_column(Text, nullable=True, comment="线路特色标签文本")
    cost_excluded: Mapped[str | None] = mapped_column(Text, nullable=True, comment="费用不含说明")
    doc_url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    is_hot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    sort_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    pricing: Mapped[RoutePricing | None] = relationship(back_populates="route", uselist=False)
    schedule: Mapped[RouteSchedule | None] = relationship(back_populates="route", uselist=False)
    leads: Mapped[list[Lead]] = relationship(back_populates="active_route")


class RoutePricing(Base):
    """Route pricing snapshot."""

    __tablename__ = "route_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, unique=True)
    price_min: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    price_max: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CNY", server_default="CNY")
    price_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    route: Mapped[Route] = relationship(back_populates="pricing")


class RouteSchedule(Base):
    """Route schedule snapshot."""

    __tablename__ = "route_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, unique=True)
    schedules_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    schedule_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    route: Mapped[Route] = relationship(back_populates="schedule")


class Session(Base):
    """Conversation session state."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    leads: Mapped[list[Lead]] = relationship(back_populates="session")


class Lead(Base):
    """Captured lead information."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_masked: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    active_route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    user_profile_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new", server_default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    session: Mapped[Session] = relationship(back_populates="leads")
    active_route: Mapped[Route | None] = relationship(back_populates="leads")


class AdminUser(Base):
    """Admin user credential data."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class PromptVersion(Base):
    """Prompt versioning records."""

    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("node_name", "version", name="uq_prompt_versions_node_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_name: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class SystemConfig(Base):
    """System configuration key-value store."""

    __tablename__ = "system_configs"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AuditLog(Base):
    """Audit log records for end-to-end traceability."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(50), nullable=False)
    run_id: Mapped[str] = mapped_column(String(50), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    intent: Mapped[str] = mapped_column(String(50), nullable=False)
    search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    topk_results: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    route_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    db_query_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_params: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    api_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_answer_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    error_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    coze_logid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    coze_debug_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class CozeCallLog(Base):
    """Coze API call logs with request/response details."""

    __tablename__ = "coze_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, default="", server_default="")
    call_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    request_params: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_data: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    coze_logid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    debug_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success", server_default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)
