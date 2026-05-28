# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

from adk_spanish_hotel_voice_assistant.gemini_errors import (
    chat_model_fallbacks,
    is_quota_error,
    user_facing_gemini_error,
)


def test_is_quota_error_detects_429():
    assert is_quota_error(Exception("429 quota exceeded"))


def test_user_facing_quota_message():
    msg = user_facing_gemini_error(Exception("ResourceExhausted 429 quota"))
    assert "Límite de uso" in msg
    assert "gemini-2.5-flash-lite" in msg


def test_chat_fallback_includes_25_flash():
    models = chat_model_fallbacks("gemini-3.5-flash")
    assert models[0] == "gemini-3.5-flash"
    assert "gemini-2.5-flash" in models
