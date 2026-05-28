# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""TTS interrupt behaviour (no real pyttsx3)."""

import queue
from unittest.mock import MagicMock, patch

from adk_spanish_hotel_voice_assistant import voice as voice_mod


@patch.object(voice_mod, "HAS_TTS", True)
@patch.object(voice_mod, "HAS_SR", True)
@patch.object(voice_mod, "sr", MagicMock())
@patch.object(voice_mod, "pyttsx3")
def test_interrupt_stops_engine_and_drains_queue(mock_pyttsx3):
    engine = MagicMock()
    mock_pyttsx3.init.return_value = engine

    vio = voice_mod.VoiceIO()
    vio._tts_queue.put("frase pendiente uno")
    vio._tts_queue.put("frase pendiente dos")

    vio.interrupt()

    engine.stop.assert_called()
    assert vio._tts_queue.empty()

    vio.shutdown()
