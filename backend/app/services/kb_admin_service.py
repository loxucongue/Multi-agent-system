"""Knowledge-base administration service wrapping Coze Dataset & Document APIs."""

from __future__ import annotations

from typing import Any

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
from app.services.coze_client import CozeClient
from app.utils.logger import get_logger


class KBAdminService:
    """知识库管理服务，封装 Coze Dataset & Document API。

    所有修改/查询均代理至 ``CozeClient._request``，错误处理由其统一负责。
    Document 系列接口自动附带 ``Agw-Js-Conv: str`` header。
    """

    _DOC_HEADERS: dict[str, str] = {"Agw-Js-Conv": "str"}

    def __init__(self, client: CozeClient) -> None:
        self._client = client
        self._logger = get_logger(__name__)

    # ─────────────────────────────────────────────
    #  Dataset 管理
    # ─────────────────────────────────────────────

    async def create_dataset(self, req: CreateDatasetRequest) -> str:
        """创建知识库，返回 dataset_id。

        POST /v1/datasets
        """

        body: dict[str, Any] = {
            "name": req.name,
            "space_id": req.space_id,
            "format_type": req.format_type,
        }
        if req.description is not None:
            body["description"] = req.description

        payload = await self._client._request("POST", "/v1/datasets", body)
        data = payload.get("data", {})
        dataset_id: str = str(data.get("dataset_id", ""))
        self._logger.info(f"created dataset {dataset_id}")
        return dataset_id

    async def list_datasets(self, req: ListDatasetsRequest) -> list[DatasetInfo]:
        """查看知识库列表。

        GET /v1/datasets
        """

        params: dict[str, Any] = {
            "space_id": req.space_id,
            "page_num": req.page_num,
            "page_size": req.page_size,
        }
        if req.name is not None:
            params["name"] = req.name
        if req.format_type is not None:
            params["format_type"] = req.format_type

        payload = await self._client._request("GET", "/v1/datasets", params=params)
        data = payload.get("data", {})
        dataset_list: list[dict[str, Any]] = data.get("dataset_list", [])
        return [DatasetInfo.model_validate(d) for d in dataset_list]

    async def update_dataset(self, req: UpdateDatasetRequest) -> bool:
        """修改知识库信息（全量刷新，未传字段会恢复默认）。

        PUT /v1/datasets/:dataset_id
        """

        body: dict[str, Any] = {"name": req.name}
        if req.description is not None:
            body["description"] = req.description
        if req.file_id is not None:
            body["file_id"] = req.file_id

        await self._client._request("PUT", f"/v1/datasets/{req.dataset_id}", body)
        self._logger.info(f"updated dataset {req.dataset_id}")
        return True

    async def delete_dataset(self, dataset_id: str) -> bool:
        """删除知识库（同时删除库内所有文件并解绑智能体）。

        DELETE /v1/datasets/:dataset_id
        """

        await self._client._request("DELETE", f"/v1/datasets/{dataset_id}")
        self._logger.info(f"deleted dataset {dataset_id}")
        return True

    # ─────────────────────────────────────────────
    #  Document 管理
    # ─────────────────────────────────────────────

    async def create_documents(self, req: CreateDocumentsRequest) -> list[DocumentInfo]:
        """上传知识库文件（最多 10 个），返回 document_infos。

        POST /open_api/knowledge/document/create
        """

        body: dict[str, Any] = {
            "dataset_id": req.dataset_id,
            "document_bases": [db.model_dump(exclude_none=True) for db in req.document_bases],
            "chunk_strategy": req.chunk_strategy.model_dump(exclude_none=True),
            "format_type": req.format_type,
        }

        payload = await self._client._request(
            "POST",
            "/open_api/knowledge/document/create",
            body,
            extra_headers=self._DOC_HEADERS,
        )
        infos: list[dict[str, Any]] = payload.get("document_infos", [])
        self._logger.info(f"created {len(infos)} documents in dataset {req.dataset_id}")
        return [DocumentInfo.model_validate(i) for i in infos]

    async def list_documents(self, req: ListDocumentsRequest) -> ListDocumentsResponse:
        """查看知识库文件列表。

        POST /open_api/knowledge/document/list
        """

        body: dict[str, Any] = {
            "dataset_id": req.dataset_id,
            "page": req.page,
            "size": req.size,
        }

        payload = await self._client._request(
            "POST",
            "/open_api/knowledge/document/list",
            body,
            extra_headers=self._DOC_HEADERS,
        )
        data = payload.get("data", payload)
        return ListDocumentsResponse(
            document_infos=[DocumentInfo.model_validate(d) for d in data.get("document_infos", [])],
            total=int(data.get("total", 0)),
        )

    async def get_document_progress(self, req: GetDocumentProgressRequest) -> list[DocumentProgress]:
        """查看文件上传/处理进度。

        POST /v1/datasets/:dataset_id/process
        """

        body: dict[str, Any] = {"document_ids": req.document_ids}

        payload = await self._client._request(
            "POST",
            f"/v1/datasets/{req.dataset_id}/process",
            body,
            extra_headers=self._DOC_HEADERS,
        )
        data = payload.get("data", {})
        items: list[dict[str, Any]] = data.get("data", []) if isinstance(data, dict) else []
        return [DocumentProgress.model_validate(p) for p in items]

    async def update_document(self, req: UpdateDocumentRequest) -> bool:
        """修改知识库文件信息。

        POST /open_api/knowledge/document/update
        """

        body: dict[str, Any] = {"document_id": req.document_id}
        if req.document_name is not None:
            body["document_name"] = req.document_name
        if req.update_rule is not None:
            body["update_rule"] = req.update_rule

        await self._client._request(
            "POST",
            "/open_api/knowledge/document/update",
            body,
            extra_headers=self._DOC_HEADERS,
        )
        self._logger.info(f"updated document {req.document_id}")
        return True

    async def delete_documents(self, req: DeleteDocumentsRequest) -> bool:
        """删除知识库文件（最多 100 个）。

        POST /open_api/knowledge/document/delete
        """

        body: dict[str, Any] = {"document_ids": req.document_ids}

        await self._client._request(
            "POST",
            "/open_api/knowledge/document/delete",
            body,
            extra_headers=self._DOC_HEADERS,
        )
        self._logger.info(f"deleted {len(req.document_ids)} documents")
        return True
