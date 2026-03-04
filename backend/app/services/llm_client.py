"""Lightweight async LLM client wrapper for DeepSeek-compatible endpoints."""

from __future__ import annotations

import httpx

from app.config.settings import settings


class LLMClient:
    """Manage shared async HTTP client for LLM calls."""

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.deepseek.com") -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._http_client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    @classmethod
    def from_settings(cls) -> LLMClient:
        """Build client instance from environment settings."""

        return cls(
            api_key=settings.DEEPSEEK_API_KEY,
            model=settings.DEEPSEEK_MODEL,
        )

    @property
    def model(self) -> str:
        """Default model name."""

        return self._model

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Underlying reusable HTTP client."""

        return self._http_client

    async def aclose(self) -> None:
        """Close async HTTP resources."""

        await self._http_client.aclose()
