# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

import time

from adk_spanish_hotel_voice_assistant import SessionManager


def test_session_cleanup_removes_expired_sessions():
    manager = SessionManager(timeout_minutes=0)  # immediate expiration
    session = manager.create_session()

    # Force last activity in the past
    session.last_activity = time.time() - 100

    manager.cleanup_expired_sessions(now=time.time())

    assert manager.get_session(session.session_id) is None


