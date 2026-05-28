"""Gemini function-calling declarations for hotel search.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .config import HAS_GEMINI, genai
from .gemini_errors import extract_response_text
from .hotel_search import HOTEL_SEARCH_FUNCTION_NAME, buscar_disponibilidad_hotel

HOTEL_SEARCH_DECLARATION: Dict[str, Any] = {
    "name": HOTEL_SEARCH_FUNCTION_NAME,
    "description": (
        "Consulta disponibilidad y precios reales de hoteles en una ciudad "
        "para fechas concretas mediante Amadeus GDS. "
        "Úsala cuando el usuario pida precios, tarifas, disponibilidad u ofertas."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ciudad": {
                "type": "string",
                "description": "Ciudad destino, ej. Las Palmas, Madrid, Barcelona.",
            },
            "check_in": {
                "type": "string",
                "description": "Fecha de entrada YYYY-MM-DD.",
            },
            "check_out": {
                "type": "string",
                "description": "Fecha de salida YYYY-MM-DD.",
            },
            "huespedes": {
                "type": "integer",
                "description": "Número de adultos (por defecto 1).",
            },
        },
        "required": ["ciudad", "check_in", "check_out"],
    },
}


def format_amadeus_context_for_prompt(result: Dict[str, Any]) -> str:
    """Inject Amadeus JSON into the user turn so Gemini cites real prices only."""
    return (
        "\n\n--- DATOS REALES AMADEUS (no inventar precios ni nombres de hotel) ---\n"
        f"{json.dumps(result, ensure_ascii=False, indent=2)}\n"
        "--- Fin datos Amadeus. Cite solo estos precios si hay hoteles; "
        "si la lista está vacía, explíquelo al usuario. ---"
    )


def parse_function_call(response: Any) -> Optional[Dict[str, Any]]:
    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        parts = getattr(candidates[0].content, "parts", None) or []
        for part in parts:
            fc = getattr(part, "function_call", None)
            if fc is None:
                continue
            name = getattr(fc, "name", "") or ""
            args = getattr(fc, "args", None)
            if args is None:
                return {"name": name, "args": {}}
            if hasattr(args, "items"):
                return {"name": name, "args": dict(args)}
            if isinstance(args, dict):
                return {"name": name, "args": args}
    except (AttributeError, IndexError, TypeError):
        return None
    return None


def execute_hotel_function(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name != HOTEL_SEARCH_FUNCTION_NAME:
        return {"ok": False, "error": f"función desconocida: {name}"}
    return buscar_disponibilidad_hotel(
        ciudad=str(args.get("ciudad") or ""),
        check_in=str(args.get("check_in") or ""),
        check_out=str(args.get("check_out") or ""),
        huespedes=int(args.get("huespedes") or args.get("guests") or 1),
    )


def build_hotel_tool() -> Any:
    if not HAS_GEMINI:
        raise RuntimeError("google-generativeai required for hotel tools")
    decl = genai.types.FunctionDeclaration(**HOTEL_SEARCH_DECLARATION)
    return genai.types.Tool(function_declarations=[decl])


def send_function_response(chat_session: Any, name: str, result: Dict[str, Any]) -> Any:
    """Send tool result back to Gemini chat session."""
    part = {
        "function_response": {
            "name": name,
            "response": result,
        }
    }
    return chat_session.send_message(part)


def run_chat_with_hotel_tools(
    *,
    model_name: str,
    system_prompt: str,
    history: List[Dict[str, Any]],
    user_input: str,
    generation_config: Any,
    max_tool_rounds: int = 3,
) -> str:
    if not HAS_GEMINI:
        raise RuntimeError("google-generativeai is not installed")

    tool = build_hotel_tool()
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt,
        tools=[tool],
    )
    chat = model.start_chat(history=history)
    kwargs: Dict[str, Any] = {}
    if generation_config is not None:
        kwargs["generation_config"] = generation_config

    response = chat.send_message(user_input, **kwargs)
    for _ in range(max_tool_rounds):
        call = parse_function_call(response)
        if not call:
            return extract_response_text(response)
        result = execute_hotel_function(call["name"], call.get("args") or {})
        response = send_function_response(chat, call["name"], result)
    return extract_response_text(response)
