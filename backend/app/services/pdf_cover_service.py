"""PDF cover generation service for route documents."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import fitz
import httpx

from app.utils.logger import get_logger

_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024


class PdfCoverService:
    """Generate a route cover image from the first page of a PDF document."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._logger = get_logger(__name__)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_cover(self, route_id: int, doc_url: str) -> str | None:
        """Download a PDF and render the first page to a static JPG file."""

        if not self._is_pdf_url(doc_url):
            return None

        pdf_bytes = await self._download_pdf(doc_url)
        if pdf_bytes is None:
            return None

        filename = f"route_{route_id}.jpg"
        output_path = self._output_dir / filename

        try:
            await asyncio.to_thread(self._render_first_page, pdf_bytes, output_path)
            return f"/static/route-covers/{filename}"
        except Exception as exc:
            self._logger.warning("generate pdf cover failed route_id=%s err=%s", route_id, exc)
            return None

    def _is_pdf_url(self, doc_url: str) -> bool:
        parsed = urlparse(doc_url.strip())
        return parsed.path.lower().endswith(".pdf")

    async def _download_pdf(self, doc_url: str) -> bytes | None:
        timeout = httpx.Timeout(20.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(doc_url)
                response.raise_for_status()
                content = response.content
        except Exception as exc:
            self._logger.warning("download pdf failed url=%s err=%s", doc_url, exc)
            return None

        if not content:
            return None
        if len(content) > _MAX_DOWNLOAD_BYTES:
            self._logger.warning("pdf too large url=%s size=%s", doc_url, len(content))
            return None
        return content

    def _render_first_page(self, pdf_bytes: bytes, output_path: Path) -> None:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if document.page_count < 1:
                raise ValueError("empty pdf")
            page = document.load_page(0)
            matrix = fitz.Matrix(1.6, 1.6)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pixmap.save(output_path.as_posix())
        finally:
            document.close()
