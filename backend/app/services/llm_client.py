"""DeepSeek OpenAI-compatible async LLM client."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config.settings import settings
from app.utils.logger import get_logger

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-chat"
_DEFAULT_TIMEOUT = 60.0
_MAX_NETWORK_RETRIES = 1
_MAX_CONCURRENT_REQUESTS = 5


class LLMClientError(RuntimeError):
    """Raised when DeepSeek request/response handling fails."""


class LLMClient:
    """DeepSeek client wrapper for chat, json chat, and streaming chat."""

    def __init__(self) -> None:
        self._api_key = settings.DEEPSEEK_API_KEY
        self._model = settings.DEEPSEEK_MODEL or _DEFAULT_MODEL
        self._logger = get_logger(__name__)
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

        self._http_client = httpx.AsyncClient(
            base_url=_DEFAULT_BASE_URL,
            timeout=_DEFAULT_TIMEOUT,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    @classmethod
    def from_settings(cls) -> LLMClient:
        """Compatibility constructor for service container."""

        return cls()

    @property
    def model(self) -> str:
        """Default model configured for this client."""

        return self._model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Run a non-stream chat completion and return content string."""

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        async with self._semaphore:
            result = await self._request_chat_completion(payload)
        return self._extract_content(result)

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any],
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Request structured JSON output and parse response into a dict."""

        schema_instruction = (
            "You must return a valid JSON object only. "
            "Follow this JSON schema strictly:\n"
            f"{json.dumps(json_schema, ensure_ascii=False)}"
        )
        schema_messages: list[dict[str, Any]] = [
            {"role": "system", "content": schema_instruction},
            *messages,
        ]

        first_content = await self.chat(
            messages=schema_messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        try:
            return self._parse_json_content(first_content)
        except ValueError:
            retry_content = await self.chat(
                messages=schema_messages,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            try:
                return self._parse_json_content(retry_content)
            except ValueError as exc:
                raise LLMClientError("failed to parse json response after retry") from exc

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Stream chat completion and yield content deltas."""

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        async with self._semaphore:
            request_error: Exception | None = None
            for attempt in range(_MAX_NETWORK_RETRIES + 1):
                usage_logged = False
                try:
                    async with self._http_client.stream("POST", "/chat/completions", json=payload) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue

                            data_str = line[5:].strip()
                            if not data_str or data_str == "[DONE]":
                                continue

                            chunk = json.loads(data_str)
                            if not isinstance(chunk, dict):
                                continue

                            usage = chunk.get("usage")
                            if isinstance(usage, dict) and not usage_logged:
                                self._log_token_usage(usage)
                                usage_logged = True

                            choices = chunk.get("choices")
                            if not isinstance(choices, list) or not choices:
                                continue

                            delta = choices[0].get("delta", {})
                            if not isinstance(delta, dict):
                                continue

                            content = delta.get("content")
                            if isinstance(content, str) and content:
                                yield content

                    return
                except httpx.RequestError as exc:
                    request_error = exc
                    if attempt < _MAX_NETWORK_RETRIES:
                        continue
                except httpx.HTTPStatusError as exc:
                    raise LLMClientError(f"deepseek http error status={exc.response.status_code}") from exc
                except json.JSONDecodeError as exc:
                    raise LLMClientError("failed to parse deepseek stream chunk json") from exc

            raise LLMClientError("deepseek stream request failed after retry") from request_error

    async def aclose(self) -> None:
        """Close async HTTP resources."""

        await self._http_client.aclose()

    async def _request_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_error: Exception | None = None

        for attempt in range(_MAX_NETWORK_RETRIES + 1):
            try:
                response = await self._http_client.post("/chat/completions", json=payload)
                response.raise_for_status()

                data = response.json()
                if not isinstance(data, dict):
                    raise LLMClientError("deepseek response payload must be json object")

                if isinstance(data.get("error"), dict):
                    err = data["error"]
                    message = str(err.get("message", "deepseek api error"))
                    raise LLMClientError(message)

                self._log_token_usage(data.get("usage"))
                return data
            except httpx.RequestError as exc:
                request_error = exc
                if attempt < _MAX_NETWORK_RETRIES:
                    continue
            except httpx.HTTPStatusError as exc:
                raise LLMClientError(f"deepseek http error status={exc.response.status_code}") from exc
            except json.JSONDecodeError as exc:
                raise LLMClientError("failed to parse deepseek response json") from exc

        raise LLMClientError("deepseek request failed after retry") from request_error

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMClientError("deepseek response missing choices")

        first = choices[0]
        if not isinstance(first, dict):
            raise LLMClientError("deepseek response choices[0] invalid")

        message = first.get("message", {})
        if not isinstance(message, dict):
            raise LLMClientError("deepseek response message invalid")

        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
            return "".join(text_parts)
        return str(content or "")

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        raw = content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\s*```$", "", raw)

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("no json object found in llm response")

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("llm response json is not an object")
        return parsed

    def _log_token_usage(self, usage: Any) -> None:
        prompt_tokens = -1
        completion_tokens = -1
        total_tokens = -1

        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("prompt_tokens", -1) or -1)
            completion_tokens = int(usage.get("completion_tokens", -1) or -1)
            total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or -1)

        self._logger.info(
            f"llm_token_usage model={self._model} prompt_tokens={prompt_tokens} "
            f"completion_tokens={completion_tokens} total_tokens={total_tokens}"
        )
