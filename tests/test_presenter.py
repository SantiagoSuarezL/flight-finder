"""Tests de Fase 6 + 11: presentación y exportación (TECHNICAL_SPEC §14)."""

import csv
import io
import json
from collections import Counter
from datetime import date
from pathlib import Path

from flight_finder.models import attach_inbound, normalize_response
from flight_finder.presenter import (
    export_csv,
    export_html,
    fmt_duration,
    format_offer_card,
    google_flights_url,
    make_console,
    print_banner,
    print_filter_summary,
    print_no_results,
    print_offers,
)

FIXTURE = Path(__file__).parent / "fixtures" / "serpapi_response.json"
DRILL = Path(__file__).parent / "fixtures" / "serpapi_drilldown.json"


def _offers():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return normalize_response(payload, provider="serpapi", currency="USD")


def _expanded(offer):
    payload = json.loads(DRILL.read_text(encoding="utf-8"))
    candidates = payload.get("best_flights") or []
    candidates += payload.get("other_flights") or []
    return attach_inbound(offer, candidates[0])


def _console():
    from rich.console import Console

    buf = io.StringIO()
    return Console(file=buf, width=200, highlight=False), buf


def test_banner_serpapi():
    console, buf = _console()
    print_banner(console, "serpapi")
    out = buf.getvalue()
    assert "SOURCE: SerpApi (Google Flights)" in out
    assert "SEARCHED AT:" in out
    assert "not bookable offers" in out
    assert "SANDBOX" not in out and "MODE:" not in out


def test_banner_searchapi():
    console, buf = _console()
    print_banner(console, "searchapi")
    assert "SOURCE: SearchApi (Google Flights)" in buf.getvalue()


def test_resumen_muestra_filtros_aplicados():
    console, buf = _console()
    print_filter_summary(
        console,
        origin="BOG",
        destination="MAD",
        n_combinations=6,
        avoid_countries=["US"],
        avoid_airports=["ATL"],
        max_stops=2,
    )
    out = buf.getvalue()
    assert "BOG -> MAD" in out
    assert "6 combinaciones" in out
    assert "US" in out and "ATL" in out


def test_tabla_muestra_precio_ruta_y_escalas_verificadas():
    console, buf = _console()
    print_offers(console, _offers(), top_n=5)
    out = buf.getvalue()
    assert "950 USD" in out
    assert "BOG" in out and "MAD" in out
    assert "verificada" in out
    assert "directo" in out
    assert "ATL" in out  # layover de la oferta 3


def test_tabla_etiqueta_vuelta_no_expandida():
    """Fixtures sin drill-down: inbound es None -> etiqueta honesta."""
    console, buf = _console()
    offers = _offers()
    assert all(o.inbound is None for o in offers)
    print_offers(console, offers, top_n=1)
    out = buf.getvalue()
    assert "not expanded (cheapest return included in price)" in out


def test_card_completa_tras_drill_down():
    offer = _expanded(_offers()[0])
    card = format_offer_card(offer, 1)
    assert "PRICE: 950 USD (round trip total)" in card
    assert "AIRLINE:" in card
    assert "OUTBOUND: BOG" in card
    assert "RETURN:" in card and "not expanded" not in card.split("RETURN:")[1].split("\n")[0]
    assert "STOPS:" in card and "LAYOVERS:" in card
    assert "BAGGAGE:" in card
    assert "CARBON:" in card and "AIRPLANE:" in card
    # Campos obsoletos Duffel prohibidos (§14)
    assert "EXPIRATION" not in card
    assert "LIVE/TEST" not in card
    assert "ZZ" not in card
    assert "TEST/SANDBOX" not in card


def test_card_vuelta_no_expandida():
    card = format_offer_card(_offers()[1], 2)
    assert "not expanded (cheapest return included in price)" in card
    assert "EXPIRATION" not in card and "LIVE/TEST" not in card


def test_google_flights_url_formato_exact():
    url = google_flights_url(
        "BOG", "MAD", date(2026, 10, 15), date(2026, 10, 25)
    )
    assert url == (
        "https://www.google.com/travel/flights"
        "?q=Flights%20to%20MAD%20from%20BOG%20on%202026-10-15"
        "%20through%202026-10-25"
    )
    assert " " not in url  # todo ASCII, sin espacios crudos


def test_card_sin_return_date_no_lleva_link():
    card = format_offer_card(_offers()[0], 1)
    assert "LINK:" not in card
    assert "Para reservar" in card  # flujo manual intacto


def test_card_con_return_date_lleva_link_honesto():
    card = format_offer_card(
        _offers()[0], 1, return_date=date(2026, 10, 25)
    )
    assert "LINK: https://www.google.com/travel/flights?q=" in card
    assert "BOG" in card.split("LINK:")[1].split("\n")[0]
    assert "precio puede variar" in card


def test_print_cards_usa_combo_para_link():
    from flight_finder.presenter import print_offer_cards

    console, buf = _console()
    offers = _offers()[:1]
    combo = {offers[0].id: (date(2026, 10, 15), date(2026, 10, 25))}
    print_offer_cards(console, offers, top_n=1, combo_of=combo)
    out = buf.getvalue()
    assert "LINK: https://www.google.com/travel/flights?q=" in out
    # La vuelta del link viene del combo (wiring CLI), no de la oferta.
    assert "through%202026-10-25" in out.split("LINK:")[1].split("\n")[0]

    console, buf = _console()
    print_offer_cards(console, offers, top_n=1)
    assert "LINK:" not in buf.getvalue()


def test_sin_resultados_explica_descartes():
    console, buf = _console()
    print_no_results(
        console,
        8,
        Counter(
            {
                "Escala en ATL (pais excluido: US)": 6,
                "Exceso de escalas": 2,
            }
        ),
    )
    out = buf.getvalue()
    assert "8 ofertas en bruto" in out
    assert "6x" in out and "ATL" in out


def test_export_csv(tmp_path):
    path = export_csv(tmp_path / "vuelos.csv", _offers(), top_n=2)
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 2
    assert rows[0]["precio"] == "950"
    assert rows[0]["moneda"] == "USD"
    assert "BOG" in rows[0]["ida_ruta"]
    # Dentro (INFORME §8.5): emissions/layovers(escalas)/airline_logo
    assert "emissions_kg" in rows[0]
    assert "escalas_ida" in rows[0]
    assert "airline_logo" in rows[0]
    # Fuera: expires_at/live_mode/owner (Duffel)
    assert "expires_at" not in rows[0]
    assert "live_mode" not in rows[0]
    assert "owner" not in rows[0]


def test_export_html(tmp_path):
    path = export_html(tmp_path / "vuelos.html", _offers(), top_n=2)
    content = path.read_text(encoding="utf-8")
    assert "<table" in content and "950" in content
    assert "emissions_kg" in content
    assert "expires_at" not in content and "live_mode" not in content


def test_fmt_duration():
    assert fmt_duration(677) == "11h 17m"
    assert fmt_duration(60) == "1h 00m"


def test_make_console_es_ascii_seguro():
    # Regla de Oro 5.1: el modulo no emite flechas unicode en helpers.
    from flight_finder.presenter import fmt_route

    assert "->" in fmt_route(_offers()[0].outbound)
    assert "→" not in fmt_route(_offers()[0].outbound)
