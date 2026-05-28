# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""Transcription endpoint and helpers."""

from io import BytesIO

from adk_spanish_hotel_voice_assistant.sessions import SessionManager
from adk_spanish_hotel_voice_assistant.transcribe import (
    normalize_audio_mime,
    transcribe_model_candidates,
)
from adk_spanish_hotel_voice_assistant.web import create_app


def test_transcribe_model_candidates_prefers_flash_20():
    models = transcribe_model_candidates("gemini-3.5-flash")
    assert models[0] == "gemini-2.0-flash"
    assert "gemini-3.5-flash" in models


def test_normalize_audio_mime_strips_codec():
    assert normalize_audio_mime("audio/webm;codecs=opus") == "audio/webm"


def test_webhook_transcribe_returns_text(monkeypatch):
    monkeypatch.setattr(
        "adk_spanish_hotel_voice_assistant.web.GOOGLE_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        "adk_spanish_hotel_voice_assistant.web.transcribe_audio",
        lambda **_: "Quiero una habitación doble",
    )

    sm = SessionManager(timeout_minutes=60)
    app = create_app(agent=None, session_manager=sm, voice_io=None)
    client = app.test_client()

    data = {"audio": (BytesIO(b"fake-audio-bytes"), "test.webm")}
    r = client.post(
        "/webhook/transcribe",
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["text"] == "Quiero una habitación doble"


def test_webhook_transcribe_rejects_empty(monkeypatch):
    monkeypatch.setattr(
        "adk_spanish_hotel_voice_assistant.web.GOOGLE_API_KEY",
        "test-key",
    )
    sm = SessionManager(timeout_minutes=60)
    app = create_app(agent=None, session_manager=sm, voice_io=None)
    client = app.test_client()

    data = {"audio": (BytesIO(b""), "empty.webm")}
    r = client.post(
        "/webhook/transcribe",
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
