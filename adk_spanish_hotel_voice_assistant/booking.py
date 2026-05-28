"""Default booking handlers and callback wiring.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import requests

from . import callbacks as _callbacks_mod
from .amadeus_client import amadeus_configured
from .config import logger
from .security import parse_guest_count

_BOOKING_CONFIRM_RE = re.compile(
    r"\b("
    r"confirmo|confirma|sí,? confirmo|si,? confirmo|correcto|de acuerdo|"
    r"procede|proceder|haz la reserva|realiza la reserva|reserva confirmada|"
    r"adelante con la reserva|ok,? reserva"
    r")\b",
    re.IGNORECASE,
)

_REQUIRED_BOOKING_FIELDS = ("guest_name", "check_in", "check_out", "ciudad")

@dataclass
class ReservationRequest:
    guest_name: str = ""
    check_in: str = ""
    check_out: str = ""
    guests: int = 1
    room_type: str = ""
    session_id: str = ""
    extras: Dict[str, Any] = field(default_factory=dict)


def reservation_snapshot_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ``current_reservation`` with top-level entity fields from the turn payload."""
    cr = payload.get("current_reservation")
    merged: Dict[str, Any] = dict(cr) if isinstance(cr, dict) else {}
    entities = payload.get("extracted_entities")
    if isinstance(entities, dict):
        for key in ("guest_name", "check_in", "check_out", "room_type", "ciudad"):
            value = entities.get(key)
            if value is not None and str(value).strip():
                merged[key] = str(value).strip()
        guests = entities.get("guests")
        if isinstance(guests, int) and guests > 0:
            merged["guests"] = guests
    return merged


def reservation_missing_fields(reservation: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for field_name in _REQUIRED_BOOKING_FIELDS:
        if not str(reservation.get(field_name) or "").strip():
            missing.append(field_name)
    return missing


def user_confirmed_booking(user_input: str) -> bool:
    return bool(_BOOKING_CONFIRM_RE.search(user_input or ""))


def should_invoke_booking_handler(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Gate booking hooks until required fields exist and the user explicitly confirms."""
    reservation = reservation_snapshot_from_payload(payload)
    missing = reservation_missing_fields(reservation)
    if missing:
        return False, "incomplete:" + ",".join(missing)
    if not user_confirmed_booking(str(payload.get("user_input") or "")):
        return False, "awaiting_confirmation"
    return True, "ready"


def default_booking_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        ready, reason = should_invoke_booking_handler(payload)
        if not ready:
            reservation = reservation_snapshot_from_payload(payload)
            return {
                "status": "skipped",
                "reason": reason,
                "missing_fields": reservation_missing_fields(reservation),
                "session_id": str(payload.get("session_id", "")),
                "message": (
                    "Reserva no ejecutada: faltan datos obligatorios o confirmación explícita "
                    "del huésped."
                ),
            }

        merged = reservation_snapshot_from_payload(payload)
        def _pick(*keys: str) -> Any:
            for k in keys:
                v = payload.get(k)
                if v is not None and v != "":
                    return v
                v = merged.get(k)
                if v is not None and v != "":
                    return v
            return merged.get(keys[0]) if keys else None

        guest_name = str(_pick("guest_name") or "")
        check_in = str(_pick("check_in") or "")
        check_out = str(_pick("check_out") or "")
        room_type = str(_pick("room_type") or "")
        guests_val = _pick("guests")
        guests = parse_guest_count(guests_val, default=1)

        _reserved = {
            "guest_name",
            "check_in",
            "check_out",
            "guests",
            "room_type",
            "session_id",
            "user_input",
            "assistant_response",
            "detected_intent",
            "extracted_entities",
            "current_reservation",
            "booking_result",
            "timestamp",
        }
        reservation = ReservationRequest(
            guest_name=guest_name,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            room_type=room_type,
            session_id=str(payload.get("session_id", "")),
            extras={k: v for k, v in payload.items() if k not in _reserved},
        )
        booking_api = os.getenv("HOTEL_BOOKING_API")
        if booking_api:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('HOTEL_API_TOKEN', '')}",
            }
            resp = requests.post(
                booking_api,
                json={
                    "guest_name": reservation.guest_name,
                    "check_in": reservation.check_in,
                    "check_out": reservation.check_out,
                    "guests": reservation.guests,
                    "room_type": reservation.room_type,
                    "session_id": reservation.session_id,
                    "extras": reservation.extras,
                },
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

        if amadeus_configured():
            search = payload.get("amadeus_search")
            offer_id = ""
            if isinstance(search, dict) and search.get("ok"):
                hotels = search.get("hoteles") or []
                if hotels and isinstance(hotels[0], dict):
                    offer_id = str(hotels[0].get("offer_id") or "")
            return {
                "status": "pending",
                "session_id": reservation.session_id,
                "message": (
                    "Búsqueda Amadeus realizada. La reserva definitiva requiere "
                    "confirmar un offer_id de Amadeus Hotel Booking API"
                    + (f" (ej. {offer_id})" if offer_id else "")
                    + ". Mientras tanto se registran los datos del huésped."
                ),
                "amadeus_offer_id": offer_id or None,
                "timestamp": time.time(),
            }

        if os.getenv("FLASK_ENV") == "production":
            raise RuntimeError(
                "Sin HOTEL_BOOKING_API ni Amadeus: no ejecutar reserva simulada en producción"
            )

        logger.info("Simulated booking created for session %s", reservation.session_id)
        return {
            "status": "success",
            "reservation_id": f"SIM-{int(time.time())}",
            "session_id": reservation.session_id,
            "message": "Reserva simulada creada (configure Amadeus o HOTEL_BOOKING_API)",
            "timestamp": time.time(),
        }
    except Exception as exc:
        cb = _callbacks_mod.callbacks
        if cb.on_error:
            cb.on_error(exc)
        return {"status": "failed", "message": str(exc)}


def booking_confirmed_handler(event: Dict[str, Any]) -> None:
    reservation_id = event.get("reservation_id", "N/A")
    session_id = event.get("session_id", "N/A")
    logger.info("Reserva confirmada - ID: %s, Sesión: %s", reservation_id, session_id)


def generic_error_handler(exc: Exception) -> None:
    logger.error("[ERROR CALLBACK] %s: %s", type(exc).__name__, exc)


_callbacks_mod.callbacks.on_booking_request = default_booking_handler
_callbacks_mod.callbacks.on_confirm = booking_confirmed_handler
_callbacks_mod.callbacks.on_error = generic_error_handler
