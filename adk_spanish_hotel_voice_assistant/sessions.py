"""Session storage: in-process (single node) or Redis (horizontal scale).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import (
    REDIS_KEY_PREFIX,
    REDIS_URL,
    SESSION_TIMEOUT_MINUTES,
    logger,
)

try:
    import redis as redis_lib

    HAS_REDIS = True
except ImportError:  # pragma: no cover - optional dependency
    redis_lib = None  # type: ignore
    HAS_REDIS = False


@dataclass
class UserSession:
    """Conversation context container stored per user."""

    session_id: str
    user_id: Optional[str] = None
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    current_reservation: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def add_message(self, role: str, content: str) -> None:
        """Track a chat message and retain only the most recent turns."""
        self.conversation_history.append({"role": role, "content": content})
        self.conversation_history = self.conversation_history[-20:]
        self.last_activity = time.time()


def user_session_to_dict(session: UserSession) -> Dict[str, Any]:
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "conversation_history": session.conversation_history,
        "current_reservation": session.current_reservation,
        "created_at": session.created_at,
        "last_activity": session.last_activity,
    }


def user_session_from_dict(data: Dict[str, Any]) -> UserSession:
    return UserSession(
        session_id=str(data["session_id"]),
        user_id=data.get("user_id"),
        conversation_history=list(data.get("conversation_history") or []),
        current_reservation=data.get("current_reservation"),
        created_at=float(data.get("created_at") or time.time()),
        last_activity=float(data.get("last_activity") or time.time()),
    )


class SessionManager:
    """In-memory session tracker with background cleanup (single process)."""

    def __init__(self, timeout_minutes: Optional[int] = None):
        tm = (
            timeout_minutes if timeout_minutes is not None else SESSION_TIMEOUT_MINUTES
        )
        self.sessions: Dict[str, UserSession] = {}
        self.timeout = tm * 60
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True
        )
        self._cleanup_thread.start()

    def create_session(self, user_id: Optional[str] = None) -> UserSession:
        with self._lock:
            session = UserSession(session_id=str(uuid.uuid4()), user_id=user_id)
            self.sessions[session.session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[UserSession]:
        with self._lock:
            return self.sessions.get(session_id)

    def put_session(self, session: UserSession) -> None:
        """Persist updates (no-op reference for in-memory; Redis store overwrites)."""
        with self._lock:
            self.sessions[session.session_id] = session

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self.sessions.pop(session_id, None)

    def count_sessions(self) -> int:
        with self._lock:
            return len(self.sessions)

    def cleanup_expired_sessions(self, now: Optional[float] = None) -> None:
        """Public helper mainly used by tests."""
        now = now or time.time()
        with self._lock:
            expired = [
                sid
                for sid, sess in self.sessions.items()
                if now - sess.last_activity > self.timeout
            ]
            for sid in expired:
                self.sessions.pop(sid, None)

    def _cleanup_loop(self) -> None:  # pragma: no cover - background loop
        while True:
            time.sleep(300)
            self.cleanup_expired_sessions()


class RedisSessionStore:
    """Distributed session storage with TTL (share state across Waitress workers / replicas)."""

    def __init__(
        self,
        url: str,
        *,
        key_prefix: str = REDIS_KEY_PREFIX,
        timeout_minutes: Optional[int] = None,
    ):
        if not HAS_REDIS or redis_lib is None:
            raise RuntimeError("redis package required; pip install redis")
        self._r = redis_lib.Redis.from_url(url, decode_responses=True)
        self._prefix = key_prefix
        tm = (
            timeout_minutes
            if timeout_minutes is not None
            else SESSION_TIMEOUT_MINUTES
        )
        self._ttl_seconds = max(60, tm * 60)

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def create_session(self, user_id: Optional[str] = None) -> UserSession:
        session = UserSession(session_id=str(uuid.uuid4()), user_id=user_id)
        raw = json.dumps(user_session_to_dict(session), ensure_ascii=False)
        self._r.setex(self._key(session.session_id), self._ttl_seconds, raw)
        return session

    def get_session(self, session_id: str) -> Optional[UserSession]:
        raw = self._r.get(self._key(session_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            sess = user_session_from_dict(data)
            self._r.expire(self._key(session_id), self._ttl_seconds)
            return sess
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Corrupt session %s: %s", session_id, exc)
            return None

    def put_session(self, session: UserSession) -> None:
        session.last_activity = time.time()
        raw = json.dumps(user_session_to_dict(session), ensure_ascii=False)
        self._r.setex(self._key(session.session_id), self._ttl_seconds, raw)

    def delete_session(self, session_id: str) -> None:
        self._r.delete(self._key(session_id))

    def count_sessions(self) -> int:
        n = 0
        for _ in self._r.scan_iter(match=f"{self._prefix}*", count=100):
            n += 1
        return n

    def cleanup_expired_sessions(self, now: Optional[float] = None) -> None:
        """Redis TTL handles expiry; optional manual sweep of missing keys is unnecessary."""
        del now


def create_session_store() -> SessionManager | RedisSessionStore:
    """Memory by default; set REDIS_URL for multi-process / multi-instance deployments."""
    url = REDIS_URL.strip() if REDIS_URL else ""
    if url:
        if not HAS_REDIS:
            logger.error(
                "REDIS_URL is set but redis is not installed; falling back to in-memory sessions."
            )
            return SessionManager()
        try:
            store = RedisSessionStore(url)
            logger.info("Session store: Redis (%s)", url.split("@")[-1])
            return store
        except Exception as exc:
            logger.exception("Redis connection failed; using in-memory sessions: %s", exc)
            return SessionManager()
    return SessionManager()
