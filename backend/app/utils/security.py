"""Security helpers for masking and validating PII fields."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config.settings import settings

_CN_PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_HOURS = 24
_bearer_scheme = HTTPBearer(auto_error=False)


def validate_phone(phone: str) -> bool:
    """Validate China mainland mobile number format."""

    value = phone.strip()
    return bool(_CN_PHONE_PATTERN.fullmatch(value))


def mask_phone(phone: str) -> str:
    """Mask a phone number to 138****1234 style."""

    value = phone.strip()
    if len(value) < 7:
        return value
    return f"{value[:3]}****{value[-4:]}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against bcrypt hash."""

    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def hash_password(password: str) -> str:
    """Hash password with bcrypt."""

    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token."""

    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=_ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate JWT access token."""

    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """FastAPI dependency that validates admin bearer token."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        )

    payload = decode_access_token(credentials.credentials)
    username = payload.get("sub")
    if username != settings.ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin token",
        )
    return username
