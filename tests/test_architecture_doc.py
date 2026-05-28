# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""Smoke tests for the Mermaid architecture HTML page."""

from pathlib import Path

from adk_spanish_hotel_voice_assistant.sessions import SessionManager
from adk_spanish_hotel_voice_assistant.web import create_app


def test_architecture_html_exists_in_repo():
    path = Path(__file__).resolve().parents[1] / "docs" / "architecture.html"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "mermaid" in text
    assert "flowchart" in text


def test_architecture_route_serves_html():
    sm = SessionManager(timeout_minutes=60)
    app = create_app(agent=None, session_manager=sm, voice_io=None)
    client = app.test_client()
    r = client.get("/docs/architecture")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Arquitectura del asistente" in html
    assert "sequenceDiagram" in html
