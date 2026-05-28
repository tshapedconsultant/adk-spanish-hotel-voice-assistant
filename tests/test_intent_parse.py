"""Regression tests for LLM intent JSON parsing edge cases.

Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from adk_spanish_hotel_voice_assistant.agent import GeminiAgent


def test_parse_intent_strips_markdown_fence():
    text = '```json\n{"intent": "greeting"}\n```'
    assert GeminiAgent._parse_intent_response(text) == "greeting"


def test_parse_intent_regex_fallback_when_json_is_noisy():
    text = 'Claro. {"intent": "price_inquiry"} es lo que necesito.'
    assert GeminiAgent._parse_intent_response(text) == "price_inquiry"


def test_parse_intent_normalizes_case():
    text = '{"intent": "PRICE_INQUIRY"}'
    assert GeminiAgent._parse_intent_response(text) == "price_inquiry"
