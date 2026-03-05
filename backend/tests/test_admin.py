"""Admin auth and protected endpoint tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.config.settings import settings
from app.utils.security import create_access_token, hash_password


@pytest.fixture
def admin_creds(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Patch settings with deterministic admin credentials for tests."""

    username = "admin"
    password = "admin123"
    monkeypatch.setattr(settings, "ADMIN_USERNAME", username, raising=False)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", hash_password(password), raising=False)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test_jwt_secret", raising=False)
    return {"username": username, "password": password}


@pytest.mark.anyio
async def test_login_success(async_client: AsyncClient, admin_creds: dict[str, str]) -> None:
    """Valid admin credentials should return access token."""

    resp = await async_client.post("/admin/login", json=admin_creds)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"


@pytest.mark.anyio
async def test_login_wrong_password(async_client: AsyncClient, admin_creds: dict[str, str]) -> None:
    """Wrong password should be rejected."""

    resp = await async_client.post(
        "/admin/login",
        json={"username": admin_creds["username"], "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_admin_api_without_token(async_client: AsyncClient) -> None:
    """Protected admin API should reject missing token."""

    resp = await async_client.get("/admin/prompts/")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_admin_api_with_valid_token(async_client: AsyncClient, admin_creds: dict[str, str]) -> None:
    """Protected admin API should pass with valid bearer token."""

    login_resp = await async_client.post("/admin/login", json=admin_creds)
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    resp = await async_client.get("/admin/prompts/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text


@pytest.mark.anyio
async def test_admin_api_with_expired_token(async_client: AsyncClient, admin_creds: dict[str, str]) -> None:
    """Expired token should be rejected with 401."""

    expired_token = create_access_token({"sub": admin_creds["username"]}, expires_delta=timedelta(seconds=-1))
    resp = await async_client.get("/admin/prompts/", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
