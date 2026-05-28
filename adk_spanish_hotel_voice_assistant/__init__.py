"""
ADK Spanish Hotel Reservation Voice Assistant
============================================

Spanish hotel reservation assistant backed by Google Gemini. Runs as a voice
kiosk, CLI, or Flask webhook service. Booking backends integrate via callbacks.

Implementation is split under this package; run with:

    python -m adk_spanish_hotel_voice_assistant

Author: Andres Lage
Copyright (c) 2026 Andres Lage. MIT License — see LICENSE at repository root.
"""

from __future__ import annotations

from typing import Any

from .agent import GeminiAgent
from .callbacks import Callbacks
from .config import GEMINI_35_FLASH, GEMINI_20_FLASH, GEMINI_MODEL
from .main import main
from .sessions import SessionManager, UserSession, create_session_store
from . import state
from .web import create_app

agent = state.agent
session_manager = state.session_manager
voice_io = state.voice_io
app = state.app

__all__ = [
    "GeminiAgent",
    "Callbacks",
    "callbacks",
    "SessionManager",
    "UserSession",
    "create_session_store",
    "create_app",
    "GEMINI_MODEL",
    "GEMINI_35_FLASH",
    "GEMINI_20_FLASH",
    "agent",
    "session_manager",
    "voice_io",
    "app",
    "main",
]


def __getattr__(name: str) -> Any:
    if name == "callbacks":
        from . import callbacks as cm

        return cm.callbacks
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
