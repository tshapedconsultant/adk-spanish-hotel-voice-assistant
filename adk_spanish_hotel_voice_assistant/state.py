"""Process-wide composition: session store, agent, voice, and Flask app.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

from typing import Optional

from . import booking  # noqa: F401 - register default callbacks
from .agent import GeminiAgent
from .config import (
    GEMINI_20_FLASH,
    GEMINI_35_FLASH,
    GEMINI_MODEL,
    GOOGLE_API_KEY,
    KNOWN_GEMINI_MODELS,
    SYSTEM_PROMPT_ES,
    is_preview_gemini_model,
    logger,
)
from .sessions import create_session_store
from .voice import VoiceIO, try_init_voice_io
from .web import create_app

session_manager = create_session_store()

agent: Optional[GeminiAgent] = None
if GOOGLE_API_KEY:
    try:
        agent = GeminiAgent(
            system_prompt=SYSTEM_PROMPT_ES,
            api_key=GOOGLE_API_KEY,
            session_manager=session_manager,
        )
        logger.info("Gemini Agent initialized with model: %s", GEMINI_MODEL)
        if is_preview_gemini_model(GEMINI_MODEL):
            logger.warning(
                "Using preview/experimental Gemini model '%s'. "
                "Consider a stable ID such as %s or %s for production.",
                GEMINI_MODEL,
                GEMINI_35_FLASH,
                GEMINI_20_FLASH,
            )
        elif GEMINI_MODEL not in KNOWN_GEMINI_MODELS:
            logger.warning(
                "GEMINI_MODEL '%s' is not in the built-in known list; "
                "verify API access and upgrade google-generativeai if calls fail.",
                GEMINI_MODEL,
            )
    except Exception as exc:
        logger.exception("Failed to initialize Gemini Agent: %s", exc)
else:
    logger.warning("GOOGLE_API_KEY not configured.")

voice_io: Optional[VoiceIO] = try_init_voice_io()

app = create_app(
    agent=agent,
    session_manager=session_manager,
    voice_io=voice_io,
)
