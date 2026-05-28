"""Flask application factory and webhook routes (request-scoped via ``g``).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

Rate limiting uses ``request.remote_addr``. When the app sits behind trusted reverse proxies,
set ``TRUSTED_PROXY_HOPS`` (see ``config``) so Werkzeug ``ProxyFix`` rewrites the remote address
safely; do not trust raw ``X-Forwarded-For`` from clients on direct connections.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional, cast

from flask import (
    Flask,
    current_app,
    g,
    jsonify,
    redirect,
    request,
    send_from_directory,
)
from flask.typing import ResponseReturnValue
from werkzeug.middleware.proxy_fix import ProxyFix

from .callbacks import callbacks as _callbacks
from .config import (
    GEMINI_MODEL,
    GOOGLE_API_KEY,
    MAX_AUDIO_BYTES,
    MAX_REQUEST_BYTES,
    MAX_TEXT_CHARS,
    SESSION_API_KEY,
    TRUSTED_PROXY_HOPS,
    WEBHOOK_API_KEY,
    WEBHOOK_RATE_LIMIT_PER_MINUTE,
    logger,
)
from .amadeus_client import amadeus_configured
from .transcribe import transcribe_audio
from .security import (
    extract_session_api_key,
    extract_webhook_secret,
    is_valid_session_id,
    validate_user_text_length,
    webhook_secret_matches,
)
from .throttler import SlidingWindowLimiter

def _webhook_authorized() -> bool:
    expected = (current_app.config.get("WEBHOOK_API_KEY") or "").strip()
    if not expected:
        return True
    provided = extract_webhook_secret(request)
    return webhook_secret_matches(expected, provided)


def _client_ip() -> str:
    """Client IP for rate limiting.

    With ``TRUSTED_PROXY_HOPS > 0``, ``ProxyFix`` adjusts ``request.remote_addr``.
    Without trusted proxies (hops=0), spoofed ``X-Forwarded-For`` is ignored.
    """
    return (request.remote_addr or "unknown")[:128]


def _pkg_static_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _repo_docs_dir() -> str:
    """Repository ``docs/`` folder (sibling of the Python package)."""
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
    )


def _apply_proxy_fix(app: Flask) -> None:
    hops = TRUSTED_PROXY_HOPS
    if hops <= 0:
        return
    app.wsgi_app = cast(
        Any,
        ProxyFix(
            app.wsgi_app,
            x_for=hops,
            x_proto=hops,
            x_host=hops,
            x_port=hops,
            x_prefix=hops,
        ),
    )
    logger.info(
        "ProxyFix enabled (%s trusted proxy hop(s)); rate limit uses remote_addr",
        hops,
    )


def create_app(
    agent: Any = None,
    session_manager: Any = None,
    voice_io: Any = None,
    webhook_api_key: Optional[str] = None,
) -> Flask:
    """Build the Flask app with assistant dependencies (test-friendly, no import-time globals)."""
    static_dir = _pkg_static_dir()
    app = Flask(
        __name__,
        static_folder=static_dir,
        static_url_path="/assets",
    )
    _apply_proxy_fix(app)
    app.config["TRUSTED_PROXY_HOPS"] = TRUSTED_PROXY_HOPS

    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    app.config["WEBHOOK_API_KEY"] = (
        WEBHOOK_API_KEY if webhook_api_key is None else (webhook_api_key or "")
    )
    app.extensions["assistant"] = {
        "agent": agent,
        "session_manager": session_manager,
        "voice_io": voice_io,
    }
    if WEBHOOK_RATE_LIMIT_PER_MINUTE > 0:
        app.extensions["webhook_limiter"] = SlidingWindowLimiter(
            WEBHOOK_RATE_LIMIT_PER_MINUTE, 60.0
        )
    else:
        app.extensions["webhook_limiter"] = None

    @app.before_request
    def _assistant_request_context() -> None:
        ext = app.extensions.get("assistant") or {}
        g.agent = ext.get("agent")
        g.session_manager = ext.get("session_manager")
        g.voice_io = ext.get("voice_io")

    @app.route("/demo")
    def demo_redirect() -> ResponseReturnValue:
        return redirect("/demo/", code=302)

    @app.route("/demo/", methods=["GET"])
    def demo_ui() -> ResponseReturnValue:
        """Interactive chat UI for manual testing and screen recording."""
        response = send_from_directory(os.path.join(static_dir, "demo"), "index.html")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.route("/docs/architecture", methods=["GET"])
    @app.route("/docs/architecture/", methods=["GET"])
    def architecture_diagram() -> ResponseReturnValue:
        """Mermaid architecture diagrams (HTML)."""
        return send_from_directory(_repo_docs_dir(), "architecture.html")

    @app.route("/webhook/transcribe", methods=["POST"])
    def webhook_transcribe() -> ResponseReturnValue:
        """Transcribe a short microphone recording via Gemini (no Chrome cloud STT)."""
        if not _webhook_authorized():
            return jsonify({"error": "Unauthorized"}), 401

        limiter = app.extensions.get("webhook_limiter")
        if limiter is not None and not limiter.allow(_client_ip()):
            return (
                jsonify(
                    {
                        "error": "Too many requests",
                        "retry_after_sec": 60,
                    }
                ),
                429,
            )

        if not GOOGLE_API_KEY:
            return jsonify({"error": "Transcription not available"}), 503

        upload = request.files.get("audio")
        if upload is None or not upload.filename:
            return jsonify({"error": "Missing audio file (field name: audio)"}), 400

        audio_bytes = upload.read()
        if not audio_bytes:
            return jsonify({"error": "Empty audio file"}), 400
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            return (
                jsonify(
                    {
                        "error": f"Audio exceeds {MAX_AUDIO_BYTES} bytes",
                        "max_bytes": MAX_AUDIO_BYTES,
                    }
                ),
                400,
            )

        mime_type = (upload.mimetype or "audio/webm").strip()
        try:
            text = transcribe_audio(
                api_key=GOOGLE_API_KEY,
                model_name=GEMINI_MODEL,
                audio_bytes=audio_bytes,
                mime_type=mime_type,
            )
            return jsonify(
                {
                    "text": text,
                    "timestamp": time.time(),
                }
            )
        except Exception as exc:
            if _callbacks.on_error:
                _callbacks.on_error(exc)
            logger.exception("Transcription failed")
            detail = str(exc).strip()[:240] or exc.__class__.__name__
            return (
                jsonify(
                    {
                        "error": "No se pudo transcribir el audio",
                        "detail": detail,
                    }
                ),
                500,
            )

    @app.route("/webhook/trigger", methods=["POST"])
    def webhook_trigger() -> ResponseReturnValue:
        if not _webhook_authorized():
            return jsonify({"error": "Unauthorized"}), 401

        limiter = app.extensions.get("webhook_limiter")
        if limiter is not None and not limiter.allow(_client_ip()):
            return (
                jsonify(
                    {
                        "error": "Too many requests",
                        "retry_after_sec": 60,
                    }
                ),
                429,
            )

        if not g.agent:
            return jsonify({"error": "Agent not available"}), 503

        if not request.is_json:
            return jsonify({"error": "Request body must be JSON"}), 400

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON payload"}), 400

        raw_text = data.get("text")
        if raw_text is not None and not isinstance(raw_text, str):
            return jsonify({"error": "Field 'text' must be a string"}), 400

        text = (
            raw_text
            if isinstance(raw_text, str) and raw_text.strip()
            else "Hola, necesito ayuda con una reserva de hotel"
        )

        ok, err = validate_user_text_length(text, MAX_TEXT_CHARS)
        if not ok:
            return (
                jsonify(
                    {
                        "error": err,
                        "max_chars": MAX_TEXT_CHARS,
                    }
                ),
                400,
            )

        raw_session_id = data.get("session_id")
        if raw_session_id is not None and not isinstance(raw_session_id, str):
            return jsonify({"error": "Field 'session_id' must be a string"}), 400

        session_id = (
            raw_session_id.strip()
            if isinstance(raw_session_id, str) and raw_session_id.strip()
            else None
        )
        if session_id is not None and not is_valid_session_id(session_id):
            return jsonify({"error": "Invalid session_id format"}), 400

        try:
            reply, resolved_session_id = g.agent.generate(text, session_id)
            return jsonify(
                {
                    "reply": reply,
                    "session_id": resolved_session_id,
                    "timestamp": time.time(),
                }
            )
        except Exception as exc:
            if _callbacks.on_error:
                _callbacks.on_error(exc)
            return jsonify({"error": "Internal error processing request"}), 500

    @app.route("/webhook/booking_event", methods=["POST"])
    def webhook_booking_event() -> ResponseReturnValue:
        if not _webhook_authorized():
            return jsonify({"error": "Unauthorized"}), 401

        if not request.is_json:
            return jsonify({"error": "Request body must be JSON"}), 400

        event = request.get_json(silent=True) or {}
        if not isinstance(event, dict):
            return jsonify({"error": "Invalid JSON payload"}), 400

        if _callbacks.on_confirm:
            _callbacks.on_confirm(event)
        return jsonify({"received": True, "timestamp": time.time()})

    @app.route("/health", methods=["GET"])
    def health_check() -> ResponseReturnValue:
        sm = g.session_manager
        n_sessions = (
            sm.count_sessions()
            if sm is not None and hasattr(sm, "count_sessions")
            else 0
        )
        return jsonify(
            {
                "status": "healthy" if g.agent else "unhealthy",
                "timestamp": time.time(),
                "sessions_active": n_sessions,
                "model": GEMINI_MODEL if g.agent else "none",
                "voice_available": bool(g.voice_io),
                "demo_ui": True,
                "architecture_diagram": True,
                "server_transcription": bool(GOOGLE_API_KEY),
                "amadeus_hotel_search": amadeus_configured(),
                "proxy_fix_hops": TRUSTED_PROXY_HOPS,
                "proxy_fix_active": TRUSTED_PROXY_HOPS > 0,
            }
        )

    @app.route("/session/<session_id>", methods=["GET"])
    def get_session_info(session_id: str) -> ResponseReturnValue:
        if not is_valid_session_id(session_id):
            return jsonify({"error": "Invalid session_id format"}), 400

        if SESSION_API_KEY:
            provided = extract_session_api_key(request)
            if not webhook_secret_matches(SESSION_API_KEY, provided):
                return jsonify({"error": "Unauthorized"}), 401

        sm = g.session_manager
        if sm is None:
            return jsonify({"error": "Session store unavailable"}), 503

        session = sm.get_session(session_id)
        if not session:
            return jsonify({"error": "Session not found"}), 404
        return jsonify(
            {
                "session_id": session.session_id,
                "user_id": session.user_id,
                "message_count": len(session.conversation_history),
                "last_activity": session.last_activity,
                "created_at": session.created_at,
            }
        )

    return app
