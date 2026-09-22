"""Entrypoint: config -> fechas -> SerpApi/SearchApi -> normaliza -> filtra -> ordena.

Uso:
    uv run flight-finder [--config otra_busqueda.yaml]

Fase 11 (TECHNICAL_SPEC.md §12/§14): unico modulo que orquesta al cliente
`FlightsClient` (GET-only, SEARCH-ONLY). La estimacion de requests se imprime
ANTES del primer request (regla de cuota, §12.4). Drill-down con
`departure_token` acotado a `search.drill_down: top_n` (§14.2).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from flight_finder.config import ConfigError, load_config
from flight_finder.filters import load_airport_country_map
from flight_finder.flights_client import (
    PROVIDERS,
    FlightsAuthError,
    FlightsClient,
)
from flight_finder.presenter import (
    export_csv,
    export_html,
    make_console,
    print_aggregate_counts,
    print_banner,
    print_filter_summary,
    print_no_results,
    print_offer_cards,
    print_offers,
)
from flight_finder.search import estimate_requests, plan_combinations, run_search

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Buscador de vuelos con filtro de escalas restringidas."
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Archivo de búsqueda (default: config.yaml)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    console = make_console()

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    try:
        airport_country_map = load_airport_country_map(
            DATA_PATH / "country_airports.json"
        )
    except (OSError, ValueError) as exc:
        print(f"No se pudo cargar el dataset de aeropuertos: {exc}",
              file=sys.stderr)
        return 1

    combinations, effective, truncated = plan_combinations(cfg)

    load_dotenv()
    env_var = PROVIDERS[cfg.provider].env_var
    api_key = os.getenv(env_var, "")
    try:
        client = FlightsClient(cfg.provider, api_key)
    except FlightsAuthError as exc:
        print(exc, file=sys.stderr)
        return 1

    print_filter_summary(
        console,
        origin=cfg.search.origin,
        destination=cfg.search.destination,
        n_combinations=len(effective),
        avoid_countries=cfg.avoid.countries,
        avoid_airports=cfg.avoid.airports,
        max_stops=cfg.max_stops,
    )
    # Estimacion previa OBLIGATORIA antes del primer request (§12.4):
    # 1 request por combinacion + hasta top_n drill-down si esta activo.
    drill_requests = (
        cfg.output.top_n if cfg.search.drill_down == "top_n" else 0
    )
    max_requests = estimate_requests(cfg, len(effective))
    console.print(
        f"Search combinations: {len(effective)}"
        + (
            f" (de {len(combinations)} generadas;"
            f" {truncated} omitidas por max_combinations)"
            if truncated
            else ""
        )
    )
    drill_note = (
        f" (+{drill_requests} drill-down top_n)"
        if drill_requests
        else " (drill-down off)"
    )
    console.print(
        f"Maximum API requests: {len(effective)}{drill_note}"
        f" -> max {max_requests}"
    )
    console.print(f"Provider: {cfg.provider} ({env_var})")
    console.print(
        "Search-only operation. No booking/payment operation will be performed."
    )

    try:
        outcome = run_search(cfg, client, airport_country_map)
    except FlightsAuthError as exc:
        print(exc, file=sys.stderr)
        return 1
    ordered = outcome.ordered
    discard_reasons = outcome.discard_reasons
    total_raw = outcome.total_raw
    combo_of = outcome.combo_of

    print_banner(console, cfg.provider)
    if ordered:
        print_offers(console, ordered, top_n=cfg.output.top_n)
        console.print("")
        print_offer_cards(console, ordered, top_n=cfg.output.top_n,
                          combo_of=combo_of)
        # Conteos agregados (§14.2)
        c = Counter(discard_reasons)
        filtered_country = sum(
            v for k, v in c.items() if "pais excluido" in k
        )
        filtered_airport = sum(
            v for k, v in c.items() if "aeropuerto excluido" in k
        )
        filtered_stops = sum(
            v for k, v in c.items() if "Exceso de escalas" in k
        )
        filtered_unverified = sum(
            v for k, v in c.items() if "no verificado" in k
        )
        print_aggregate_counts(
            console,
            valid=len(ordered),
            filtered_by_country=filtered_country,
            filtered_by_airport=filtered_airport,
            filtered_by_max_stops=filtered_stops,
            filtered_by_unverified=filtered_unverified,
        )
    else:
        print_no_results(console, total_raw, discard_reasons)

    if cfg.output.export == "csv":
        path = export_csv("vuelos.csv", ordered, top_n=cfg.output.top_n)
        console.print(f"Exportado a {path}")
    elif cfg.output.export == "html":
        path = export_html("vuelos.html", ordered, top_n=cfg.output.top_n)
        console.print(f"Exportado a {path}")
    return 0


def _entrypoint() -> None:
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nBusqueda interrumpida por el usuario.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    _entrypoint()
