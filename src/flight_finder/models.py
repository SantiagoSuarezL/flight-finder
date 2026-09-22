"""Modelos internos y normalización de respuestas de Google Flights.

Única capa que conoce el schema externo de SerpApi/SearchApi (ambos exponen
Google Flights; diferencias de forma en `INFORME_FASE_11.md` §2-§4). El resto
del sistema (filtro, orden, presentación) trabaja solo con
``Offer`` / ``Slice`` / ``Segment`` / ``Layover``.

Contrato según TECHNICAL_SPEC.md §4 + §13 (Fase 11):
- Fail-closed: oferta sin ``price``, sin ``currency`` o sin ``segments`` en
  el outbound -> ``ValueError`` (reemplaza a la Regla de Oro 9.1 de
  ``live_mode``, hoy obsoleta).
- Todo ``Offer`` siempre lleva ``provider`` + ``retrieved_at``.
- ``inbound`` es ``None`` hasta el drill-down con ``departure_token``
  (``search.drill_down``); nunca se inventa la vuelta.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

_AIRLINE_CODE_RE = re.compile(r"^[A-Z0-9]{2,3}$")


def _parse_airport_datetime(raw: Any) -> datetime:
    """Interpreta el tiempo de un aeropuerto de segmento.

    SerpApi: ``time`` combinado ``"2026-03-03 10:10"``.
    SearchApi: ``date`` + ``time`` separados (``"2026-03-03"`` / ``"10:10"``).
    """
    if not isinstance(raw, dict):
        raise ValueError(f"airport datetime invalido: {raw!r}")
    date_part = raw.get("date")
    time_part = raw.get("time")
    if date_part and time_part:
        text = f"{date_part} {time_part}".replace("T", " ").strip()
    elif time_part:
        text = str(time_part).replace("T", " ").strip()
    else:
        raise ValueError("airport sin date/time")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"time de airport no reconocido: {text!r}")


def _airline_code(flight_number: Any, logo: Any) -> str | None:
    """Deriva el código IATA: prefijo de ``flight_number`` o filename del logo.

    Nunca inventa: si no hay código derivable -> ``None``.
    """
    if isinstance(flight_number, str) and flight_number.strip():
        prefix = flight_number.strip().split()[0].upper()
        if _AIRLINE_CODE_RE.match(prefix):
            return prefix
    if isinstance(logo, str) and logo.strip():
        stem = logo.rstrip("/").rsplit("/", 1)[-1]
        code = stem.rsplit(".", 1)[0].upper()
        if _AIRLINE_CODE_RE.match(code):
            return code
    return None


class Layover(BaseModel):
    """Escala entre segmentos (alimenta display; el filtro usa
    ``Slice.stopover_airports``)."""

    id: str  # IATA
    name: str | None = None
    duration_minutes: int | None = None
    overnight: bool = False


class Segment(BaseModel):
    origin: str  # IATA
    destination: str  # IATA
    departure_time: datetime
    arrival_time: datetime
    airline: str | None = None  # nombre Google Flights, ej. "Iberia"
    airline_code: str | None = None  # derivado; nunca inventado
    flight_number: str | None = None  # ej. "IB 212"
    duration_minutes: int | None = None
    airplane: str | None = None
    is_overnight: bool | None = None
    legroom: str | None = None
    airline_logo: str | None = None


class Slice(BaseModel):
    segments: list[Segment]
    duration_minutes: int
    layovers: list[Layover] = []

    @property
    def stopover_airports(self) -> list[str]:
        """Aeropuertos de escala: destino de cada segmento excepto el último."""
        return [seg.destination for seg in self.segments[:-1]]


class Offer(BaseModel):
    id: str  # sintético: provider + índice (Google no expone id)
    price: Decimal  # precio total del round trip listado
    currency: str  # de config `currency`
    provider: str  # serpapi | searchapi
    retrieved_at: datetime
    outbound: Slice
    inbound: Slice | None = None  # completa tras drill-down; None = sin expandir
    total_duration_minutes: int
    carbon_emissions_kg: int | None = None
    baggage_note: str | None = None  # string textual de `extensions`
    departure_token: str | None = None  # opaco, solo drill-down inmediato
    booking_token: str | None = None  # opaco, nunca usado para booking


class PriceInsights(BaseModel):
    """Datos de RUTA (no de oferta): forma normalizada de ambos proveedores."""

    lowest_price: float | None = None
    price_level: str | None = None
    typical_low: float | None = None
    typical_high: float | None = None


def parse_price_insights(raw: Any, provider: str) -> PriceInsights | None:
    """Normaliza ``price_insights`` de ambos proveedores (§15.2).

    SerpApi: ``typical_price_range`` es ``[low, high]`` (array).
    SearchApi: ``typical_price_range`` es ``{low_price, high_price}`` (objeto).
    """
    if not isinstance(raw, dict) or not raw:
        return None
    low: float | None = None
    high: float | None = None
    range_val = raw.get("typical_price_range")
    if isinstance(range_val, dict):
        low = _as_float(range_val.get("low_price"))
        high = _as_float(range_val.get("high_price"))
    elif isinstance(range_val, list) and len(range_val) == 2:
        low = _as_float(range_val[0])
        high = _as_float(range_val[1])
    level = raw.get("price_level")
    return PriceInsights(
        lowest_price=_as_float(raw.get("lowest_price")),
        price_level=str(level) if level is not None else None,
        typical_low=low,
        typical_high=high,
    )


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_segment(raw: Any, *, offer_id: str) -> Segment:
    if not isinstance(raw, dict):
        raise ValueError(f"Oferta {offer_id}: segmento no es un objeto")
    try:
        origin = raw["departure_airport"]["id"]
        destination = raw["arrival_airport"]["id"]
        departure_time = _parse_airport_datetime(raw["departure_airport"])
        arrival_time = _parse_airport_datetime(raw["arrival_airport"])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Oferta {offer_id}: segmento invalido ({exc})") from exc
    flight_number = raw.get("flight_number")
    airline = raw.get("airline")
    logo = raw.get("airline_logo")
    legroom = raw.get("legroom")
    if legroom is None and isinstance(raw.get("detected_extensions"), dict):
        legroom = raw["detected_extensions"].get("legroom_short")
    duration = raw.get("duration")
    return Segment(
        origin=str(origin),
        destination=str(destination),
        departure_time=departure_time,
        arrival_time=arrival_time,
        airline=str(airline) if airline else None,
        airline_code=_airline_code(flight_number, logo),
        flight_number=str(flight_number) if flight_number else None,
        duration_minutes=int(duration) if isinstance(duration, int) else None,
        airplane=str(raw["airplane"]) if raw.get("airplane") else None,
        is_overnight=(
            bool(raw["is_overnight"]) if "is_overnight" in raw else None
        ),
        legroom=str(legroom) if legroom is not None else None,
        airline_logo=str(logo) if logo else None,
    )


def _parse_layovers(raw: Any) -> list[Layover]:
    if not isinstance(raw, list):
        return []
    layovers: list[Layover] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        airport_id = item.get("id")
        if not airport_id:
            continue
        duration = item.get("duration")
        layovers.append(
            Layover(
                id=str(airport_id),
                name=str(item["name"]) if item.get("name") else None,
                duration_minutes=(
                    int(duration) if isinstance(duration, int) else None
                ),
                overnight=bool(item.get("overnight")),
            )
        )
    return layovers


def _parse_slice(raw: Any, *, offer_id: str) -> Slice:
    if not isinstance(raw, dict):
        raise ValueError(f"Oferta {offer_id}: itinerario no es un objeto")
    flights = raw.get("flights")
    if not isinstance(flights, list) or not flights:
        raise ValueError(f"Oferta {offer_id}: itinerario sin segments/flights")
    segments = [_parse_segment(seg, offer_id=offer_id) for seg in flights]
    duration = raw.get("total_duration")
    if not isinstance(duration, int):
        duration = sum(
            (seg.duration_minutes or 0) for seg in segments
        )
    return Slice(
        segments=segments,
        duration_minutes=int(duration),
        layovers=_parse_layovers(raw.get("layovers")),
    )


def _baggage_note(raw: dict[str, Any]) -> str | None:
    """Texto libre de ``extensions`` del itinerario (sin estructura)."""
    extensions = raw.get("extensions")
    if isinstance(extensions, list):
        parts = [str(x) for x in extensions if isinstance(x, str) and x]
        if parts:
            return "; ".join(dict.fromkeys(parts))
    return None


def _carbon_kg(raw: dict[str, Any]) -> int | None:
    """``carbon_emissions.this_flight`` viene en gramos -> kg enteros."""
    emissions = raw.get("carbon_emissions")
    if not isinstance(emissions, dict):
        return None
    this_flight = emissions.get("this_flight")
    if isinstance(this_flight, bool) or not isinstance(this_flight, (int, float)):
        return None
    return int(round(this_flight / 1000))


def _decimal_price(value: Any, *, offer_id: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"Oferta {offer_id}: sin price")
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 — price no numerico
        raise ValueError(f"Oferta {offer_id}: price no numerico ({value!r})") from exc


def normalize_itinerary(
    raw: Any,
    *,
    provider: str,
    currency: str,
    offer_id: str,
    retrieved_at: datetime | None = None,
) -> Offer:
    """Convierte UN itinerario crudo de Google Flights en un ``Offer``.

    Fail-closed (§4): sin ``price``, sin ``currency`` o sin ``flights`` en el
    outbound -> ``ValueError``. El inbound queda ``None`` hasta drill-down.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"Oferta {offer_id}: itinerario no es un objeto")
    if not currency:
        raise ValueError(f"Oferta {offer_id}: sin currency")
    price = _decimal_price(raw.get("price"), offer_id=offer_id)
    outbound = _parse_slice(raw, offer_id=offer_id)
    return Offer(
        id=offer_id,
        price=price,
        currency=currency,
        provider=provider,
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
        outbound=outbound,
        inbound=None,
        total_duration_minutes=outbound.duration_minutes,
        carbon_emissions_kg=_carbon_kg(raw),
        baggage_note=_baggage_note(raw),
        departure_token=(
            str(raw["departure_token"]) if raw.get("departure_token") else None
        ),
        booking_token=(
            str(raw["booking_token"]) if raw.get("booking_token") else None
        ),
    )


