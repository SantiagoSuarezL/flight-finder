"""Tests de Fase 11.1: normalización Google Flights -> modelos internos.

Matriz TECHNICAL_SPEC.md §15.2 (sin red, sin credenciales): shapes de
**ambos** proveedores (hora combinada SerpApi vs date+time SearchApi),
fail-closed sobre price/currency/segments, drill-down con
`departure_token`, `price_insights` array vs objeto.

Fixtures sintéticos con forma fiel a la doc oficial (`INFORME_FASE_11.md`
§2-§3): 5 itinerarios por proveedor (directa, 1 escala FRA, 1 escala ATL,
1 escala MEX, 2 escalas FRA+ZRH) + fixtures de drill-down (vuelta).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from flight_finder.models import (
    attach_inbound,
    extract_itineraries,
    normalize_itinerary,
    normalize_response,
    parse_price_insights,
)

FIXTURES = Path(__file__).parent / "fixtures"
SERP = FIXTURES / "serpapi_response.json"
SEARCH = FIXTURES / "searchapi_response.json"
SERP_DRILL = FIXTURES / "serpapi_drilldown.json"
SEARCH_DRILL = FIXTURES / "searchapi_drilldown.json"

# Orden de normalize_response: best_flights (direct, FRA) + other (ATL, MEX, 2)
DIRECT, FRA, ATL, MEX, TWO = range(5)


@pytest.fixture(scope="module")
def serpapi_payload():
    return json.loads(SERP.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def searchapi_payload():
    return json.loads(SEARCH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def serpapi_offers(serpapi_payload):
    return normalize_response(serpapi_payload, provider="serpapi", currency="USD")


@pytest.fixture(scope="module")
def searchapi_offers(searchapi_payload):
    return normalize_response(
        searchapi_payload, provider="searchapi", currency="USD"
    )


# --- cantidad y estructura básica ------------------------------------------


def test_ambos_proveedores_producen_cinco_ofertas(serpapi_offers, searchapi_offers):
    assert len(serpapi_offers) == 5
    assert len(searchapi_offers) == 5
    assert [o.id for o in serpapi_offers] == [f"serpapi_{i}" for i in range(5)]
    assert [o.id for o in searchapi_offers] == [f"searchapi_{i}" for i in range(5)]


def test_offer_lleva_provider_currency_y_retrieved_at(
    serpapi_offers, searchapi_offers
):
    for offer in serpapi_offers:
        assert offer.provider == "serpapi"
        assert offer.currency == "USD"
        assert offer.retrieved_at is not None
    for offer in searchapi_offers:
        assert offer.provider == "searchapi"
        assert offer.currency == "USD"


def test_inbound_es_none_hasta_drill_down(serpapi_offers, searchapi_offers):
    assert all(o.inbound is None for o in serpapi_offers)
    assert all(o.inbound is None for o in searchapi_offers)


def test_departure_token_se_conserva(serpapi_offers, searchapi_offers):
    assert serpapi_offers[DIRECT].departure_token == "SERP_TOKEN_DIRECT"
    assert searchapi_offers[DIRECT].departure_token == "SEARCH_TOKEN_DIRECT"
    assert serpapi_offers[DIRECT].booking_token is None


# --- hora combinada (SerpApi) vs date+time (SearchApi) ---------------------


def test_serpapi_hora_combinada(serpapi_offers):
    seg = serpapi_offers[DIRECT].outbound.segments[0]
    assert seg.departure_time.isoformat() == "2026-10-05T22:40:00"
    assert seg.arrival_time.isoformat() == "2026-10-06T15:50:00"  # dia+1


def test_searchapi_date_y_time_separados(searchapi_offers):
    seg = searchapi_offers[DIRECT].outbound.segments[0]
    assert seg.departure_time.isoformat() == "2026-10-05T22:40:00"
    assert seg.arrival_time.isoformat() == "2026-10-06T15:50:00"


def test_formato_de_hora_ambos_proveedores_identicos(
    serpapi_offers, searchapi_offers
):
    for i in range(5):
        s = serpapi_offers[i].outbound.segments[0]
        a = searchapi_offers[i].outbound.segments[0]
        assert s.departure_time == a.departure_time
        assert s.arrival_time == a.arrival_time


# --- precios, duraciones, escalas ------------------------------------------


def test_precios_decimal_y_rutina_barata_primero(serpapi_offers, searchapi_offers):
    assert serpapi_offers[TWO].price == Decimal("800")  # mas barata
    assert serpapi_offers[DIRECT].price == Decimal("950")
    assert searchapi_offers[FRA].price == Decimal("850")


def test_stopover_airports_por_itinerario(serpapi_offers, searchapi_offers):
    for offers in (serpapi_offers, searchapi_offers):
        assert offers[DIRECT].outbound.stopover_airports == []
        assert offers[FRA].outbound.stopover_airports == ["FRA"]
        assert offers[ATL].outbound.stopover_airports == ["ATL"]
        assert offers[MEX].outbound.stopover_airports == ["MEX"]
        assert offers[TWO].outbound.stopover_airports == ["FRA", "ZRH"]


def test_layovers_parseados_con_id_iata(serpapi_offers, searchapi_offers):
    layovers = serpapi_offers[FRA].outbound.layovers
    assert len(layovers) == 1
    assert layovers[0].id == "FRA"
    assert layovers[0].duration_minutes == 135
    assert layovers[0].overnight is False
    assert searchapi_offers[TWO].outbound.layovers[1].id == "ZRH"


def test_total_duration_y_outbound_duration(serpapi_offers):
    direct = serpapi_offers[DIRECT]
    assert direct.outbound.duration_minutes == 610
    assert direct.total_duration_minutes == 610  # sin inbound = solo ida
    fra = serpapi_offers[FRA]
    assert fra.outbound.duration_minutes == 960
    assert fra.total_duration_minutes == 960


# --- aerolineas: nombre + codigo derivado ----------------------------------


def test_airline_code_desde_prefijo_de_flight_number(serpapi_offers):
    seg = serpapi_offers[DIRECT].outbound.segments[0]
    assert seg.airline == "Iberia"
    assert seg.flight_number == "IB 6626"
    assert seg.airline_code == "IB"


def test_airline_code_desde_logo_cuando_falta_flight_number(serpapi_offers):
    # Segmento FRA->ZRH del itinerario 2 escalas: sin flight_number, con logo
    seg = serpapi_offers[TWO].outbound.segments[1]
    assert seg.flight_number is None
    assert seg.airline == "Lufthansa"
    assert seg.airline_code == "LH"  # filename del logo .../LH.png


def test_searchapi_is_overnight_y_legroom(searchapi_offers):
    direct = searchapi_offers[DIRECT].outbound.segments[0]
    assert direct.is_overnight is True
    assert direct.legroom == "31in"  # desde detected_extensions.legroom_short
    fra = searchapi_offers[FRA].outbound.segments[0]
    assert fra.is_overnight is False
    assert fra.legroom == "32"  # legroom top-level


def test_serpapi_sin_is_overnight_es_none(serpapi_offers):
    assert serpapi_offers[DIRECT].outbound.segments[0].is_overnight is None


# --- carbon / baggage ------------------------------------------------------


def test_carbon_emissions_gramos_a_kg(serpapi_offers, searchapi_offers):
    assert serpapi_offers[DIRECT].carbon_emissions_kg == 161  # 161000 g
    assert searchapi_offers[FRA].carbon_emissions_kg == 172


def test_baggage_note_es_texto_de_extensions(serpapi_offers, searchapi_offers):
    assert serpapi_offers[DIRECT].baggage_note == "Checked baggage for a fee"
    assert searchapi_offers[DIRECT].baggage_note == "Checked baggage for a fee"


# --- fail-closed (TECHNICAL_SPEC §4) ---------------------------------------


def test_sin_price_es_value_error(serpapi_offers):
    payload = json.loads(SERP.read_text(encoding="utf-8"))
    broken = dict(payload["best_flights"][0])
    broken.pop("price", None)
    with pytest.raises(ValueError, match="sin price"):
        normalize_itinerary(
            broken, provider="serpapi", currency="USD", offer_id="x"
        )


def test_sin_currency_es_value_error(serpapi_offers):
    payload = json.loads(SERP.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="currency"):
        normalize_itinerary(
            payload["best_flights"][0],
            provider="serpapi",
            currency="",
            offer_id="x",
        )


def test_sin_flights_es_value_error(serpapi_offers):
    payload = json.loads(SERP.read_text(encoding="utf-8"))
    broken = dict(payload["best_flights"][0])
    broken["flights"] = []
    with pytest.raises(ValueError, match="flights"):
        normalize_itinerary(
            broken, provider="serpapi", currency="USD", offer_id="x"
        )


def test_itinerario_no_dict_es_value_error():
    with pytest.raises(ValueError, match="no es un objeto"):
        normalize_itinerary(
            ["nope"], provider="serpapi", currency="USD", offer_id="x"
        )


# --- drill-down (attach_inbound) -------------------------------------------


def test_attach_inbound_completa_vuelta_y_duración(serpapi_offers):
    drill = json.loads(SERP_DRILL.read_text(encoding="utf-8"))
    offer = attach_inbound(serpapi_offers[DIRECT], drill["best_flights"][0])
    assert offer.inbound is not None
    assert offer.inbound.stopover_airports == []
    assert offer.inbound.segments[0].origin == "MAD"
    assert offer.inbound.segments[0].destination == "BOG"
    # total = ida 610 + vuelta 620
    assert offer.total_duration_minutes == 1230
    # la oferta original (inmutable) sigue sin inbound
    assert serpapi_offers[DIRECT].inbound is None


def test_attach_inbound_vuelta_con_escala(serpapi_offers):
    drill = json.loads(SERP_DRILL.read_text(encoding="utf-8"))
    offer = attach_inbound(serpapi_offers[FRA], drill["other_flights"][0])
    assert offer.inbound.stopover_airports == ["ATL"]
    assert offer.total_duration_minutes == 960 + 1030


def test_attach_inbound_searchapi(searchapi_offers):
    drill = json.loads(SEARCH_DRILL.read_text(encoding="utf-8"))
    offer = attach_inbound(searchapi_offers[DIRECT], drill["best_flights"][0])
    assert offer.inbound.segments[0].departure_time.isoformat() == (
        "2026-10-18T21:10:00"
    )
    assert offer.inbound.segments[0].is_overnight is True


def test_attach_inbound_retorno_invalido_es_value_error(serpapi_offers):
    with pytest.raises(ValueError, match="no es un objeto"):
        attach_inbound(serpapi_offers[DIRECT], "nope")


# --- price_insights (array vs objeto) --------------------------------------


def test_price_insights_serpapi_array(serpapi_payload):
    insights = parse_price_insights(serpapi_payload["price_insights"], "serpapi")
    assert insights is not None
    assert insights.lowest_price == 800.0
    assert insights.price_level == "low"
    assert insights.typical_low == 750.0
    assert insights.typical_high == 1100.0


def test_price_insights_searchapi_objeto(searchapi_payload):
    insights = parse_price_insights(
        searchapi_payload["price_insights"], "searchapi"
    )
    assert insights is not None
    assert insights.lowest_price == 800.0
    assert insights.typical_low == 750.0
    assert insights.typical_high == 1100.0


def test_price_insights_ausente_es_none():
    assert parse_price_insights(None, "serpapi") is None
    assert parse_price_insights({}, "serpapi") is None


# --- extract_itineraries ---------------------------------------------------


def test_extract_itineraries_best_y_other(serpapi_payload):
    itineraries = extract_itineraries(serpapi_payload)
    assert len(itineraries) == 5


def test_extract_itineraries_lista_y_basura():
    assert extract_itineraries([{"a": 1}, "x"]) == [{"a": 1}]
    assert extract_itineraries("nope") == []
    assert extract_itineraries(None) == []
