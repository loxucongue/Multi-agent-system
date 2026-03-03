"""Coze workflow execution service for online retrieval (route / visa / external info)."""

from __future__ import annotations

import json
from typing import Any

from app.config.settings import Settings
from app.models.schemas import (
    ExternalInfoResult,
    RouteCandidate,
    RouteSearchResult,
    VisaSearchResult,
)
from app.services.coze_client import CozeClient, CozeClientError
from app.utils.logger import get_logger


class WorkflowService:
    """Coze 工作流执行服务。

    通过 ``POST /v1/workflow/run`` 调用三类工作流，提供线上检索能力。
    """

    _WORKFLOW_ENDPOINT = "/v1/workflow/run"

    def __init__(self, client: CozeClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._logger = get_logger(__name__)

    # ─────────────────────────────────────────────
    #  Public methods
    # ─────────────────────────────────────────────

    async def run_route_search(self, query: str, trace_id: str) -> RouteSearchResult:
        """调用 WF_ROUTE_SEARCH 工作流，返回路线候选列表。

        Parameters 约定入参名为 ``"input"``（COZE.md 0.3 节）。
        """

        payload = await self._run_workflow(
            workflow_id=self._settings.COZE_WF_ROUTE_SEARCH_ID,
            parameters={"input": query},
            trace_id=trace_id,
        )

        debug_url = payload.get("debug_url")
        candidates = self._parse_route_candidates(payload)

        return RouteSearchResult(candidates=candidates, debug_url=debug_url)

    async def run_visa_search(self, query: str, trace_id: str) -> VisaSearchResult:
        """调用 WF_VISA_SEARCH 工作流，返回签证搜索结果。

        Parameters 约定入参名为 ``"input"``（COZE.md 0.3 节）。
        """

        payload = await self._run_workflow(
            workflow_id=self._settings.COZE_WF_VISA_SEARCH_ID,
            parameters={"input": query},
            trace_id=trace_id,
        )

        debug_url = payload.get("debug_url")
        answer, sources = self._parse_visa_result(payload)

        return VisaSearchResult(answer=answer, sources=sources, debug_url=debug_url)

    async def run_external_info(
        self, info_type: str, params: dict, trace_id: str
    ) -> ExternalInfoResult:
        """调用 WF_EXTERNAL_INFO 工作流，获取外部信息（天气/航班/交通）。

        info_type ∈ {"weather", "flight", "transport"}
        """

        parameters: dict[str, Any] = {"type": info_type, **params}

        payload = await self._run_workflow(
            workflow_id=self._settings.COZE_WF_EXTERNAL_INFO_ID,
            parameters=parameters,
            trace_id=trace_id,
        )

        debug_url = payload.get("debug_url")
        output = self._parse_external_output(payload)

        return ExternalInfoResult(info_type=info_type, output=output, debug_url=debug_url)

    # ─────────────────────────────────────────────
    #  Internal: unified workflow execution
    # ─────────────────────────────────────────────

    async def _run_workflow(
        self,
        workflow_id: str,
        parameters: dict[str, Any],
        trace_id: str,
    ) -> dict[str, Any]:
        """Execute a Coze workflow and handle interrupt_data / logging."""

        body: dict[str, Any] = {
            "workflow_id": workflow_id,
            "parameters": parameters,
            "connector_id": "1024",
        }

        payload = await self._client._request("POST", self._WORKFLOW_ENDPOINT, body)

        # ── 记录 debug_url 和 usage ──
        debug_url = payload.get("debug_url", "-")
        usage = payload.get("usage", {})
        token_count = usage.get("token_count", 0) if isinstance(usage, dict) else 0
        self._logger.info(
            f"workflow_run workflow_id={workflow_id} trace_id={trace_id} "
            f"debug_url={debug_url} token_count={token_count}"
        )

        # ── interrupt_data 检测（MVP 不恢复中断） ──
        interrupt_data = payload.get("interrupt_data")
        if interrupt_data:
            event_id = interrupt_data.get("event_id", "-")
            interrupt_type = interrupt_data.get("type", "-")
            self._logger.warning(
                f"workflow_interrupted workflow_id={workflow_id} trace_id={trace_id} "
                f"event_id={event_id} type={interrupt_type}"
            )
            raise CozeClientError(
                f"workflow interrupted (event_id={event_id}, type={interrupt_type})",
                code=-2,
                logid=str(event_id),
            )

        return payload

    # ─────────────────────────────────────────────
    #  Internal: response parsers
    # ─────────────────────────────────────────────

    def _parse_data_field(self, payload: dict[str, Any]) -> Any:
        """Extract and JSON-parse the ``data`` field from workflow response.

        ``data`` is typically a JSON-serialized string; fall back to raw value
        if it is already a dict/list.
        """

        raw_data = payload.get("data", "")

        if isinstance(raw_data, str):
            if not raw_data.strip():
                return None
            try:
                return json.loads(raw_data)
            except json.JSONDecodeError:
                self._logger.warning(f"workflow data is not valid JSON: {raw_data[:200]}")
                return raw_data
        return raw_data

    def _parse_route_candidates(self, payload: dict[str, Any]) -> list[RouteCandidate]:
        """Parse route search workflow output into candidate list."""

        parsed = self._parse_data_field(payload)
        if parsed is None:
            self._logger.warning("route search returned empty data")
            return []

        # 期望结构: {"output": [{"documentId": ..., "output": ...}, ...]}
        items: list[dict[str, Any]] = []
        if isinstance(parsed, dict):
            items = parsed.get("output", [])
        elif isinstance(parsed, list):
            items = parsed
        else:
            self._logger.warning(f"unexpected route search data type: {type(parsed)}")
            return []

        if not items:
            self._logger.warning("route search returned 0 candidates")
            return []

        candidates: list[RouteCandidate] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            doc_id = item.get("documentId") or item.get("document_id")
            output_text = item.get("output", "")
            if doc_id:
                candidates.append(RouteCandidate(document_id=str(doc_id), output=str(output_text)))

        if not candidates:
            self._logger.warning("route search parsed 0 valid candidates")

        return candidates

    def _parse_visa_result(self, payload: dict[str, Any]) -> tuple[str, list[str]]:
        """Parse visa search workflow output into (answer, sources)."""

        parsed = self._parse_data_field(payload)
        if parsed is None:
            self._logger.warning("visa search returned empty data")
            return "", []

        # 期望结构: {"output": [{"documentId": ..., "output": ...}, ...]}
        items: list[dict[str, Any]] = []
        if isinstance(parsed, dict):
            items = parsed.get("output", [])
        elif isinstance(parsed, list):
            items = parsed

        if not items:
            # data 可能直接是字符串（外部信息格式），当做 answer
            if isinstance(parsed, str):
                return parsed, []
            self._logger.warning("visa search returned 0 items")
            return "", []

        answer_parts: list[str] = []
        sources: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            doc_id = item.get("documentId") or item.get("document_id")
            output_text = item.get("output", "")
            if doc_id:
                sources.append(str(doc_id))
            if output_text:
                answer_parts.append(str(output_text))

        return "\n\n".join(answer_parts), sources

    def _parse_external_output(self, payload: dict[str, Any]) -> str:
        """Parse external info workflow output into a plain text string."""

        parsed = self._parse_data_field(payload)
        if parsed is None:
            self._logger.warning("external info returned empty data")
            return ""

        # 期望结构: {"output": "..."}  或直接字符串
        if isinstance(parsed, dict):
            return str(parsed.get("output", ""))
        return str(parsed)
