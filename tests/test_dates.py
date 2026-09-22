"""Tests de Fase 4: generación de combinaciones de fecha."""

from datetime import date

from flight_finder.config import DepartureConfig, StayConfig
from flight_finder.dates import generate_date_combinations


def _dep(**kwargs):
    return DepartureConfig.model_validate(kwargs)


def _stay(min_days, max_days):
    return StayConfig(min_days=min_days, max_days=max_days)


def test_fixed_date_genera_rango_exacto():
    combos = generate_date_combinations(
        _dep(fixed_date=date(2026, 11, 10)), _stay(10, 12)
    )
    assert combos == [
        (date(2026, 11, 10), date(2026, 11, 20)),
        (date(2026, 11, 10), date(2026, 11, 21)),
        (date(2026, 11, 10), date(2026, 11, 22)),
    ]


def test_before_es_fecha_unica_de_salida_ejemplo_prd():
    # Ejemplo del PRD: before 2026-09-28, estadía 10-15 → 6 combinaciones
    # verificables a mano (28-sep + 10..15 días = 08..13-oct).
    combos = generate_date_combinations(
        _dep(before=date(2026, 9, 28)), _stay(10, 15)
    )
    assert combos == [
        (date(2026, 9, 28), date(2026, 10, 8)),
        (date(2026, 9, 28), date(2026, 10, 9)),
        (date(2026, 9, 28), date(2026, 10, 10)),
        (date(2026, 9, 28), date(2026, 10, 11)),
        (date(2026, 9, 28), date(2026, 10, 12)),
        (date(2026, 9, 28), date(2026, 10, 13)),
    ]


def test_before_y_fixed_date_coincidentes_dan_lo_mismo():
    day = date(2026, 11, 10)
    assert generate_date_combinations(
        _dep(before=day), _stay(10, 15)
    ) == generate_date_combinations(_dep(fixed_date=day), _stay(10, 15))


def test_estadia_de_un_dia_da_una_combinacion():
    combos = generate_date_combinations(
        _dep(fixed_date=date(2026, 11, 10)), _stay(7, 7)
    )
    assert combos == [(date(2026, 11, 10), date(2026, 11, 17))]


def test_es_pura_y_determinista():
    dep, stay = _dep(before=date(2026, 9, 28)), _stay(10, 15)
    first = generate_date_combinations(dep, stay)
    assert generate_date_combinations(dep, stay) == first
    assert len(set(first)) == len(first)  # sin duplicados, ordenada
    assert first == sorted(first)
