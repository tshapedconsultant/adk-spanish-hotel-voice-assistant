"""Security helpers and webhook hardening.

Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

import uuid

import pytest

from adk_spanish_hotel_voice_assistant.security import (
    is_valid_session_id,
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
