"""Unified asynchronous client for Coze OpenAPI."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from jose import JWTError, jwt

from app.config.settings import settings
from app.utils.logger import get_logger, get_trace_id


class CozeClientError(RuntimeError):
    """Coze client operation error."""

    def __init__(self, message: str, code: int | None = None, logid: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.logid = logid


class CozeClient:
    """Asynchronous Coze API client with OAuth JWT token exchange."""

    def __init__(self, coze_oauth_app_id: str, coze_kid: str, coze_private_key_path: str) -> None:
        """Initialize client credentials, token cache, and async http client."""

        self._logger = get_logger(__name__)
        self._base_url = "https://api.coze.cn"
        self._app_id = coze_oauth_app_id
        self._kid = coze_kid
        self._private_key_path = self._resolve_private_key_path(coze_private_key_path)
        self._private_key = self._private_key_path.read_text(encoding="utf-8")

        self._token_cache: dict[str, Any] = {}
        self._token_lock = asyncio.Lock()
        self._http_client = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)

    @classmethod
    def from_settings(cls) -> CozeClient:
        """Create a client from application settings."""

        return cls(settings.COZE_OAUTH_APP_ID, settings.COZE_KID, settings.COZE_PRIVATE_KEY_PATH)

    async def _generate_jwt(self) -> str:
        """Generate one-time JWT for Coze OAuth exchange."""

        now = int(time.time())
        payload = {
            "iss": self._app_id,
            "aud": "api.coze.cn",
            "iat": now,
            "exp": now + 600,
            "jti": str(uuid4()),
        }
        headers = {"kid": self._kid, "typ": "JWT"}

        try:
            return jwt.encode(payload, self._private_key, algorithm="RS256", headers=headers)
        except JWTError as exc:
            raise CozeClientError("failed to generate coze oauth jwt") from exc

    async def _get_access_token(self) -> str:
        """Get cached access token and refresh if expiring within 60 seconds."""

        now = int(time.time())
        cached_token = self._token_cache.get("token")
        cached_expires_at = int(self._token_cache.get("expires_at", 0))
        if cached_token and cached_expires_at - now > 60:
            return str(cached_token)

        async with self._token_lock:
            now = int(time.time())
            cached_token = self._token_cache.get("token")
            cached_expires_at = int(self._token_cache.get("expires_at", 0))
            if cached_token and cached_expires_at - now > 60:
                return str(cached_token)

            jwt_token = await self._generate_jwt()
            body: dict[str, Any] = {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "duration_seconds": 900,
            }

            endpoint = "/api/permission/oauth2/token"
            last_request_error: Exception | None = None
            for attempt in range(2):
                started_at = time.monotonic()
                payload: dict[str, Any] | None = None
                try:
                    response = await self._http_client.post(
                        endpoint,
                        json=body,
                        headers={
                            "Authorization": f"Bearer {jwt_token}",
                            "Content-Type": "application/json",
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise CozeClientError("invalid coze oauth token response payload")

                    code = int(payload.get("code", 0))
                    msg = str(payload.get("msg", ""))
                    detail = payload.get("detail")
                    logid = detail.get("logid", "-") if isinstance(detail, dict) else "-"
                    self._logger.info(
                        f"coze_oauth endpoint={endpoint} trace_id={get_trace_id()} code={code} msg={msg} logid={logid}"
                    )

                    if code != 0:
                        await self._log_call(
                            trace_id=get_trace_id(),
                            session_id="",
                            call_type="oauth_token",
                            workflow_id=None,
                            endpoint=endpoint,
                            request_params=body,
                            response_code=code,
                            response_data=payload,
                            coze_logid=str(logid),
                            debug_url=None,
                            token_count=None,
                            latency_ms=int((time.monotonic() - started_at) * 1000),
                            status="error",
                            error_message=msg or "coze oauth token exchange failed",
                        )
                        raise CozeClientError("coze oauth token exchange failed", code=code, logid=str(logid))

                    token_data = payload.get("data", payload)
                    if not isinstance(token_data, dict):
                        token_data = payload

                    access_token = token_data.get("access_token")
                    if not isinstance(access_token, str) or not access_token:
                        raise CozeClientError("coze oauth token missing access_token field")

                    expires_at = self._resolve_expires_at(token_data.get("expires_in"), now)
                    self._token_cache = {"token": access_token, "expires_at": expires_at}
                    await self._log_call(
                        trace_id=get_trace_id(),
                        session_id="",
                        call_type="oauth_token",
                        workflow_id=None,
                        endpoint=endpoint,
                        request_params=body,
                        response_code=code,
                        response_data=payload,
                        coze_logid=str(logid),
                        debug_url=None,
                        token_count=None,
                        latency_ms=int((time.monotonic() - started_at) * 1000),
                        status="success",
                        error_message=None,
                    )
                    return access_token
                except httpx.RequestError as exc:
                    last_request_error = exc
                    await self._log_call(
                        trace_id=get_trace_id(),
                        session_id="",
                        call_type="oauth_token",
                        workflow_id=None,
                        endpoint=endpoint,
                        request_params=body,
                        response_code=None,
                        response_data=None,
                        coze_logid=None,
                        debug_url=None,
                        token_count=None,
                        latency_ms=int((time.monotonic() - started_at) * 1000),
                        status="error",
                        error_message=str(exc),
                    )
                    if attempt == 0:
                        continue
                except ValueError as exc:
                    await self._log_call(
                        trace_id=get_trace_id(),
                        session_id="",
                        call_type="oauth_token",
                        workflow_id=None,
                        endpoint=endpoint,
                        request_params=body,
                        response_code=None,
                        response_data=payload,
                        coze_logid=None,
                        debug_url=None,
                        token_count=None,
                        latency_ms=int((time.monotonic() - started_at) * 1000),
                        status="error",
                        error_message=str(exc),
                    )
                    raise CozeClientError("failed to parse coze oauth response") from exc

            raise CozeClientError("coze oauth request failed after retry") from last_request_error

    async def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        extra_headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        log_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a Coze API request with OAuth token and unified response handling."""

        access_token = await self._get_access_token()
        endpoint = path if path.startswith("/") else f"/{path}"
        last_request_error: Exception | None = None

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(2):
            started_at = time.monotonic()
            payload: dict[str, Any] | None = None
            try:
                response = await self._http_client.request(
                    method=method.upper(),
                    url=endpoint,
                    headers=headers,
                    json=body,
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise CozeClientError("invalid coze response payload")

                code = int(payload.get("code", 0))
                msg = str(payload.get("msg", ""))
                detail = payload.get("detail")
                logid = detail.get("logid", "-") if isinstance(detail, dict) else "-"
                self._logger.info(
                    f"coze_request endpoint={endpoint} trace_id={get_trace_id()} code={code} msg={msg} logid={logid}"
                )

                if code != 0:
                    await self._log_call(
                        trace_id=str((log_context or {}).get("trace_id") or get_trace_id()),
                        session_id=str((log_context or {}).get("session_id") or ""),
                        call_type=str((log_context or {}).get("call_type") or self._infer_call_type(endpoint, method)),
                        workflow_id=str((log_context or {}).get("workflow_id") or (body or {}).get("workflow_id") or "")
                        or None,
                        endpoint=endpoint,
                        request_params={"body": body, "params": params},
                        response_code=code,
                        response_data=payload,
                        coze_logid=str(logid),
                        debug_url=self._extract_debug_url(payload),
                        token_count=self._extract_token_count(payload),
                        latency_ms=int((time.monotonic() - started_at) * 1000),
                        status="error",
                        error_message=msg or "coze api request failed",
                    )
                    raise CozeClientError("coze api request failed", code=code, logid=str(logid))

                await self._log_call(
                    trace_id=str((log_context or {}).get("trace_id") or get_trace_id()),
                    session_id=str((log_context or {}).get("session_id") or ""),
                    call_type=str((log_context or {}).get("call_type") or self._infer_call_type(endpoint, method)),
                    workflow_id=str((log_context or {}).get("workflow_id") or (body or {}).get("workflow_id") or "")
                    or None,
                    endpoint=endpoint,
                    request_params={"body": body, "params": params},
                    response_code=code,
                    response_data=payload,
                    coze_logid=str(logid),
                    debug_url=self._extract_debug_url(payload),
                    token_count=self._extract_token_count(payload),
                    latency_ms=int((time.monotonic() - started_at) * 1000),
                    status="success",
                    error_message=None,
                )
                return payload
            except httpx.RequestError as exc:
                last_request_error = exc
                await self._log_call(
                    trace_id=str((log_context or {}).get("trace_id") or get_trace_id()),
                    session_id=str((log_context or {}).get("session_id") or ""),
                    call_type=str((log_context or {}).get("call_type") or self._infer_call_type(endpoint, method)),
                    workflow_id=str((log_context or {}).get("workflow_id") or (body or {}).get("workflow_id") or "")
                    or None,
                    endpoint=endpoint,
                    request_params={"body": body, "params": params},
                    response_code=None,
                    response_data=None,
                    coze_logid=None,
                    debug_url=None,
                    token_count=None,
                    latency_ms=int((time.monotonic() - started_at) * 1000),
                    status="error",
                    error_message=str(exc),
                )
                if attempt == 0:
                    continue
                self._logger.error(
                    f"coze_request endpoint={endpoint} trace_id={get_trace_id()} code=-1 msg=network_error logid=-"
                )
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                await self._log_call(
                    trace_id=str((log_context or {}).get("trace_id") or get_trace_id()),
                    session_id=str((log_context or {}).get("session_id") or ""),
                    call_type=str((log_context or {}).get("call_type") or self._infer_call_type(endpoint, method)),
                    workflow_id=str((log_context or {}).get("workflow_id") or (body or {}).get("workflow_id") or "")
                    or None,
                    endpoint=endpoint,
                    request_params={"body": body, "params": params},
                    response_code=status_code,
                    response_data=None,
                    coze_logid=None,
                    debug_url=None,
                    token_count=None,
                    latency_ms=int((time.monotonic() - started_at) * 1000),
                    status="error",
                    error_message=str(exc),
                )
                self._logger.error(
                    f"coze_request endpoint={endpoint} trace_id={get_trace_id()} code={status_code} msg=http_status_error logid=-"
                )
                raise CozeClientError(f"coze http error status={status_code}") from exc
            except ValueError as exc:
                await self._log_call(
                    trace_id=str((log_context or {}).get("trace_id") or get_trace_id()),
                    session_id=str((log_context or {}).get("session_id") or ""),
                    call_type=str((log_context or {}).get("call_type") or self._infer_call_type(endpoint, method)),
                    workflow_id=str((log_context or {}).get("workflow_id") or (body or {}).get("workflow_id") or "")
                    or None,
                    endpoint=endpoint,
                    request_params={"body": body, "params": params},
                    response_code=None,
                    response_data=payload,
                    coze_logid=None,
                    debug_url=None,
                    token_count=None,
                    latency_ms=int((time.monotonic() - started_at) * 1000),
                    status="error",
                    error_message=str(exc),
                )
                self._logger.error(
                    f"coze_request endpoint={endpoint} trace_id={get_trace_id()} code=-1 msg=invalid_json logid=-"
                )
                raise CozeClientError("failed to parse coze response json") from exc

        raise CozeClientError("coze request failed after retry") from last_request_error

    async def aclose(self) -> None:
        """Close underlying async HTTP client resources."""

        await self._http_client.aclose()

    def _resolve_private_key_path(self, configured_path: str) -> Path:
        """Resolve private key path from absolute path or backend-root relative path."""

        raw_path = Path(configured_path)
        if raw_path.is_absolute():
            resolved_path = raw_path
        else:
            backend_root = Path(__file__).resolve().parents[2]
            resolved_path = (backend_root / raw_path).resolve()

        if not resolved_path.exists():
            raise CozeClientError(f"coze private key file not found: {resolved_path}")
        return resolved_path

    def _resolve_expires_at(self, expires_in_value: Any, now: int) -> int:
        """Resolve absolute expires_at timestamp from token response field."""

        if expires_in_value is None:
            return now + 900

        try:
            parsed_value = int(expires_in_value)
        except (TypeError, ValueError):
            return now + 900

        if parsed_value > now + 60:
            return parsed_value
        if parsed_value <= 0:
            return now + 900
        return now + parsed_value

    async def _log_call(
        self,
        *,
        trace_id: str,
        session_id: str,
        call_type: str,
        workflow_id: str | None,
        endpoint: str,
        request_params: dict[str, Any] | None,
        response_code: int | None,
        response_data: dict[str, Any] | None,
        coze_logid: str | None,
        debug_url: str | None,
        token_count: int | None,
        latency_ms: int,
        status: str,
        error_message: str | None,
    ) -> None:
        try:
            from app.services.container import services

            coze_log_service = getattr(services, "_coze_log_service", None)
            if coze_log_service is None:
                return

            await coze_log_service.log_call(
                trace_id=trace_id,
                session_id=session_id,
                call_type=call_type,
                workflow_id=workflow_id,
                endpoint=endpoint,
                request_params=request_params,
                response_code=response_code,
                response_data=response_data,
                coze_logid=coze_logid,
                debug_url=debug_url,
                token_count=token_count,
                latency_ms=latency_ms,
                status=status,
                error_message=error_message,
            )
        except Exception as exc:
            self._logger.warning(f"failed to write coze call log: {exc}")

    def _infer_call_type(self, endpoint: str, method: str) -> str:
        if endpoint == "/api/permission/oauth2/token":
            return "oauth_token"
        if endpoint == "/v1/workflow/run":
            return "workflow_run"
        if endpoint == "/v1/datasets":
            return "kb_list_datasets" if method.upper() == "GET" else "kb_create_dataset"
        if endpoint.startswith("/v1/datasets/") and endpoint.endswith("/process"):
            return "kb_document_progress"
        if endpoint.startswith("/v1/datasets/"):
            return "kb_update_dataset" if method.upper() == "PUT" else "kb_delete_dataset"
        if endpoint == "/open_api/knowledge/document/create":
            return "kb_create_doc"
        if endpoint == "/open_api/knowledge/document/list":
            return "kb_list_doc"
        if endpoint == "/open_api/knowledge/document/update":
            return "kb_update_doc"
        if endpoint == "/open_api/knowledge/document/delete":
            return "kb_delete_doc"
        return "unknown"

    def _extract_debug_url(self, payload: dict[str, Any]) -> str | None:
        value = payload.get("debug_url")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _extract_token_count(self, payload: dict[str, Any]) -> int | None:
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return None
        raw = usage.get("token_count")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None
