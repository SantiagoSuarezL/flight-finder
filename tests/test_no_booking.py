"""Test estructural SEARCH-ONLY: el sistema no puede reservar.

Matriz TECHNICAL_SPEC.md §15.2: ningún módulo fuera de `flights_client.py`
hace HTTP, y la presentación/export no filtra credenciales. Los tests del
cliente (guard engine, sin métodos de reserva, fuente sin `post_data`/
`orders`/`payments`) viven en `test_flights_client.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from flight_finder.models import normalize_response
from flight_finder.presenter import export_csv, format_offer_card

FIXTURE = Path(__file__).parent / "fixtures" / "serpapi_response.json"

_SECRET_MARKERS = ("api_key", "SERP_API", "SEARCH_API_IO", "Bearer ")


def test_ningun_otro_modulo_hace_http():
    for rel in [
        "src/flight_finder/models.py",
        "src/flight_finder/filters.py",
        "src/flight_finder/presenter.py",
        "src/flight_finder/sorter.py",
        "src/flight_finder/cli.py",
        "src/flight_finder/config.py",
        "src/flight_finder/dates.py",
    ]:
        src = Path(rel).read_text(encoding="utf-8")
        assert "import httpx" not in src, f"{rel} no debe importar httpx"
        assert "import requests" not in src, f"{rel} no debe importar requests"
        assert "from httpx" not in src, f"{rel} no debe importar httpx"
        assert "from requests" not in src, f"{rel} no debe importar requests"


def test_secreto_no_en_card():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    offers = normalize_response(payload, provider="serpapi", currency="USD")
    card = format_offer_card(offers[0], 1)
    for marker in _SECRET_MARKERS:
        assert marker not in card, f"card no debe contener {marker!r}"


def test_secreto_no_en_export(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    offers = normalize_response(payload, provider="serpapi", currency="USD")
    path = export_csv(tmp_path / "vuelos.csv", offers, top_n=1)
    content = path.read_text(encoding="utf-8")
    for marker in _SECRET_MARKERS:
        assert marker not in content, f"CSV no debe contener {marker!r}"
