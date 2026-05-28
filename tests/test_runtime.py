# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""CLI mode normalization."""

from adk_spanish_hotel_voice_assistant.runtime import normalize_cli_mode


def test_normalize_cli_mode_maps_legacy_aliases():
    assert normalize_cli_mode("text") == "text"
    assert normalize_cli_mode("chat") == "text"
    assert normalize_cli_mode("code") == "text"
    assert normalize_cli_mode("voice") == "voice"
