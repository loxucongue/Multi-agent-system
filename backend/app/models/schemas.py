"""Pydantic schemas for Coze services and route data models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────
#  Dataset schemas
# ─────────────────────────────────────────────


class CreateDatasetRequest(BaseModel):
    """POST /v1/datasets – 创建知识库。"""

    name: str  # ≤100 字符
    space_id: str
    format_type: int = 0  # 0=文本, 2=图片
    description: str | None = None


class ListDatasetsRequest(BaseModel):
    """GET /v1/datasets – 查看知识库列表（Query 参数）。"""

    space_id: str
    name: str | None = None
    format_type: int | None = None
    page_num: int = 1
    page_size: int = 10  # 1~300


class UpdateDatasetRequest(BaseModel):
    """PUT /v1/datasets/:dataset_id – 修改知识库（全量刷新）。"""

    dataset_id: str
    name: str
    description: str | None = None
    file_id: str | None = None


class DatasetInfo(BaseModel):
    """知识库列表/详情中返回的单条记录。"""

    dataset_id: str
    name: str | None = None
    status: int | None = None
    doc_count: int | None = None
    model_config = ConfigDict(extra="allow")


# ─────────────────────────────────────────────
#  Document schemas
# ─────────────────────────────────────────────


class DocumentSourceInfo(BaseModel):
    """文档来源信息（Base64 / 网页 / 图片 三选一）。"""

    file_base64: str | None = None
    file_type: str | None = None  # pdf / txt / doc / docx
    document_source: int | None = None  # 0=本地, 1=网页, 5=图片
    web_url: str | None = None
    source_file_id: str | None = None
    update_rule: dict | None = None  # 仅网页文档：自动更新规则
    model_config = ConfigDict(extra="allow")


class DocumentBase(BaseModel):
    """单个待上传文档描述。"""

    name: str
    source_info: DocumentSourceInfo
    model_config = ConfigDict(extra="allow")


class ChunkStrategy(BaseModel):
    """分段策略。"""

    chunk_type: int = 0  # 0=自动, 1=自定义
    separator: str | None = None
    max_tokens: int | None = None  # 100~2000
    remove_extra_spaces: bool | None = None
    remove_urls_emails: bool | None = None
    model_config = ConfigDict(extra="allow")


class CreateDocumentsRequest(BaseModel):
    """POST /open_api/knowledge/document/create – 上传文档。"""

    dataset_id: str
    document_bases: list[DocumentBase]  # 最多 10
    chunk_strategy: ChunkStrategy
    format_type: int = 0


class ListDocumentsRequest(BaseModel):
    """POST /open_api/knowledge/document/list – 查看文档列表。"""

    dataset_id: str
    page: int = 1
    size: int = 10


class UpdateDocumentRequest(BaseModel):
    """POST /open_api/knowledge/document/update – 修改文档。"""

    document_id: str
    document_name: str | None = None
    update_rule: dict | None = None  # 仅网页文档


class DeleteDocumentsRequest(BaseModel):
    """POST /open_api/knowledge/document/delete – 删除文档（最多 100）。"""

    document_ids: list[str]


class GetDocumentProgressRequest(BaseModel):
    """POST /v1/datasets/:dataset_id/process – 查看处理进度。"""

    dataset_id: str
    document_ids: list[str]


class DocumentInfo(BaseModel):
    """文档创建/列表返回的单条信息。"""

    document_id: str
    status: int | None = None
    slice_count: int | None = None
    name: str | None = None
    model_config = ConfigDict(extra="allow")


class ListDocumentsResponse(BaseModel):
    """文档列表响应（含 total）。"""

    document_infos: list[DocumentInfo] = []
    total: int = 0


class DocumentProgress(BaseModel):
    """文档处理进度。"""

    document_id: str | None = None
    status: int | None = None  # 0=处理中, 1=完毕, 9=失败
    progress: int | None = None  # 0~100
    status_descript: str | None = None
    document_name: str | None = None
    model_config = ConfigDict(extra="allow")


# ─────────────────────────────────────────────
#  Workflow schemas
# ─────────────────────────────────────────────


class RouteCandidate(BaseModel):
    """路线检索候选项（来自 WF_ROUTE_SEARCH 工作流输出）。"""

    document_id: str
    output: str  # RAG 原始输出文本（含 basic_info / rag_abstract / file_url_id 等）
    model_config = ConfigDict(extra="allow")


class RouteSearchResult(BaseModel):
    """路线检索工作流结果。"""

    candidates: list[RouteCandidate] = []
    debug_url: str | None = None


class VisaSearchResult(BaseModel):
    """签证检索工作流结果。"""

    answer: str = ""
    sources: list[str] = []  # documentId 列表
    debug_url: str | None = None


class ExternalInfoResult(BaseModel):
    """外部信息检索工作流结果。"""

    info_type: str  # weather / flight / transport
    output: str = ""
    debug_url: str | None = None


# ─────────────────────────────────────────────
#  Session schemas
# ─────────────────────────────────────────────


class SessionState(BaseModel):
    """会话状态 JSON。"""

    stage: str = "init"
    lead_status: str = "none"
    active_route_id: int | None = None
    candidate_route_ids: list[int] = Field(default_factory=list)
    excluded_route_ids: list[int] = Field(default_factory=list)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    last_intent: str | None = None
    followup_count: int = 0
    context_turns: list[dict[str, str]] = Field(default_factory=list)
    state_version: int = 1


# ─────────────────────────────────────────────
#  Lead schemas
# ─────────────────────────────────────────────


class LeadCreate(BaseModel):
    """Lead create request payload."""

    session_id: str
    phone: str


class LeadResponse(BaseModel):
    """Lead submission response payload."""

    success: bool
    message: str
    phone_masked: str


class LeadInfo(BaseModel):
    """Lead detail for user/admin display."""

    id: int
    session_id: str
    phone_masked: str
    source: str
    active_route_id: int | None = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LeadListResponse(BaseModel):
    """Paginated lead list response."""

    leads: list[LeadInfo] = Field(default_factory=list)
    total: int


# ─────────────────────────────────────────────
#  Route schemas
# ─────────────────────────────────────────────


class RouteDetail(BaseModel):
    """routes 表全部字段。"""

    id: int
    name: str
    supplier: str
    tags: list
    summary: str
    highlights: str
    base_info: str
    itinerary_json: Any
    notice: str
    included: str
    doc_url: str
    is_hot: bool
    sort_weight: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PricingInfo(BaseModel):
    """价格快照。"""

    price_min: Decimal
    price_max: Decimal
    currency: str = "CNY"
    price_updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ScheduleInfo(BaseModel):
    """排期快照。"""

    schedules_json: Any
    schedule_updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RoutePriceSchedule(BaseModel):
    """路线价格+排期组合（含 Redis 缓存）。"""

    route_id: int
    pricing: PricingInfo | None = None
    schedule: ScheduleInfo | None = None


class RouteBatchItem(BaseModel):
    """批量查询单条（静态信息+pricing+schedule）。"""

    id: int
    name: str
    supplier: str
    tags: list
    summary: str
    doc_url: str
    is_hot: bool
    sort_weight: int
    pricing: PricingInfo | None = None
    schedule: ScheduleInfo | None = None
    model_config = ConfigDict(from_attributes=True)


class RouteCard(BaseModel):
    """热门路线卡片（精简字段）。"""

    id: int
    name: str
    tags: list
    summary: str
    doc_url: str
    sort_weight: int
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    model_config = ConfigDict(from_attributes=True)
