"""Coze workflow execution service for online retrieval (route / visa / external info)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from app.config.settings import Settings
from app.models.schemas import (
    ExternalInfoResult,
    RouteCandidate,
    RouteParseResult,
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

    async def run_route_search(self, query: str, trace_id: str, session_id: str = "") -> RouteSearchResult:
        """调用 WF_ROUTE_SEARCH 工作流，返回路线候选列表。

        Parameters 约定入参名为 ``"input"``（COZE.md 0.3 节）。
        """

        payload = await self._run_workflow(
            workflow_id=self._settings.COZE_WF_ROUTE_SEARCH_ID,
            parameters={"input": query},
            trace_id=trace_id,
            session_id=session_id,
        )

        debug_url = payload.get("debug_url")
        candidates = self._parse_route_candidates(payload, trace_id=trace_id)

        return RouteSearchResult(candidates=candidates, debug_url=debug_url)

    async def run_visa_search(self, query: str, trace_id: str, session_id: str = "") -> VisaSearchResult:
        """调用 WF_VISA_SEARCH 工作流，返回签证搜索结果。

        Parameters 约定入参名为 ``"input"``（COZE.md 0.3 节）。
        """

        payload = await self._run_workflow(
            workflow_id=self._settings.COZE_WF_VISA_SEARCH_ID,
            parameters={"input": query},
            trace_id=trace_id,
            session_id=session_id,
        )

        debug_url = payload.get("debug_url")
        answer, sources = self._parse_visa_result(payload)

        return VisaSearchResult(answer=answer, sources=sources, debug_url=debug_url)

    async def run_external_info(
        self,
        query: str,
        trace_id: str,
        session_id: str = "",
        info_type: str = "external_info",
    ) -> ExternalInfoResult:
        """调用 WF_EXTERNAL_INFO 工作流，参数按 COZE.md 约定使用 input 字符串。"""

        parameters: dict[str, Any] = {"input": query}

        payload = await self._run_workflow(
            workflow_id=self._settings.COZE_WF_EXTERNAL_INFO_ID,
            parameters=parameters,
            trace_id=trace_id,
            session_id=session_id,
        )

        debug_url = payload.get("debug_url")
        output = self._parse_external_output(payload)

        return ExternalInfoResult(info_type=info_type, output=output, debug_url=debug_url)

    async def run_route_parse(self, doc_url: str, trace_id: str) -> RouteParseResult:
        """调用 WF_ROUTE_PARSE 工作流，解析路线文档并返回结构化字段。"""

        payload = await self._run_workflow(
            workflow_id=self._settings.COZE_WF_ROUTE_PARSE_ID,
            parameters={"input": doc_url},
            trace_id=trace_id,
            timeout=self._settings.COZE_PARSE_TIMEOUT,
        )

        return self._parse_route_parse_result(payload, trace_id=trace_id)

    # ─────────────────────────────────────────────
    #  Internal: unified workflow execution
    # ─────────────────────────────────────────────

    async def _run_workflow(
        self,
        workflow_id: str,
        parameters: dict[str, Any],
        trace_id: str,
        session_id: str = "",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a Coze workflow and handle interrupt_data / logging."""

        body: dict[str, Any] = {
            "workflow_id": workflow_id,
            "parameters": parameters,
            "connector_id": "1024",
        }

        payload = await self._client._request(
            "POST",
            self._WORKFLOW_ENDPOINT,
            body,
            log_context={
                "trace_id": trace_id,
                "session_id": session_id,
                "workflow_id": workflow_id,
                "call_type": self._infer_call_type(workflow_id),
            },
            timeout=timeout,
        )

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
            try:
                from app.services.container import services

                await services.coze_log_service.log_call(
                    trace_id=trace_id,
                    session_id=session_id,
                    call_type=self._infer_call_type(workflow_id),
                    workflow_id=workflow_id,
                    endpoint=self._WORKFLOW_ENDPOINT,
                    request_params=parameters,
                    response_code=int(payload.get("code", 0) or 0),
                    response_data=payload,
                    coze_logid=str(event_id),
                    debug_url=str(payload.get("debug_url") or "") or None,
                    token_count=int(usage.get("token_count", 0) or 0) if isinstance(usage, dict) else None,
                    latency_ms=0,
                    status="interrupted",
                    error_message=f"interrupted event_id={event_id} type={interrupt_type}",
                )
            except Exception:
                self._logger.warning("failed to write interrupted workflow log")
            raise CozeClientError(
                f"workflow interrupted (event_id={event_id}, type={interrupt_type})",
                code=-2,
                logid=str(event_id),
            )

        return payload

    def _infer_call_type(self, workflow_id: str) -> str:
        if workflow_id == self._settings.COZE_WF_ROUTE_SEARCH_ID:
            return "route_search"
        if workflow_id == self._settings.COZE_WF_VISA_SEARCH_ID:
            return "visa_search"
        if workflow_id == self._settings.COZE_WF_EXTERNAL_INFO_ID:
            return "external_info"
        if workflow_id == self._settings.COZE_WF_ROUTE_PARSE_ID:
            return "route_parse"
        return "workflow_run"

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

    def _parse_route_candidates(self, payload: dict[str, Any], trace_id: str) -> list[RouteCandidate]:
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
        none_route_id_count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            doc_id = item.get("documentId") or item.get("document_id")
            output_text = item.get("output", "")
            if doc_id:
                raw_route_id = self._extract_route_id(item, str(output_text))
                route_id: str | None = None
                if raw_route_id is not None:
                    normalized_route_id = str(raw_route_id).strip()
                    try:
                        route_id = str(int(normalized_route_id))
                    except (TypeError, ValueError):
                        if normalized_route_id.lower().startswith(("http://", "https://")):
                            route_id = normalized_route_id
                        else:
                            self._logger.warning(
                                "invalid route_id from workflow candidate, "
                                f"trace_id={trace_id} document_id={doc_id} raw_route_id={raw_route_id}"
                            )
                if route_id is None and raw_route_id is None:
                    self._logger.warning(
                        f"route_id not found in route candidate output, trace_id={trace_id} document_id={doc_id}"
                    )
                if route_id is None:
                    none_route_id_count += 1
                candidates.append(
                    RouteCandidate(
                        document_id=str(doc_id),
                        route_id=route_id,
                        output=str(output_text),
                    )
                )

        if not candidates:
            self._logger.warning("route search parsed 0 valid candidates")
        else:
            self._logger.info(
                "route search parsed candidates trace_id=%s total=%s route_id_none=%s",
                trace_id,
                len(candidates),
                none_route_id_count,
            )

        return candidates

    def _extract_route_id(self, item: dict[str, Any], output_text: str) -> str | None:
        """Extract route id from workflow item fields or output text."""

        direct_route_id = item.get("route_id") or item.get("routeId")
        if direct_route_id:
            return str(direct_route_id)

        route_id_match = re.search(r"route_id\s*[:：]\s*([A-Za-z0-9_-]+)", output_text, flags=re.IGNORECASE)
        if route_id_match:
            return route_id_match.group(1)

        numeric_route_id_match = re.search(
            r"(?:route_id|id)\s*[:：=]\s*(\d+)",
            output_text,
            flags=re.IGNORECASE,
        )
        if numeric_route_id_match:
            return numeric_route_id_match.group(1)

        loose_numeric_id_match = re.search(r"\b(?:id|ID)\b\s*[:：=]?\s*(\d+)", output_text)
        if loose_numeric_id_match:
            return loose_numeric_id_match.group(1)

        file_url_id = item.get("file_url_id") or item.get("fileUrlId")
        if isinstance(file_url_id, str):
            file_url_id = file_url_id.strip()
            if file_url_id.lower().startswith(("http://", "https://")):
                return file_url_id

        file_url_match = re.search(r"file_url_id[：:]\s*(https?://[^\s\"'\n，。；）\)]+)", output_text)
        if file_url_match:
            url = file_url_match.group(1).strip().rstrip(".,;，。；、)")
            return url

        unique_numeric_tokens = re.findall(r"(?<!\d)(\d{3,})(?!\d)", output_text)
        unique_numeric_token_set = {token for token in unique_numeric_tokens if token}
        if len(unique_numeric_token_set) == 1:
            return next(iter(unique_numeric_token_set))

        return None

    def _extract_route_id_from_url(self, url: str) -> str | None:
        """Extract route id from the file URL basename (without extension)."""

        parsed = urlparse(url.strip())
        filename = parsed.path.rsplit("/", 1)[-1]
        if "." not in filename:
            return None

        stem, ext = filename.rsplit(".", 1)
        if ext.lower() not in {"pdf", "doc", "docx"}:
            return None
        if not stem:
            return None
        return stem

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

    def _parse_route_parse_result(self, payload: dict[str, Any], trace_id: str) -> RouteParseResult:
        """Parse route document parsing workflow output into RouteParseResult."""

        parsed = self._parse_data_field(payload)
        if parsed is None:
            self._logger.warning("route parse returned empty data, trace_id=%s", trace_id)
            return RouteParseResult()

        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except json.JSONDecodeError:
                self._logger.warning("route parse data is not JSON, trace_id=%s", trace_id)
                return RouteParseResult()

        if not isinstance(parsed, dict):
            self._logger.warning("route parse data unexpected type=%s, trace_id=%s", type(parsed), trace_id)
            return RouteParseResult()

        # 优先取 output 字段（和其他工作流一致的嵌套结构）
        inner = parsed
        if "output" in parsed and isinstance(parsed["output"], dict):
            inner = parsed["output"]

        tags_raw = inner.get("index_tags", [])
        tags = self._normalize_index_tags(tags_raw)

        return RouteParseResult(
            basic_info=self._normalize_text_block(inner.get("basic_info")),
            highlights=self._normalize_text_block(inner.get("highlights")),
            index_tags=tags,
            itinerary_days=self._normalize_itinerary_days(inner.get("itinerary_days")),
            notices=self._normalize_text_block(inner.get("notices")),
            cost_included=self._normalize_text_block(inner.get("cost_included")),
            cost_excluded=self._normalize_text_block(inner.get("cost_excluded")),
            age_limit=self._normalize_text_block(inner.get("age_limit")),
            certificate_limit=self._normalize_text_block(inner.get("certificate_limit")),
        )

    def _normalize_text_block(self, value: Any) -> str:
        """Normalize route-parse field value into displayable text."""

        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts = [self._normalize_text_block(item) for item in value]
            return "\n".join(part for part in parts if part)
        if isinstance(value, dict):
            try:
                return json.dumps(value, ensure_ascii=False)
            except TypeError:
                return str(value).strip()
        return str(value).strip()

    def _normalize_itinerary_days(self, value: Any) -> list[dict]:
        """Ensure itinerary_days is always a list of dicts."""

        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            return []
        if isinstance(value, list):
            return value
        return []

    def _normalize_index_tags(self, value: Any) -> list[str]:
        """Normalize index_tags from list or JSON string to string list."""

        if isinstance(value, list):
            return [str(tag).strip() for tag in value if str(tag).strip()]

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None

            if isinstance(parsed, list):
                return [str(tag).strip() for tag in parsed if str(tag).strip()]

            cleaned = text.strip().strip("[]")
            tokens = re.split(r"[，,;\n]+", cleaned)
            normalized: list[str] = []
            for token in tokens:
                tag = token.strip().strip("\"'").strip()
                if tag:
                    normalized.append(tag)
            return normalized

        return []
