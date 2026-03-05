"""Admin authentication API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.config.settings import settings
from app.models.schemas import AdminLoginRequest, AdminLoginResponse
from app.utils.security import create_access_token, verify_password

router = APIRouter()


@router.post('/login', response_model=AdminLoginResponse)
async def admin_login(req: AdminLoginRequest) -> AdminLoginResponse:
    """Validate admin credentials and issue JWT token."""

    if req.username != settings.ADMIN_USERNAME:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid credentials')

    if not verify_password(req.password, settings.ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid credentials')

    token = create_access_token({'sub': req.username})
    return AdminLoginResponse(access_token=token)
