# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

from unittest.mock import patch

from werkzeug.middleware.proxy_fix import ProxyFix

from adk_spanish_hotel_voice_assistant.sessions import SessionManager
from adk_spanish_hotel_voice_assistant.web import create_app


def test_proxy_fix_not_wrapped_when_hops_zero():
    with patch("adk_spanish_hotel_voice_assistant.web.TRUSTED_PROXY_HOPS", 0):
        sm = SessionManager(timeout_minutes=60)
        app = create_app(agent=None, session_manager=sm, voice_io=None)
        assert not isinstance(app.wsgi_app, ProxyFix)


def test_proxy_fix_wrapped_when_hops_positive():
    with patch("adk_spanish_hotel_voice_assistant.web.TRUSTED_PROXY_HOPS", 1):
        sm = SessionManager(timeout_minutes=60)
        app = create_app(agent=None, session_manager=sm, voice_io=None)
        assert isinstance(app.wsgi_app, ProxyFix)
        assert app.config["TRUSTED_PROXY_HOPS"] == 1
