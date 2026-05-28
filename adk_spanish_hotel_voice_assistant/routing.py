"""Structured intent + entity extraction via Gemini (JSON schema or function calling).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from .config import HAS_GEMINI, genai, logger

ROUTING_FUNCTION_NAME = "emit_turn_routing"

INTENT_ENUM = [
    "booking_request",
    "greeting",
    "gratitude",
    "price_inquiry",
    "cancellation_request",
    "smalltalk",
    "unknown",
]

ROUTING_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": INTENT_ENUM,
            "description": "Primary user intent for this turn.",
        },
        "guest_name": {
            "type": "string",
            "description": "Guest full name if stated, else empty.",
        },
        "check_in": {
            "type": "string",
            "description": "Check-in date as YYYY-MM-DD if parseable, else original phrase or empty.",
        },
        "check_out": {
            "type": "string",
            "description": "Check-out date as YYYY-MM-DD if parseable, else original phrase or empty.",
        },
        "guests": {
            "type": "integer",
            "description": "Number of guests if mentioned; omit or 0 if unknown.",
        },
        "room_type": {
            "type": "string",
            "description": "Room category (suite, doble, individual, etc.) if mentioned.",
        },
        "ciudad": {
            "type": "string",
            "description": "Destination city if stated (e.g. Las Palmas, Madrid), else empty.",
        },
    },
    "required": ["intent"],
}

_ROUTING_PROMPT = """Eres un analizador para un asistente de reservas hoteleras en español.
Del mensaje del usuario, determina la intención principal y extrae solo datos explícitos de reserva:
fechas (check_in, check_out), ciudad de destino (ciudad), huéspedes, tipo de habitación y nombre.
No inventes fechas, ciudades ni nombres. Usa cadena vacía o 0 para campos desconocidos.
Mensaje del usuario:
"""


def _normalize_routing_payload(data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    raw_intent = data.get("intent")
    if not isinstance(raw_intent, str):
        return "unknown", {}
    intent = raw_intent.strip().lower()
    if intent not in INTENT_ENUM:
        intent = "unknown"

    guests = data.get("guests")
    if guests is None:
        guests_val = 0
    elif isinstance(guests, (int, float)):
        guests_val = max(0, int(guests))
    else:
        guests_val = 0

    entities = {
        "guest_name": _str_field(data.get("guest_name")),
        "check_in": _str_field(data.get("check_in")),
        "check_out": _str_field(data.get("check_out")),
        "guests": guests_val,
        "room_type": _str_field(data.get("room_type")),
        "ciudad": _str_field(data.get("ciudad")),
    }
    return intent, entities


def _str_field(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return str(val).strip()


def _parse_function_call_args(response: Any) -> Optional[Dict[str, Any]]:
    try:
        cands = getattr(response, "candidates", None) or []
        if not cands:
            return None
        parts = getattr(cands[0].content, "parts", None) or []
        for part in parts:
            fc = getattr(part, "function_call", None)
            if fc is None:
                continue
            name = getattr(fc, "name", "") or ""
            if name != ROUTING_FUNCTION_NAME:
                continue
            args = getattr(fc, "args", None)
            if args is None:
                return None
            if hasattr(args, "items"):
                return dict(args)
            if isinstance(args, dict):
                return args
    except (AttributeError, IndexError, TypeError) as exc:
        logger.debug("function_call parse skipped: %s", exc)
    return None


class RoutingService:
    """Calls Gemini with structured output or a forced function call to classify + extract."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        *,
        use_function_call: bool = False,
    ):
        if not HAS_GEMINI:
            raise RuntimeError("google-generativeai required for routing")
        genai.configure(api_key=api_key)
        self._use_function_call = use_function_call
        self._model_name = model_name

        if use_function_call:
            decl = genai.types.FunctionDeclaration(
                name=ROUTING_FUNCTION_NAME,
                description=(
                    "Emit the user's intent and any reservation-related entities "
                    "extracted from their Spanish message."
                ),
                parameters={
                    "type": "object",
                    "properties": ROUTING_JSON_SCHEMA["properties"],
                    "required": ["intent"],
                },
            )
            tool = genai.types.Tool(function_declarations=[decl])
            self._model = genai.GenerativeModel(
                self._model_name,
                tools=[tool],
                tool_config={
                    "function_calling_config": {
                        "mode": "ANY",
                        "allowed_function_names": [ROUTING_FUNCTION_NAME],
                    }
                },
            )
            self._json_config = None
        else:
            self._json_config = genai.types.GenerationConfig(
                temperature=0.15,
                response_mime_type="application/json",
                response_schema=ROUTING_JSON_SCHEMA,
            )
            self._model = genai.GenerativeModel(
                self._model_name,
                generation_config=self._json_config,
            )

    def route(self, user_input: str) -> Tuple[str, Dict[str, Any]]:
        prompt = _ROUTING_PROMPT + user_input.strip()
        try:
            if self._use_function_call:
                response = self._model.generate_content(prompt)
                args = _parse_function_call_args(response)
                if args:
                    return _normalize_routing_payload(args)
            else:
                response = self._model.generate_content(prompt)
                text = (response.text or "").strip()
                data = json.loads(text)
                if isinstance(data, dict):
                    return _normalize_routing_payload(data)
        except (json.JSONDecodeError, ValueError, AttributeError) as exc:
            logger.debug("Structured routing failed: %s", exc)
        except Exception as exc:
            logger.warning("Routing API error: %s", exc)
        return "unknown", {}
