"""Tests de Fase 11.2: cliente SerpApi/SearchApi con transporte mockeado.

Sin red real y sin credenciales (TECHNICAL_SPEC.md §15.2): mapeo de params
por proveedor, auth, 429/backoff, batch con fallos parciales, drill-down
con departure_token, guard SEARCH-ONLY y ausencia de métodos de reserva.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from flight_finder.flights_client import (
    PROVIDERS,
    FlightsAuthError,
    FlightsClient,
    FlightsError,
    FlightsNetworkError,
    FlightsRateLimitError,
    map_search_params,
)

ITINERARY = {"flights": [], "price": 950, "departure_token": "TOK"}


def _search_payload(n=1):
    return {
        "best_flights": [dict(ITINERARY, price=950) for _ in range(n)],
        "other_flights": [],
    }


def _client(provider, handler, key="fake_key", **kwargs):
    kwargs.setdefault("backoff_base", 0)
    return FlightsClient(
        provider, key, transport=httpx.MockTransport(handler), **kwargs
    )


def _search_kwargs(**overrides):
    kwargs = dict(
        origin="BOG",
        destination="MAD",
        departure=date(2026, 10, 5),
        return_date=date(2026, 10, 18),
        currency="USD",
        max_stops=2,
        avoid_airports=("ATL",),
    )
    kwargs.update(overrides)
    return kwargs


# --- map_search_params (puro, sin red) -------------------------------------


def test_params_serpapi():
    p = map_search_params("serpapi", **_search_kwargs())
    assert p["engine"] == "google_flights"
    assert p["type"] == "1"  # round trip numerico
    assert p["departure_id"] == "BOG"
    assert p["arrival_id"] == "MAD"
    assert p["outbound_date"] == "2026-10-05"
    assert p["return_date"] == "2026-10-18"
    assert p["currency"] == "USD"
    assert p["adults"] == "1"
    assert p["travel_class"] == "1"  # economy -> 1
    assert p["stops"] == "3"  # max_stops=2 -> 2-stops-or-fewer
    assert p["exclude_conns"] == "ATL"
    assert "flight_type" not in p
    assert "api_key" not in p  # la key la agrega _get


def test_params_searchapi():
    p = map_search_params("searchapi", **_search_kwargs())
    assert p["engine"] == "google_flights"
    assert p["flight_type"] == "round_trip"
    assert p["travel_class"] == "economy"
    assert p["stops"] == "two_stops_or_fewer"
    assert p["excluded_connecting_airports"] == "ATL"
    assert p["separate_tickets"] == "1"  # oculta self-transfer (INFORME §11)
    assert "type" not in p
    assert "exclude_conns" not in p


def test_stops_mapping_bordes():
    for provider, zero, one, two, any_stops in [
        ("serpapi", "1", "2", "3", "0"),
        ("searchapi", "nonstop", "one_stop_or_fewer",
         "two_stops_or_fewer", "any"),
    ]:
        base = _search_kwargs(max_stops=0, avoid_airports=())
        assert map_search_params(provider, **base)["stops"] == zero
        assert map_search_params(
            provider, **_search_kwargs(max_stops=1, avoid_airports=())
        )["stops"] == one
        assert map_search_params(
            provider, **_search_kwargs(max_stops=2, avoid_airports=())
        )["stops"] == two
        assert map_search_params(
            provider, **_search_kwargs(max_stops=9, avoid_airports=())
        )["stops"] == any_stops


def test_sin_airports_evitados_no_manda_exclude():
    for provider in PROVIDERS:
        p = map_search_params(provider, **_search_kwargs(avoid_airports=()))
        assert "exclude_conns" not in p
        assert "excluded_connecting_airports" not in p


def test_provider_desconocido_y_cabin_invalida():
    with pytest.raises(ValueError, match="Provider desconocido"):
        map_search_params("duffel", **_search_kwargs())
    with pytest.raises(ValueError, match="cabin_class"):
        map_search_params(
            "serpapi", **_search_kwargs(cabin_class="business")
        )


# --- auth -------------------------------------------------------------------


def test_sin_api_key_falla_rapido_con_env_var():
    with pytest.raises(FlightsAuthError, match="SERP_API"):
        FlightsClient("serpapi", "")
    with pytest.raises(FlightsAuthError, match="SEARCH_API_IO"):
        FlightsClient("searchapi", "")


def test_provider_invalido_en_cliente():
    with pytest.raises(FlightsError, match="Provider desconocido"):
        FlightsClient("otro", "key")


def test_401_da_auth_error_claro():
    def handler(request):
        return httpx.Response(401, json={"error": "Invalid API key"})

    with _client("serpapi", handler) as client:
        with pytest.raises(FlightsAuthError, match="SERP_API"):
            client.search_round_trip(**_search_kwargs())


def test_401_searchapi_menciona_su_env_var():
    def handler(request):
        return httpx.Response(401, json={"message": "unauthorized"})

    with _client("searchapi", handler) as client:
        with pytest.raises(FlightsAuthError, match="SEARCH_API_IO"):
            client.search_round_trip(**_search_kwargs())


# --- request real (mockeada) ------------------------------------------------


def test_busqueda_serpapi_get_ok():
    def handler(request):
        assert request.method == "GET"
        assert request.url.host == "serpapi.com"
        assert request.url.path == "/search"
        q = request.url.params
        assert q["api_key"] == "fake_key"
        assert q["engine"] == "google_flights"
        assert q["type"] == "1"
        assert q["exclude_conns"] == "ATL"
        return httpx.Response(200, json=_search_payload(2))

    with _client("serpapi", handler) as client:
        result = client.search_round_trip(**_search_kwargs())
    assert len(result) == 2
    assert result[0]["price"] == 950


def test_busqueda_searchapi_url_y_params():
    def handler(request):
        assert request.url.host == "www.searchapi.io"
        assert request.url.path == "/api/v1/search"
        q = request.url.params
        assert q["api_key"] == "fake_key"
        assert q["flight_type"] == "round_trip"
        return httpx.Response(200, json=_search_payload(1))

    with _client("searchapi", handler) as client:
        result = client.search_round_trip(**_search_kwargs())
    assert len(result) == 1


def test_respuesta_vacia_es_lista_vacia_no_error():
    def handler(request):
        return httpx.Response(200, json={})

    with _client("serpapi", handler) as client:
        assert client.search_round_trip(**_search_kwargs()) == []


def test_error_en_cuerpo_200_sin_itinerarios_es_vacio():
    def handler(request):
        return httpx.Response(
            200, json={"error": "Google hasn't returned any results"}
        )

    with _client("serpapi", handler) as client:
        assert client.search_round_trip(**_search_kwargs()) == []


def test_respuesta_no_json_da_error_claro():
    def handler(request):
        return httpx.Response(200, text="<html>nope</html>")

    with _client("serpapi", handler) as client:
        with pytest.raises(FlightsError, match="JSON"):
            client.search_round_trip(**_search_kwargs())


def test_400_da_error_sin_reintento():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"error": "bad request"})

    with _client("serpapi", handler) as client:
        with pytest.raises(FlightsError, match="bad request"):
            client.search_round_trip(**_search_kwargs())
    assert len(calls) == 1


# --- backoff 429 / red ------------------------------------------------------


def test_rate_limit_reintenta_y_luego_recupera():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, json={"error": "too many"})
        return httpx.Response(200, json=_search_payload(1))

    with _client("serpapi", handler) as client:
        result = client.search_round_trip(**_search_kwargs())
    assert len(calls) == 3
    assert len(result) == 1


def test_rate_limit_persistente_falla_tras_3_intentos():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": "too many"})

    with _client("serpapi", handler) as client:
        with pytest.raises(FlightsRateLimitError, match="3 intentos"):
            client.search_round_trip(**_search_kwargs())
    assert len(calls) == 3


def test_error_de_red_agota_reintentos():
    def handler(request):
        raise httpx.ConnectTimeout("timeout!")

    with _client("serpapi", handler) as client:
        with pytest.raises(FlightsNetworkError, match="3 intentos"):
            client.search_round_trip(**_search_kwargs())


def test_5xx_persistente_es_network_error():
    def handler(request):
        return httpx.Response(503, json={"error": "unavailable"})

    with _client("serpapi", handler) as client:
        with pytest.raises(FlightsNetworkError, match="3 intentos"):
            client.search_round_trip(**_search_kwargs())


# --- batch ------------------------------------------------------------------


def test_batch_continua_ante_fallo_parcial():
    def handler(request):
        if request.url.params["outbound_date"] == "2026-10-05":
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json=_search_payload(1))

    with _client("serpapi", handler) as client:
        itineraries, stats = client.search_combinations(
            "BOG",
            "MAD",
            [(date(2026, 10, 5), date(2026, 10, 18)),
             (date(2026, 10, 6), date(2026, 10, 19))],
            avoid_airports=(),
        )
    assert stats == {"consultadas": 2, "con_resultados": 1, "fallidas": 1}
    assert len(itineraries) == 1


def test_batch_aborta_con_key_invalida():
    def handler(request):
        return httpx.Response(401, json={"error": "Invalid API key"})

    with _client("serpapi", handler) as client:
        with pytest.raises(FlightsAuthError):
            client.search_combinations(
                "BOG", "MAD", [(date(2026, 10, 5), date(2026, 10, 18))]
            )


# --- drill-down -------------------------------------------------------------


def test_drill_down_manda_departure_token():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(
            200, json={"best_flights": [{"price": 950}], "other_flights": []}
        )

    with _client("serpapi", handler) as client:
        result = client.drill_down("TOKEN_IDA_1", **_search_kwargs())
    assert seen["departure_token"] == "TOKEN_IDA_1"
    assert seen["outbound_date"] == "2026-10-05"
    assert len(result) == 1


def test_drill_down_sin_token_da_error():
    with _client("serpapi", lambda r: httpx.Response(200, json={})) as client:
        with pytest.raises(FlightsError, match="departure_token"):
            client.drill_down("", **_search_kwargs())


# --- guard SEARCH-ONLY ------------------------------------------------------


def test_guard_bloquea_engine_distinto():
    with _client("serpapi", lambda r: httpx.Response(200, json={})) as client:
        with pytest.raises(FlightsError, match="SEARCH-ONLY"):
            client._get({"engine": "google_hotel"})


def test_cliente_no_expone_metodos_de_reserva():
    for name in ("post", "_post", "create_order", "book", "pay"):
        assert not hasattr(FlightsClient, name), (
            f"FlightsClient no debe exponer {name!r} (SEARCH-ONLY)"
        )


def test_fuente_sin_marcas_de_reserva():
    src = Path("src/flight_finder/flights_client.py").read_text(
        encoding="utf-8"
    )
    for pat in ("httpx.post", ".post(", "post_data", "orders", "payments"):
        assert pat not in src, f"flights_client.py no debe contener {pat!r}"
    assert '"google_flights"' in src
