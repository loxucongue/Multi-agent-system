"""Admin knowledge-base proxy APIs for Coze dataset/document operations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config.settings import settings
from app.models.schemas import (
    ChunkStrategy,
    CreateDatasetRequest,
    CreateDocumentsRequest,
    DatasetInfo,
    DeleteDocumentsRequest,
    DocumentBase,
    DocumentInfo,
    DocumentProgress,
    GetDocumentProgressRequest,
    ListDatasetsRequest,
    ListDocumentsRequest,
    ListDocumentsResponse,
    UpdateDatasetRequest,
    UpdateDocumentRequest,
)
from app.services.container import services
from app.utils.security import get_current_admin

router = APIRouter(dependencies=[Depends(get_current_admin)])


class CreateDatasetBody(BaseModel):
    """Request payload for creating dataset under configured space."""

    name: str
    format_type: int = 0
    description: str | None = None


class UpdateDatasetBody(BaseModel):
    """Request payload for updating dataset metadata."""

    name: str
    description: str | None = None
    file_id: str | None = None


class CreateDocumentsBody(BaseModel):
    """Request payload for creating knowledge documents."""

    document_bases: list[DocumentBase]
    chunk_strategy: ChunkStrategy
    format_type: int = 0


class UpdateDocumentBody(BaseModel):
    """Request payload for updating one document."""

    document_name: str | None = None
    update_rule: dict[str, Any] | None = None


class DocumentProgressBody(BaseModel):
    """Request payload for document process query."""

    document_ids: list[str]


def _kb_error(exc: Exception) -> JSONResponse:
    """Build a unified knowledge-base upstream error response."""

    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "knowledge base service error", "message": str(exc)},
    )


@router.get('/datasets', response_model=list[DatasetInfo])
async def list_datasets(
    name: str | None = Query(default=None),
    format_type: int | None = Query(default=None),
    page_num: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=300),
) -> Any:
    """List datasets under configured Coze space."""

    await services.initialize()
    req = ListDatasetsRequest(
        space_id=settings.COZE_SPACE_ID,
        name=name,
        format_type=format_type,
        page_num=page_num,
        page_size=page_size,
    )
    try:
        return await services.kb_admin_service.list_datasets(req)
    except HTTPException:
        raise
    except Exception as exc:
        return _kb_error(exc)


@router.post('/datasets')
async def create_dataset(req: CreateDatasetBody) -> Any:
    """Create a dataset in configured Coze space."""

    await services.initialize()
    create_req = CreateDatasetRequest(
        name=req.name,
        space_id=settings.COZE_SPACE_ID,
        format_type=req.format_type,
        description=req.description,
    )
    try:
        dataset_id = await services.kb_admin_service.create_dataset(create_req)
        return {'dataset_id': dataset_id}
    except HTTPException:
        raise
    except Exception as exc:
        return _kb_error(exc)


@router.put('/datasets/{dataset_id}')
async def update_dataset(dataset_id: str, req: UpdateDatasetBody) -> Any:
    """Update dataset metadata."""

    await services.initialize()
    update_req = UpdateDatasetRequest(
        dataset_id=dataset_id,
        name=req.name,
        description=req.description,
        file_id=req.file_id,
    )
    try:
        await services.kb_admin_service.update_dataset(update_req)
        return {'success': True}
    except HTTPException:
        raise
    except Exception as exc:
        return _kb_error(exc)


@router.delete('/datasets/{dataset_id}')
async def delete_dataset(dataset_id: str) -> Any:
    """Delete one dataset."""

    await services.initialize()
    try:
        await services.kb_admin_service.delete_dataset(dataset_id)
        return {'success': True}
    except HTTPException:
        raise
    except Exception as exc:
        return _kb_error(exc)


@router.post('/datasets/{dataset_id}/documents', response_model=list[DocumentInfo])
async def create_documents(dataset_id: str, req: CreateDocumentsBody) -> Any:
    """Create documents under one dataset."""

    await services.initialize()
    create_req = CreateDocumentsRequest(
        dataset_id=dataset_id,
        document_bases=req.document_bases,
        chunk_strategy=req.chunk_strategy,
        format_type=req.format_type,
    )
    try:
        return await services.kb_admin_service.create_documents(create_req)
    except HTTPException:
        raise
    except Exception as exc:
        return _kb_error(exc)


@router.get('/datasets/{dataset_id}/documents', response_model=ListDocumentsResponse)
async def list_documents(
    dataset_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1),
) -> Any:
    """List documents in dataset with pagination."""

    await services.initialize()
    list_req = ListDocumentsRequest(dataset_id=dataset_id, page=page, size=size)
    try:
        return await services.kb_admin_service.list_documents(list_req)
    except HTTPException:
        raise
    except Exception as exc:
        return _kb_error(exc)


@router.put('/documents/{document_id}')
async def update_document(document_id: str, req: UpdateDocumentBody) -> Any:
    """Update one knowledge document."""

    await services.initialize()
    update_req = UpdateDocumentRequest(
        document_id=document_id,
        document_name=req.document_name,
        update_rule=req.update_rule,
    )
    try:
        await services.kb_admin_service.update_document(update_req)
        return {'success': True}
    except HTTPException:
        raise
    except Exception as exc:
        return _kb_error(exc)


@router.delete('/documents')
async def delete_documents(req: DeleteDocumentsRequest) -> Any:
    """Delete multiple knowledge documents."""

    await services.initialize()
    try:
        await services.kb_admin_service.delete_documents(req)
        return {'success': True}
    except HTTPException:
        raise
    except Exception as exc:
        return _kb_error(exc)


@router.post('/datasets/{dataset_id}/progress', response_model=list[DocumentProgress])
async def get_document_progress(
    dataset_id: str,
    req: DocumentProgressBody,
) -> Any:
    """Query processing progress for dataset documents."""

    await services.initialize()
    progress_req = GetDocumentProgressRequest(dataset_id=dataset_id, document_ids=req.document_ids)
    try:
        return await services.kb_admin_service.get_document_progress(progress_req)
    except HTTPException:
        raise
    except Exception as exc:
        return _kb_error(exc)
