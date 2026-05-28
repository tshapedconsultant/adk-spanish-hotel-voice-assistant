"""Flask application factory and request-scoped assistant handles.

Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from adk_spanish_hotel_voice_assistant.sessions import SessionManager
from adk_spanish_hotel_voice_assistant.web import create_app


def test_create_app_injects_agent_via_g():
    class StubAgent:
        def generate(self, text, session_id):
            # Valid UUID v4 shape for session_id validation in webhook layer
            return "stub-reply", "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

    sm = SessionManager(timeout_minutes=60)
    app = create_app(agent=StubAgent(), session_manager=sm, voice_io=None)
    client = app.test_client()

    h = client.get("/health")
    assert h.status_code == 200
    body = h.get_json()
    assert body["status"] == "healthy"
    assert body["sessions_active"] == 0

    r = client.post("/webhook/trigger", json={"text": "Hola"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["reply"] == "stub-reply"
    assert data["session_id"] == "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
