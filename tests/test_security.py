"""Security helpers and webhook hardening.

Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

import uuid

import pytest

from adk_spanish_hotel_voice_assistant.security import (
    clamp_user_text,
    is_valid_session_id,
    parse_guest_count,
    validate_user_text_length,
    webhook_secret_matches,
)
from adk_spanish_hotel_voice_assistant.sessions import SessionManager
from adk_spanish_hotel_voice_assistant.web import create_app


def test_is_valid_session_id_accepts_uuid4():
    sid = str(uuid.uuid4())
    assert is_valid_session_id(sid) is True


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-a-uuid",
        "../../../etc/passwd",
        "session-stable",
        "123e4567-e89b-12d3-a456-426614174000",  # version 1, not v4
    ],
)
def test_is_valid_session_id_rejects_malformed(bad):
    assert is_valid_session_id(bad) is False


def test_webhook_secret_matches_uses_digest():
    assert webhook_secret_matches("secret-a", "secret-a") is True
    assert webhook_secret_matches("secret-a", "secret-b") is False
    assert webhook_secret_matches("", "x") is True
    assert webhook_secret_matches("secret-a", None) is False
    assert webhook_secret_matches("secret-a", "") is False


def test_clamp_user_text_respects_limit():
    assert clamp_user_text("hello", 10) == "hello"
    assert clamp_user_text("hello world", 5) == "hello"


def test_validate_user_text_length():
    ok, err = validate_user_text_length("short", 10)
    assert ok is True
    assert err == ""
    ok, err = validate_user_text_length("x" * 11, 10)
    assert ok is False
    assert "10 characters" in err


def test_parse_guest_count_handles_bad_values():
    assert parse_guest_count(None) == 1
    assert parse_guest_count("2") == 2
    assert parse_guest_count("dos") == 1
    assert parse_guest_count("2 personas") == 1
    assert parse_guest_count(0) == 1
    assert parse_guest_count(-3) == 1


def test_webhook_requires_key_when_configured():
    class StubAgent:
        def generate(self, text, session_id):
            return "ok", str(uuid.uuid4())

    sm = SessionManager(timeout_minutes=60)
    app = create_app(
        agent=StubAgent(),
        session_manager=sm,
        voice_io=None,
        webhook_api_key="super-secret-key",
    )
    client = app.test_client()

    r = client.post("/webhook/trigger", json={"text": "Hola"})
    assert r.status_code == 401

    r2 = client.post(
        "/webhook/trigger",
        json={"text": "Hola"},
        headers={"X-Webhook-Key": "super-secret-key"},
    )
    assert r2.status_code == 200


def test_webhook_rejects_invalid_session_id():
    class StubAgent:
        def generate(self, text, session_id):
            return "ok", str(uuid.uuid4())

    sm = SessionManager(timeout_minutes=60)
    app = create_app(agent=StubAgent(), session_manager=sm, voice_io=None)
    client = app.test_client()

    r = client.post(
        "/webhook/trigger",
        json={"text": "Hola", "session_id": "'; DROP TABLE--"},
    )
    assert r.status_code == 400
    assert "session_id" in r.get_json().get("error", "").lower()


def test_webhook_rejects_oversized_text(monkeypatch):
    monkeypatch.setattr(
        "adk_spanish_hotel_voice_assistant.web.MAX_TEXT_CHARS",
        20,
        raising=False,
    )

    class StubAgent:
        def generate(self, text, session_id):
            return "ok", str(uuid.uuid4())

    sm = SessionManager(timeout_minutes=60)
    app = create_app(agent=StubAgent(), session_manager=sm, voice_io=None)
    client = app.test_client()

    r = client.post("/webhook/trigger", json={"text": "x" * 21})
    assert r.status_code == 400
    body = r.get_json()
    assert "20 characters" in body.get("error", "")
    assert body.get("max_chars") == 20


def test_session_endpoint_requires_api_key_when_configured(monkeypatch):
    monkeypatch.setattr(
        "adk_spanish_hotel_voice_assistant.web.SESSION_API_KEY",
        "inspect-secret",
        raising=False,
    )

    sm = SessionManager(timeout_minutes=60)
    session = sm.create_session()
    app = create_app(agent=None, session_manager=sm, voice_io=None)
    client = app.test_client()

    r = client.get(f"/session/{session.session_id}")
    assert r.status_code == 401

    r2 = client.get(
        f"/session/{session.session_id}",
        headers={"X-API-Key": "inspect-secret"},
    )
    assert r2.status_code == 200
    assert r2.get_json()["session_id"] == session.session_id
