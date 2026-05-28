# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""Booking handler edge cases and completeness gate."""

from adk_spanish_hotel_voice_assistant.booking import (
    default_booking_handler,
    reservation_missing_fields,
    should_invoke_booking_handler,
    user_confirmed_booking,
)


def test_should_not_book_on_vague_intent_only():
    payload = {
        "session_id": "s1",
        "user_input": "Quiero reservar un hotel",
        "current_reservation": {},
        "extracted_entities": {},
    }
    ok, reason = should_invoke_booking_handler(payload)
    assert ok is False
    assert reason.startswith("incomplete:")


def test_should_book_when_complete_and_confirmed():
    payload = {
        "session_id": "s1",
        "user_input": "Confirmo la reserva",
        "current_reservation": {
            "guest_name": "Ana García",
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
            "ciudad": "Madrid",
        },
        "extracted_entities": {},
    }
    ok, reason = should_invoke_booking_handler(payload)
    assert ok is True
    assert reason == "ready"


def test_complete_data_without_confirmation_is_skipped():
    payload = {
        "session_id": "s1",
        "user_input": "Quiero reservar del 1 al 3 de junio en Madrid",
        "current_reservation": {
            "guest_name": "Ana",
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
            "ciudad": "Madrid",
        },
    }
    ok, reason = should_invoke_booking_handler(payload)
    assert ok is False
    assert reason == "awaiting_confirmation"


def test_default_booking_handler_tolerates_non_numeric_guests():
    result = default_booking_handler(
        {
            "session_id": "test-session",
            "user_input": "Confirmo",
            "guests": "dos",
            "guest_name": "Ana",
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
            "ciudad": "Madrid",
            "current_reservation": {
                "guest_name": "Ana",
                "check_in": "2026-06-01",
                "check_out": "2026-06-03",
                "ciudad": "Madrid",
            },
        }
    )
    assert result["status"] in ("success", "pending", "skipped", "failed")
    if result["status"] == "success":
        assert result.get("session_id") == "test-session"


def test_default_booking_handler_skips_incomplete():
    result = default_booking_handler(
        {
            "session_id": "test-session",
            "user_input": "Quiero reservar",
            "current_reservation": {},
        }
    )
    assert result["status"] == "skipped"
    assert "guest_name" in result["missing_fields"]


def test_user_confirmed_booking_phrases():
    assert user_confirmed_booking("Sí, confirmo la reserva") is True
    assert user_confirmed_booking("solo estoy preguntando") is False


def test_reservation_missing_fields():
    assert reservation_missing_fields({}) == [
        "guest_name",
        "check_in",
        "check_out",
        "ciudad",
    ]
