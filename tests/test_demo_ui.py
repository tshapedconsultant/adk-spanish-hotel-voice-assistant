# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""Smoke tests for the /demo web UI."""

from adk_spanish_hotel_voice_assistant.sessions import SessionManager
from adk_spanish_hotel_voice_assistant.web import create_app


def test_demo_page_loads():
    sm = SessionManager(timeout_minutes=60)
    app = create_app(agent=None, session_manager=sm, voice_io=None)
    client = app.test_client()
    r = client.get("/demo/", follow_redirects=False)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Asistente de reservas" in html
    assert "webhook/trigger" in html
    assert "/webhook/transcribe" in html
    assert 'id="mic"' in html


def test_demo_redirect():
    sm = SessionManager(timeout_minutes=60)
    app = create_app(agent=None, session_manager=sm, voice_io=None)
    client = app.test_client()
    r = client.get("/demo", follow_redirects=False)
    assert r.status_code == 302
    assert "/demo/" in r.location
