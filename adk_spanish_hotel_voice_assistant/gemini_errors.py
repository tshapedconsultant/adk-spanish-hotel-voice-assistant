"""Gemini API error helpers (quota, user-facing messages).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .config import GEMINI_25_FLASH, GEMINI_25_FLASH_LITE, GEMINI_MODEL

_QUOTA_RE = re.compile(r"\b429\b|quota|rate[- ]?limit|resourceexhausted", re.I)


def is_quota_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}"
    return bool(_QUOTA_RE.search(text))


def chat_model_fallbacks(primary: Optional[str] = None) -> List[str]:
    """Models to try for chat when the primary hits quota or errors."""
    ordered = [
        primary,
        GEMINI_25_FLASH,
        GEMINI_25_FLASH_LITE,
        GEMINI_MODEL,
    ]
    seen: set[str] = set()
    out: List[str] = []
    for name in ordered:
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def user_facing_gemini_error(exc: Optional[BaseException]) -> str:
    if exc is None:
        return (
            "Lo siento, estoy teniendo dificultades técnicas. "
            "¿Puede intentarlo nuevamente?"
        )
    if is_quota_error(exc):
        return (
            "Límite de uso de la API de Gemini alcanzado (cuota gratuita). "
            "Espere un minuto y vuelva a intentar, o ponga en `.env`: "
            "`GEMINI_MODEL=gemini-2.5-flash-lite` y `ROUTING_MODEL=gemini-2.5-flash-lite` "
            "para repartir las peticiones entre modelos."
        )
    return (
        "Lo siento, estoy teniendo dificultades técnicas. "
        "¿Puede intentarlo nuevamente?"
    )


def extract_response_text(response: object) -> str:
    try:
        text = getattr(response, "text", None)
        if text:
            return str(text).strip()
    except ValueError:
        pass

    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) if content else None
        if parts:
            chunks = [
                str(getattr(p, "text", ""))
                for p in parts
                if getattr(p, "text", None)
            ]
            joined = "".join(chunks).strip()
            if joined:
                return joined

    feedback = getattr(response, "prompt_feedback", None)
    block = getattr(feedback, "block_reason", None) if feedback else None
    if block:
        raise RuntimeError(f"Respuesta bloqueada ({block})")

    raise RuntimeError("El modelo no devolvió texto")
