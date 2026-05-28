"""Pluggable callback hooks for intents, booking, and errors.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class Callbacks:
    on_intent: Optional[Callable[[Dict[str, Any]], None]] = None
    on_booking_request: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    on_confirm: Optional[Callable[[Dict[str, Any]], None]] = None
    on_error: Optional[Callable[[Exception], None]] = None


callbacks = Callbacks()
