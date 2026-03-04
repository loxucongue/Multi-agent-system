"""Security helpers for masking and validating PII fields."""

from __future__ import annotations

import re

_CN_PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


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
