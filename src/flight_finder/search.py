"""Nucleo de busqueda compartido por CLI y web (Fase 13).

`run_search` ejecuta la orquestacion pura (sin imprimir): por combo
(`search_round_trip`), normaliza, filtra, ordena y expande el top N con
drill-down. `plan_combinations` calcula las combinaciones efectivas y la
estimacion de requests ANTES de cualquier GET (regla de cuota §12.4).

Ni este modulo ni sus llamantes hacen POST/booking: el unico contacto de
red es `FlightsClient` (GET-only, SEARCH-ONLY).
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from flight_finder.config import FlightFinderConfig
from flight_finder.dates import generate_date_combinations
from flight_finder.filters import is_offer_valid
from flight_finder.flights_client import FlightsAuthError, FlightsError
from flight_finder.models import Offer, attach_inbound, normalize_itinerary
from flight_finder.sorter import sort_offers

log = logging.getLogger(__name__)


def plan_combinations(
    cfg: FlightFinderConfig,
) -> tuple[list[tuple[date, date]], list[tuple[date, date]], int]:
    """(generadas, efectivas, omitidas) segun `max_combinations` (§3.1).

    Puro: sin red. Las efectivas son las primeras N en orden cronologico
    determinista.
    """
    combinations = generate_date_combinations(cfg.departure, cfg.stay)
    effective = combinations[: cfg.search.max_combinations]
    truncated = len(combinations) - len(effective)
    return combinations, effective, truncated


def estimate_requests(cfg: FlightFinderConfig, n_effective: int) -> int:
    """Maximo de GETs de una corrida: 1 por combo + drill-down top N."""
    drill = cfg.output.top_n if cfg.search.drill_down == "top_n" else 0
    return n_effective + drill


def search_kwargs(cfg: FlightFinderConfig) -> dict:
    return dict(
        currency=cfg.currency,
        passengers=cfg.search.passengers,
        cabin_class=cfg.search.cabin_class,
        max_stops=cfg.max_stops,
        avoid_airports=cfg.avoid.airports,
    )


@dataclass
class SearchOutcome:
    """Resultado de `run_search` (listo para presentar en CLI o web)."""

    ordered: list[Offer] = field(default_factory=list)
    combo_of: dict[str, tuple[date, date]] = field(default_factory=dict)
    discard_reasons: Counter = field(default_factory=Counter)
    stats: dict[str, int] = field(
        default_factory=lambda: {
            "consultadas": 0,
            "con_resultados": 0,
            "fallidas": 0,
        }
    )
    total_raw: int = 0
    effective: list[tuple[date, date]] = field(default_factory=list)
    truncated: int = 0
    cancelled: bool = False  # True si should_cancel freno la corrida


def run_search(
    cfg: FlightFinderConfig,
    client,
    airport_country_map: dict,
    on_progress=None,
    should_cancel=None,
) -> SearchOutcome:
    """Busca las combinaciones efectivas y devuelve el outcome ordenado.

    `client`: `FlightsClient` real o fake con la misma interfaz
    (`search_round_trip` / `drill_down` + context manager). Abre el cliente
    (`with`) y lo cierra al terminar, incluido el drill-down del top N.
    `FlightsAuthError` se propaga (key invalida = detener todo); otros
    `FlightsError` por combo se registran como fallidas sin abortar.
    `on_progress(consultadas, total)` se llama tras cada combo (la web lo
    usa para la pagina de progreso; el CLI lo ignora). Si `should_cancel()`
    es verdadero, no se lanzan mas requests y se devuelve lo conseguido
    hasta ahi (el request en vuelo, si hay, termina normal).
    """
    _, effective, truncated = plan_combinations(cfg)
    out = SearchOutcome(effective=list(effective), truncated=truncated)
    valid: list[Offer] = []
    kwargs = search_kwargs(cfg)
    total = len(effective)

    def cancelled() -> bool:
        try:
            return bool(should_cancel and should_cancel())
        except Exception:  # noqa: BLE001 — un callback roto no frena nada
            return False

    def report() -> None:
        if on_progress is not None:
            try:
                on_progress(out.stats["consultadas"], total)
            except Exception:  # noqa: BLE001 — idem
                pass

    with client:
        for departure, return_date in effective:
            if cancelled():
                out.cancelled = True
                log.info("Busqueda cancelada por el usuario tras %d combos",
                         out.stats["consultadas"])
                break
            out.stats["consultadas"] += 1
            try:
                raw_itineraries = client.search_round_trip(
                    cfg.search.origin,
                    cfg.search.destination,
                    departure,
                    return_date,
                    **kwargs,
                )
            except FlightsAuthError:
                raise
            except FlightsError as exc:
                out.stats["fallidas"] += 1
                log.warning(
                    "Combinacion %s/%s fallida (se continua): %s",
                    departure.isoformat(),
                    return_date.isoformat(),
                    exc,
                )
                report()
                continue
            out.total_raw += len(raw_itineraries)
            if raw_itineraries:
                out.stats["con_resultados"] += 1
            for raw in raw_itineraries:
                try:
                    offer = normalize_itinerary(
                        raw,
                        provider=cfg.provider,
                        currency=cfg.currency,
                        offer_id=(
                            f"{cfg.provider}_{len(valid) + len(out.discard_reasons)}"
                        ),
                    )
                except ValueError as exc:
                    out.discard_reasons[
                        f"Respuesta con formato inesperado: {exc}"
                    ] += 1
                    continue
                out.combo_of[offer.id] = (departure, return_date)
                ok, reason = is_offer_valid(
                    offer,
                    avoid_countries=set(cfg.avoid.countries),
                    avoid_airports=set(cfg.avoid.airports),
                    max_stops=cfg.max_stops,
                    airport_country_map=airport_country_map,
                )
                if ok:
                    valid.append(offer)
                else:
                    out.discard_reasons[reason or "descartada"] += 1
            report()

        log.info(
            "Batch completo: %d consultadas, %d con resultados, %d fallidas",
            out.stats["consultadas"],
            out.stats["con_resultados"],
            out.stats["fallidas"],
        )

        out.ordered = sort_offers(
            valid, primary=cfg.sort.primary, secondary=cfg.sort.secondary
        )

        # Drill-down (§6/§14.2): DENTRO del `with client` — el httpx.Client
        # queda abierto hasta terminar de expandir el top N.
        if out.ordered and cfg.search.drill_down == "top_n":
            for i, offer in enumerate(out.ordered[: cfg.output.top_n]):
                if cancelled():
                    out.cancelled = True
                    log.info("Drill-down cancelado por el usuario")
                    break
                if not offer.departure_token:
                    continue
                entry = out.combo_of.get(offer.id)
                if entry is None:
                    continue
                departure, return_date = entry
                try:
                    raw_returns = client.drill_down(
                        offer.departure_token,
                        origin=cfg.search.origin,
                        destination=cfg.search.destination,
                        departure=departure,
                        return_date=return_date,
                        **kwargs,
                    )
                except FlightsError as exc:
                    log.warning(
                        "Drill-down de %s fallido (se muestra sin expandir): %s",
                        offer.id,
                        exc,
                    )
                    continue
                if raw_returns:
                    try:
                        out.ordered[i] = attach_inbound(offer, raw_returns[0])
                    except ValueError as exc:
                        log.warning(
                            "Drill-down de %s con forma inesperada: %s",
                            offer.id,
                            exc,
                        )
    return out
