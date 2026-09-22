"""Ordenamiento de ofertas válidas (precio, duración como desempate)."""

from __future__ import annotations

from collections.abc import Callable

from flight_finder.models import Offer

_KEYS: dict[str, Callable[[Offer], object]] = {
    "total_price": lambda o: o.price,
    "duration": lambda o: o.total_duration_minutes,
}


def sort_offers(
    offers: list[Offer],
    *,
    primary: str = "total_price",
    secondary: str | None = "duration",
) -> list[Offer]:
    """Devuelve las ofertas ordenadas (ascendente) sin mutar la entrada."""
    if primary not in _KEYS:
        raise ValueError(f"Criterio de orden desconocido: {primary!r}")
    if secondary is not None and secondary not in _KEYS:
        raise ValueError(f"Criterio de orden desconocido: {secondary!r}")
    keys = [primary] + (
        [secondary] if secondary and secondary != primary else []
    )
    return sorted(offers, key=lambda o: tuple(_KEYS[k](o) for k in keys))
