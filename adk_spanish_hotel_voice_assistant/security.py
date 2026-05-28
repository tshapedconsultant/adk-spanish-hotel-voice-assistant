"""Input validation and webhook authentication (OWASP Agentic-aligned controls).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import hashlib
import hmac
import re

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


def webhook_secret_matches(expected: str, provided: str) -> bool:
    """Compare secrets via SHA-256 digests (constant-time; no length oracle on the raw key)."""
    if not expected:
        return True
    he = hashlib.sha256(expected.encode("utf-8")).digest()
    hp = hashlib.sha256(provided.encode("utf-8")).digest()
    return hmac.compare_digest(he, hp)
