# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

from adk_spanish_hotel_voice_assistant.hotel_search import infer_ciudad_from_text
from adk_spanish_hotel_voice_assistant.routing import (
    ROUTING_JSON_SCHEMA,
    _normalize_routing_payload,
)


def test_routing_schema_declares_ciudad():
    props = ROUTING_JSON_SCHEMA["properties"]
    assert "ciudad" in props
    assert props["ciudad"]["type"] == "string"


def test_normalize_routing_extracts_ciudad():
    intent, entities = _normalize_routing_payload(
        {
            "intent": "price_inquiry",
            "ciudad": "Las Palmas",
            "check_in": "2026-06-15",
            "check_out": "2026-06-18",
        }
    )
    assert intent == "price_inquiry"
    assert entities["ciudad"] == "Las Palmas"


def test_infer_ciudad_from_text_fallback():
    assert infer_ciudad_from_text("Hoteles en Las Palmas del 15 al 18") == "Las Palmas"
