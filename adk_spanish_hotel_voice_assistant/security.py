"""Input validation and webhook authentication (OWASP Agentic-aligned controls).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any, Optional, Tuple

from flask import Request

# Server-issued session IDs are UUID v4 strings; reject malformed IDs (ASI06 / injection hardening).
_SESSION_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def is_valid_session_id(session_id: str) -> bool:
    if not session_id or len(session_id) > 48:
        return False
    return _SESSION_UUID_RE.match(session_id.strip()) is not None


def extract_webhook_secret(request: Request) -> str:
    """Read shared secret from X-Webhook-Key or Authorization: Bearer <token>."""
    direct = request.headers.get("X-Webhook-Key")
    if direct is not None and str(direct).strip():
        return str(direct).strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def extract_session_api_key(request: Request) -> str:
    """Read session inspection key from X-API-Key / X-Api-Key."""
    for header in ("X-API-Key", "X-Api-Key"):
        value = request.headers.get(header)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def clamp_user_text(text: str, max_chars: int) -> str:
    """Truncate user text to mitigate context poisoning (ASI06)."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars]


def validate_user_text_length(text: str, max_chars: int) -> Tuple[bool, str]:
    """Return (ok, error_message) when text exceeds the configured limit."""
    if len(text) > max_chars:
        return False, f"Field 'text' exceeds {max_chars} characters"
    return True, ""


def parse_guest_count(value: Any, *, default: int = 1) -> int:
    """Parse guest count safely; non-numeric values fall back to ``default``."""
    if value is None or value == "" or value == 0:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if value > 0 else default
    if isinstance(value, float):
        iv = int(value)
        return iv if iv > 0 else default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        if stripped.isdigit():
            iv = int(stripped)
            return iv if iv > 0 else default
        try:
            iv = int(float(stripped))
            return iv if iv > 0 else default
        except ValueError:
            return default
    return default


def webhook_secret_matches(expected: str, provided: Optional[str]) -> bool:
    """Compare secrets via SHA-256 digests (constant-time; no length oracle on the raw key)."""
    if not expected:
        return True
    if provided is None:
        return False
    provided_str = str(provided).strip()
    if not provided_str:
        return False
    he = hashlib.sha256(expected.encode("utf-8")).digest()
    hp = hashlib.sha256(provided_str.encode("utf-8")).digest()
    return hmac.compare_digest(he, hp)
