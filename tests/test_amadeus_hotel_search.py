# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

"""Amadeus hotel search (mocked HTTP)."""

from unittest.mock import MagicMock, patch

from adk_spanish_hotel_voice_assistant.hotel_search import (
    buscar_disponibilidad_hotel,
    resolve_city_iata,
)


def test_resolve_city_iata_las_palmas():
    assert resolve_city_iata("Las Palmas") == "LPA"


@patch("adk_spanish_hotel_voice_assistant.hotel_search.amadeus_configured", return_value=False)
def test_buscar_sin_credenciales(_mock_cfg):
    out = buscar_disponibilidad_hotel("Las Palmas", "2026-06-10", "2026-06-12")
    assert out["ok"] is False
    assert out["error"] == "amadeus_not_configured"


@patch("adk_spanish_hotel_voice_assistant.hotel_search.amadeus_configured", return_value=True)
@patch("adk_spanish_hotel_voice_assistant.hotel_search.amadeus_get")
def test_buscar_devuelve_hoteles(mock_get, _mock_cfg):
    mock_get.return_value = {
        "data": [
            {
                "available": True,
                "hotel": {
                    "hotelId": "HOTEL1",
                    "name": "Hotel Urban Las Palmas",
                    "cityCode": "LPA",
                },
                "offers": [
                    {
                        "id": "OFFER1",
                        "checkInDate": "2026-06-10",
                        "checkOutDate": "2026-06-12",
                        "price": {"currency": "EUR", "total": "58.00"},
                        "room": {"description": {"text": "Doble"}},
                    }
                ],
            }
        ]
    }
    out = buscar_disponibilidad_hotel(
        "Las Palmas", "2026-06-10", "2026-06-12", huespedes=2
    )
    assert out["ok"] is True
    assert out["city_code"] == "LPA"
    assert len(out["hoteles"]) == 1
    assert out["hoteles"][0]["nombre"] == "Hotel Urban Las Palmas"
    assert out["hoteles"][0]["precio_total"] == "58.00"


@patch("adk_spanish_hotel_voice_assistant.amadeus_client.requests.post")
@patch("adk_spanish_hotel_voice_assistant.amadeus_client.AMADEUS_CLIENT_ID", "id")
@patch("adk_spanish_hotel_voice_assistant.amadeus_client.AMADEUS_CLIENT_SECRET", "secret")
def test_oauth_token_cached(mock_post):
    from adk_spanish_hotel_voice_assistant import amadeus_client as ac

    ac._TOKEN_CACHE["access_token"] = None
    ac._TOKEN_CACHE["expires_at"] = 0

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": "tok123", "expires_in": 3600}
    mock_post.return_value = resp

    assert ac.get_access_token() == "tok123"
    assert ac.get_access_token() == "tok123"
    mock_post.assert_called_once()
