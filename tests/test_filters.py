"""Tests de Fase 2 + 11: motor de filtrado de escalas prohibidas.

Criterio de hecho: suite en verde cubriendo explícitamente el caso
"escala en Atlanta se descarta" (requerimiento original del proyecto).
Usa la fixture Google Flights de SerpApi (Fase 11): directo, 1 escala
FRA, 1 escala ATL, 1 escala MEX, 2 escalas FRA+ZRH (ver
`tests/fixtures/serpapi_response.json`).

Fase 11: `inbound` es `None` hasta el drill-down — el filtro corre sobre
la ida; la vuelta se verifica solo si fue expandida (`attach_inbound`).
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from flight_finder.filters import is_offer_valid, load_airport_country_map
from flight_finder.models import (
    Offer,
    Segment,
    Slice,
    attach_inbound,
    normalize_response,
)

DATA = Path(__file__).parent.parent / "data" / "country_airports.json"
SERPAPI = Path(__file__).parent / "fixtures" / "serpapi_response.json"
SERPAPI_DRILL = Path(__file__).parent / "fixtures" / "serpapi_drilldown.json"

DIRECT_ID = "serpapi_0"     # sin escalas
FRA_ID = "serpapi_1"        # 1 escala FRA
ATL_ID = "serpapi_2"        # 1 escala ATL
MEX_ID = "serpapi_3"        # 1 escala MEX
TWOSTOP_ID = "serpapi_4"    # 2 escalas FRA + ZRH


@pytest.fixture(scope="module")
def airport_country_map():
    return load_airport_country_map(DATA)


@pytest.fixture(scope="module")
def offers():
    payload = json.loads(SERPAPI.read_text(encoding="utf-8"))
    return {
        o.id: o
        for o in normalize_response(payload, provider="serpapi", currency="USD")
    }


def _segment(a: str, b: str) -> Segment:
    return Segment(
        origin=a,
        destination=b,
        departure_time=datetime(2026, 10, 5, 8, 0),
        arrival_time=datetime(2026, 10, 5, 10, 0),
    )


def _offer_with_stopover(stopover: str) -> Offer:
    outbound = Slice(
        segments=[_segment("BOG", stopover), _segment(stopover, "MAD")],
        duration_minutes=600,
    )
    inbound = Slice(segments=[_segment("MAD", "BOG")], duration_minutes=600)
    return Offer(
        id="off_synthetic",
        price=Decimal("500.00"),
        currency="USD",
        provider="serpapi",
        retrieved_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        outbound=outbound,
        inbound=inbound,
        total_duration_minutes=1200,
    )


def test_escala_en_atl_con_us_evitado_es_invalida(offers, airport_country_map):
    valid, reason = is_offer_valid(
        offers[ATL_ID],
        avoid_countries={"US"},
        avoid_airports=set(),
        max_stops=2,
        airport_country_map=airport_country_map,
    )
    assert valid is False
    assert "ATL" in reason


def test_mex_no_afectado_por_regla_us(offers, airport_country_map):
    valid, _ = is_offer_valid(
        offers[MEX_ID],
        avoid_countries={"US"},
        avoid_airports=set(),
        max_stops=2,
        airport_country_map=airport_country_map,
    )
    assert valid is True


def test_aeropuerto_explicito_invalida_aunque_pais_no_evitado(
    offers, airport_country_map
):
    valid, reason = is_offer_valid(
        offers[TWOSTOP_ID],
        avoid_countries=set(),
        avoid_airports={"ZRH"},
        max_stops=2,
        airport_country_map=airport_country_map,
    )
    assert valid is False
    assert "ZRH" in reason


def test_oferta_sin_escalas_prohibidas_es_valida(offers, airport_country_map):
    valid, reason = is_offer_valid(
        offers[DIRECT_ID],
        avoid_countries={"US"},
        avoid_airports={"ATL"},
        max_stops=2,
        airport_country_map=airport_country_map,
    )
    assert (valid, reason) == (True, None)


def test_exceso_de_escalas_invalida_aunque_nada_prohibido(
    offers, airport_country_map
):
    valid, reason = is_offer_valid(
        offers[TWOSTOP_ID],
        avoid_countries=set(),
        avoid_airports=set(),
        max_stops=1,
        airport_country_map=airport_country_map,
    )
    assert valid is False
    assert "Exceso de escalas" in reason


def test_una_escala_valida_con_max_stops_1(offers, airport_country_map):
    valid, reason = is_offer_valid(
        offers[FRA_ID],
        avoid_countries=set(),
        avoid_airports=set(),
        max_stops=1,
        airport_country_map=airport_country_map,
    )
    assert (valid, reason) == (True, None)


def test_aeropuerto_desconocido_se_excluye_por_seguridad(airport_country_map):
    valid, reason = is_offer_valid(
        _offer_with_stopover("ZZZ"),
        avoid_countries=set(),
        avoid_airports=set(),
        max_stops=2,
        airport_country_map=airport_country_map,
    )
    assert valid is False
    assert "ZZZ" in reason and "no verificado" in reason


def test_escala_sin_mapeo_usando_mapo_vacio_se_rechaza():
    valid, reason = is_offer_valid(
        _offer_with_stopover("ZZZ"),
        avoid_countries={"US"},
        avoid_airports=set(),
        max_stops=2,
        airport_country_map={},
    )
    assert valid is False
    assert "no verificado" in (reason or "").lower()


def test_inbound_none_solo_verifica_ida(offers, airport_country_map):
    """Contrato Fase 11: sin drill-down no hay vuelta que verificar."""
    offer = offers[ATL_ID]
    assert offer.inbound is None
    valid, reason = is_offer_valid(
        offer,
        avoid_countries=set(),  # US no evitado: la ida con ATL pasa
        avoid_airports=set(),
        max_stops=2,
        airport_country_map=airport_country_map,
    )
    assert (valid, reason) == (True, None)


def test_tramo_de_vuelta_tambien_se_verifica(offers, airport_country_map):
    """Tras drill-down, la vuelta con ATL (US) invalida la oferta."""
    payload = json.loads(SERPAPI_DRILL.read_text(encoding="utf-8"))
    candidates = payload.get("best_flights") or []
    candidates += payload.get("other_flights") or []
    raw_return = next(
        it
        for it in candidates
        if any(l.get("id") == "ATL" for l in it.get("layovers", []))
    )
    expanded = attach_inbound(offers[DIRECT_ID], raw_return)
    assert expanded.inbound is not None
    valid, reason = is_offer_valid(
        expanded,
        avoid_countries={"US"},
        avoid_airports=set(),
        max_stops=2,
        airport_country_map=airport_country_map,
    )
    assert valid is False
    assert "ATL" in reason
