# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""Configuration helpers for Gemini model IDs."""

from adk_spanish_hotel_voice_assistant.config import (
    GEMINI_20_FLASH,
    GEMINI_25_FLASH_LITE,
    GEMINI_35_FLASH,
    KNOWN_GEMINI_MODELS,
    is_preview_gemini_model,
    normalize_gemini_model_id,
)


def test_default_model_is_gemini_35_flash(monkeypatch):
    """Default applies when GEMINI_MODEL is not set in the environment."""
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    import importlib

    from adk_spanish_hotel_voice_assistant import config

    importlib.reload(config)
    assert config.GEMINI_MODEL == config.GEMINI_35_FLASH


def test_default_routing_model_is_25_flash_lite(monkeypatch):
    monkeypatch.delenv("ROUTING_MODEL", raising=False)
    import importlib

    from adk_spanish_hotel_voice_assistant import config

    importlib.reload(config)
    assert config.ROUTING_MODEL == config.GEMINI_25_FLASH_LITE


def test_gemini_35_flash_is_known():
    assert GEMINI_35_FLASH == "gemini-3.5-flash"
    assert GEMINI_35_FLASH in KNOWN_GEMINI_MODELS


def test_normalize_strips_whitespace():
    assert normalize_gemini_model_id("  gemini-3.5-flash  ") == GEMINI_35_FLASH


def test_preview_detection():
    assert is_preview_gemini_model("gemini-3-flash-preview")
    assert is_preview_gemini_model("something-exp")
    assert not is_preview_gemini_model(GEMINI_20_FLASH)
