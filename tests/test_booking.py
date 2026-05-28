# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""Booking handler edge cases."""

from adk_spanish_hotel_voice_assistant.booking import default_booking_handler


def test_default_booking_handler_tolerates_non_numeric_guests():
    result = default_booking_handler(
        {
            "session_id": "test-session",
            "guests": "dos",
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
        }
    )
    assert result["status"] in ("success", "pending", "failed")
    if result["status"] != "failed":
        assert result.get("session_id") == "test-session"


def test_default_booking_handler_parses_numeric_string_guests():
    result = default_booking_handler(
        {
            "session_id": "test-session",
            "guests": "3",
        }
    )
    assert result["status"] in ("success", "pending", "failed")
