"""Real hotel availability via Amadeus GDS (buscar_disponibilidad_hotel).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .amadeus_client import AmadeusError, amadeus_configured, amadeus_get
from .config import DEFAULT_HOTEL_CITY, logger

HOTEL_SEARCH_FUNCTION_NAME = "buscar_disponibilidad_hotel"

# Ciudades frecuentes (España + ejemplos internacionales). Amadeus usa códigos IATA.
_CITY_TO_IATA: Dict[str, str] = {
    "las palmas": "LPA",
    "las palmas de gran canaria": "LPA",
    "gran canaria": "LPA",
    "madrid": "MAD",
    "barcelona": "BCN",
    "valencia": "VLC",
    "sevilla": "SVQ",
    "malaga": "AGP",
    "málaga": "AGP",
    "palma": "PMI",
    "palma de mallorca": "PMI",
    "bilbao": "BIO",
    "alicante": "ALC",
    "zaragoza": "ZAZ",
    "tenerife": "TCI",
    "santa cruz de tenerife": "TCI",
    "london": "LON",
    "londres": "LON",
    "paris": "PAR",
    "parís": "PAR",
    "new york": "NYC",
    "nueva york": "NYC",
}

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def infer_ciudad_from_text(text: str) -> str:
    """Keyword fallback when structured routing omits ciudad."""
    lower = (text or "").lower()
    if not lower:
        return ""
    for name in sorted(_CITY_TO_IATA.keys(), key=len, reverse=True):
        if name in lower:
            return " ".join(word.capitalize() for word in name.split())
    return ""


def resolve_city_iata(ciudad: str) -> Optional[str]:
    key = (ciudad or "").strip().lower()
    if not key:
        return None
    if len(key) == 3 and key.isalpha():
        upper = key.upper()
        if upper in set(_CITY_TO_IATA.values()):
            return upper
        return None
    if key in _CITY_TO_IATA:
        return _CITY_TO_IATA[key]
    # Whole-word / full-alias match only (avoid "san" → Tenerife/TCI false positives).
    padded = f" {key} "
    best_code: Optional[str] = None
    best_len = 0
    for name, code in _CITY_TO_IATA.items():
        if len(name) < 4:
            continue
        if key == name or f" {name} " in padded:
            if len(name) > best_len:
                best_code = code
                best_len = len(name)
    return best_code


def normalize_date(value: str) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    if _DATE_RE.match(raw):
        return raw
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _summarize_offer(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    hotel = item.get("hotel") if isinstance(item.get("hotel"), dict) else {}
    offers = item.get("offers") if isinstance(item.get("offers"), list) else []
    if not offers:
        return None
    offer = offers[0] if isinstance(offers[0], dict) else {}
    price = offer.get("price") if isinstance(offer.get("price"), dict) else {}
    room = offer.get("room") if isinstance(offer.get("room"), dict) else {}
    desc = room.get("description") if isinstance(room.get("description"), dict) else {}
    return {
        "hotel_id": hotel.get("hotelId") or "",
        "nombre": hotel.get("name") or "Hotel sin nombre",
        "cadena": hotel.get("chainCode") or "",
        "ciudad_iata": hotel.get("cityCode") or "",
        "precio_total": price.get("total") or price.get("sellingTotal") or "",
        "precio_base": price.get("base") or "",
        "moneda": price.get("currency") or "",
        "habitacion": desc.get("text") or room.get("type") or "",
        "offer_id": offer.get("id") or "",
        "check_in": offer.get("checkInDate") or "",
        "check_out": offer.get("checkOutDate") or "",
    }


def _fetch_offers_by_city(
    city_code: str,
    check_in: str,
    check_out: str,
    guests: int,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "cityCode": city_code,
        "checkInDate": check_in,
        "checkOutDate": check_out,
        "adults": max(1, guests),
        "roomQuantity": 1,
        "currency": "EUR",
    }
    payload = amadeus_get("/v3/shopping/hotel-offers", params)
    data = payload.get("data") if isinstance(payload.get("data"), list) else []
    hotels: List[Dict[str, Any]] = []
    for item in data[:8]:
        if not isinstance(item, dict):
            continue
        if item.get("available") is False:
            continue
        summary = _summarize_offer(item)
        if summary and summary.get("precio_total"):
            hotels.append(summary)
    return hotels


def _fetch_offers_by_hotel_ids(
    hotel_ids: List[str],
    check_in: str,
    check_out: str,
    guests: int,
) -> List[Dict[str, Any]]:
    if not hotel_ids:
        return []
    params = {
        "hotelIds": ",".join(hotel_ids[:20]),
        "checkInDate": check_in,
        "checkOutDate": check_out,
        "adults": max(1, guests),
        "roomQuantity": 1,
        "currency": "EUR",
    }
    payload = amadeus_get("/v3/shopping/hotel-offers", params)
    data = payload.get("data") if isinstance(payload.get("data"), list) else []
    hotels: List[Dict[str, Any]] = []
    for item in data[:8]:
        if isinstance(item, dict):
            summary = _summarize_offer(item)
            if summary and summary.get("precio_total"):
                hotels.append(summary)
    return hotels


def _list_hotel_ids_for_city(city_code: str) -> List[str]:
    payload = amadeus_get(
        "/v1/reference-data/locations/hotels/by-city",
        {"cityCode": city_code},
    )
    data = payload.get("data") if isinstance(payload.get("data"), list) else []
    ids: List[str] = []
    for row in data:
        if isinstance(row, dict) and row.get("hotelId"):
            ids.append(str(row["hotelId"]))
    return ids


def buscar_disponibilidad_hotel(
    ciudad: str,
    check_in: str,
    check_out: str,
    huespedes: int = 1,
) -> Dict[str, Any]:
    """Tool / callback: real availability and prices from Amadeus test or production API."""
    if not amadeus_configured():
        return {
            "ok": False,
            "error": "amadeus_not_configured",
            "mensaje": (
                "Configure AMADEUS_CLIENT_ID y AMADEUS_CLIENT_SECRET en .env "
                "(registro gratuito en developers.amadeus.com)."
            ),
        }

    city_label = (ciudad or DEFAULT_HOTEL_CITY).strip() or DEFAULT_HOTEL_CITY
    city_code = resolve_city_iata(city_label)
    if not city_code:
        return {
            "ok": False,
            "error": "ciudad_no_reconocida",
            "mensaje": f"No reconozco la ciudad «{city_label}». Pruebe Madrid, Las Palmas, Barcelona…",
        }

    cin = normalize_date(check_in)
    cout = normalize_date(check_out)
    if not cin or not cout:
        return {
            "ok": False,
            "error": "fechas_invalidas",
            "mensaje": "Indique check-in y check-out en formato YYYY-MM-DD (ej. 2026-06-15).",
        }

    guests = max(1, int(huespedes or 1))

    try:
        hotels = _fetch_offers_by_city(city_code, cin, cout, guests)
        if not hotels:
            ids = _list_hotel_ids_for_city(city_code)
            hotels = _fetch_offers_by_hotel_ids(ids, cin, cout, guests)

        if not hotels:
            return {
                "ok": True,
                "ciudad": city_label,
                "city_code": city_code,
                "check_in": cin,
                "check_out": cout,
                "huespedes": guests,
                "hoteles": [],
                "mensaje": (
                    "No hay ofertas en Amadeus para esas fechas (entorno test con datos limitados). "
                    "Pruebe otras fechas o active producción en AMADEUS_API_HOST."
                ),
            }

        return {
            "ok": True,
            "ciudad": city_label,
            "city_code": city_code,
            "check_in": cin,
            "check_out": cout,
            "huespedes": guests,
            "fuente": "amadeus",
            "hoteles": hotels,
            "mensaje": f"{len(hotels)} hotel(es) con precio disponible.",
        }
    except AmadeusError as exc:
        logger.warning("Amadeus hotel search failed: %s", exc)
        return {
            "ok": False,
            "error": "amadeus_api_error",
            "mensaje": str(exc),
        }
    except Exception as exc:
        logger.exception("Unexpected hotel search error")
        return {
            "ok": False,
            "error": "search_failed",
            "mensaje": str(exc),
        }