def attach_inbound(
    offer: Offer, raw_return: Any, *, provider: str | None = None
) -> Offer:
    """Completa ``inbound`` con el itinerario de vuelta del drill-down.

    ``provider`` se acepta solo para explícita claridad; el slice se parsea
    con la misma rutina que el outbound (mismo shape de ``flights``).
    """
    if not isinstance(raw_return, dict):
        raise ValueError(f"Oferta {offer.id}: vuelta no es un objeto")
    inbound = _parse_slice(raw_return, offer_id=offer.id)
    return offer.model_copy(
        update={
            "inbound": inbound,
            "total_duration_minutes": (
                offer.outbound.duration_minutes + inbound.duration_minutes
            ),
        }
    )


def extract_itineraries(payload: Any) -> list[dict]:
    """Extrae la lista de itinerarios de una respuesta de ambos proveedores.

    Shape de respuesta (§2-§3): ``best_flights`` + ``other_flights``.
    """
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    itineraries: list[dict] = []
    for key in ("best_flights", "other_flights"):
        block = payload.get(key)
        if isinstance(block, list):
            itineraries.extend(x for x in block if isinstance(x, dict))
    return itineraries


def normalize_response(
    payload: Any,
    *,
    provider: str,
    currency: str,
    retrieved_at: datetime | None = None,
) -> list[Offer]:
    """Normaliza una respuesta completa (best_flights + other_flights).

    Itinerarios inválidos se descartan con ``ValueError`` por separado en el
    caller; acá se propagan para que el caller cuente descartes.
    """
    offers: list[Offer] = []
    for idx, raw in enumerate(extract_itineraries(payload)):
        offers.append(
            normalize_itinerary(
                raw,
                provider=provider,
                currency=currency,
                offer_id=f"{provider}_{idx}",
                retrieved_at=retrieved_at,
            )
        )
    return offers
