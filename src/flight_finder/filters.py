"""Motor de filtrado de escalas prohibidas — el componente más crítico.

Decisión ante aeropuerto ausente del dataset (IMPLEMENTATION_PLAN.md Fase 2,
TECHNICAL_SPEC.md §5.2/§8): **fail-closed**. Una escala cuyo país no se puede
verificar se trata como riesgo y la oferta se excluye, con motivo explícito
"país no verificado". Justificación: el requisito no negociable del proyecto
es *nunca* mostrar un itinerario con escala prohibida (RF-11 / PRD §2.3);
ante datos faltantes, descartar de más es seguro y descartar de menos no.
El motivo queda visible en la salida para que el usuario pueda completar el
dataset (`data/country_airports.json`) si lo considera un falso positivo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from flight_finder.models import Offer, Slice

PathLike = Union[str, Path]


def load_airport_country_map(path: PathLike) -> dict[str, str]:
    """Carga el mapeo IATA → país ISO 3166-1 alpha-2."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _check_slice(
    slc: Slice,
    tramo: str,
    avoid_countries: set[str],
    avoid_airports: set[str],
    max_stops: int,
    airport_country_map: dict[str, str],
) -> str | None:
    stops = slc.stopover_airports
    if len(stops) > max_stops:
        return (
            f"Exceso de escalas en tramo de {tramo}: "
            f"{len(stops)} > máximo {max_stops}"
        )
    for airport in stops:
        if airport in avoid_airports:
            return f"Escala en {airport} (aeropuerto excluido)"
        country = airport_country_map.get(airport)
        if country is None:
            return (
                f"Escala en {airport} (país no verificado en el dataset; "
                f"se excluye por seguridad)"
            )
        if country in avoid_countries:
            return f"Escala en {airport} (país excluido: {country})"
    return None


def is_offer_valid(
    offer: Offer,
    avoid_countries: set[str],
    avoid_airports: set[str],
    max_stops: int,
    airport_country_map: dict[str, str],
) -> tuple[bool, str | None]:
    """
    Devuelve (True, None) si la oferta cumple todas las restricciones.
    Devuelve (False, motivo) si no, donde `motivo` es human-readable,
    ej. "Escala en ATL (país excluido: US)".
    """
    for slc, tramo in (
        (offer.outbound, "ida"),
        (offer.inbound, "vuelta"),
    ):
        if slc is None:
            # inbound es None hasta el drill-down (contrato Fase 11):
            # el filtro corre antes de expandir la vuelta; solo ida.
            continue
        reason = _check_slice(
            slc, tramo, avoid_countries, avoid_airports, max_stops,
            airport_country_map,
        )
        if reason is not None:
            return False, reason
    return True, None
