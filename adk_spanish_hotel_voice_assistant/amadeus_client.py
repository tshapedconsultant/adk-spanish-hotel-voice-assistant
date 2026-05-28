"""Amadeus Self-Service API client (OAuth2 + HTTP).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests

from .config import (
    AMADEUS_API_HOST,
    AMADEUS_CLIENT_ID,
    AMADEUS_CLIENT_SECRET,
    logger,
)

_TOKEN_CACHE: Dict[str, Any] = {"access_token": None, "expires_at": 0.0}


class AmadeusError(RuntimeError):
    """Raised when the Amadeus API returns an error."""


def amadeus_configured() -> bool:
    return bool(AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET)


def _oauth_url() -> str:
    return f"{AMADEUS_API_HOST}/v1/security/oauth2"


def get_access_token(*, force_refresh: bool = False) -> str:
    if not amadeus_configured():
        raise AmadeusError("AMADEUS_CLIENT_ID y AMADEUS_CLIENT_SECRET no configurados")

    now = time.time()
    cached = _TOKEN_CACHE.get("access_token")
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0)
    if cached and not force_refresh and now < expires_at - 30:
        return str(cached)

    resp = requests.post(
        _oauth_url(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": AMADEUS_CLIENT_ID,
            "client_secret": AMADEUS_CLIENT_SECRET,
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        raise AmadeusError(f"OAuth Amadeus falló ({resp.status_code}): {resp.text[:200]}")

    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise AmadeusError("OAuth Amadeus no devolvió access_token")

    ttl = int(payload.get("expires_in") or 1800)
    _TOKEN_CACHE["access_token"] = token
    _TOKEN_CACHE["expires_at"] = now + ttl
    logger.debug("Amadeus OAuth token refreshed (ttl=%ss)", ttl)
    return str(token)


def amadeus_get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    retry_on_401: bool = True,
) -> Dict[str, Any]:
    """Authenticated GET against the Amadeus API host."""
    token = get_access_token()
    url = f"{AMADEUS_API_HOST}{path}"
    resp = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=25,
    )
    if resp.status_code == 401 and retry_on_401:
        token = get_access_token(force_refresh=True)
        resp = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=25,
        )
    if resp.status_code >= 400:
        raise AmadeusError(f"Amadeus GET {path} ({resp.status_code}): {resp.text[:300]}")
    return resp.json()
