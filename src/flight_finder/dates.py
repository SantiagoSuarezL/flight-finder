"""Generación de combinaciones de fecha (ida, vuelta).

Función pura: sin I/O, sin red, sin estado. Recibe los modelos ya validados
de `config.py` y devuelve pares `(fecha_ida, fecha_vuelta)` a consultar
contra la API (una combinación = al menos una llamada de API en Fase 5).

Decisión explícita sobre `departure.before` (IMPLEMENTATION_PLAN.md Fase 4,
RNF-04 del PRD): **`before` se interpreta como fecha ÚNICA de salida** (el
día límite), no como ventana de salidas posibles. Es decir, `before:
2026-09-28` genera las mismas combinaciones que `fixed_date: 2026-09-28`.
Justificación: cada combinación extra es una llamada de API adicional
(costo + tiempo de respuesta); una ventana implícita desde hoy hasta `before`
podría disparar decenas de llamadas sin que el usuario lo note. Si en el
futuro se quiere una ventana real de salidas, será un flag explícito aparte,
no una reinterpretación silenciosa de `before`.
"""

from __future__ import annotations

from datetime import date, timedelta

from flight_finder.config import DepartureConfig, StayConfig


def generate_date_combinations(
    departure: DepartureConfig,
    stay: StayConfig,
) -> list[tuple[date, date]]:
    """Genera pares (ida, vuelta) ordenados, sin duplicados.

    Con salida D y estadía min..max: `[(D, D+min), ..., (D, D+max)]`
    → exactamente `max_days - min_days + 1` combinaciones.
    """
    outbound = departure.fixed_date
    if outbound is None:
        outbound = departure.before
    assert outbound is not None  # garantizado por validación de config.py
    return [
        (outbound, outbound + timedelta(days=days))
        for days in range(stay.min_days, stay.max_days + 1)
    ]
