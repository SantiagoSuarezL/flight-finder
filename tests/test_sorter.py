"""Tests de Fase 6: ordenamiento."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from flight_finder.models import Offer, Segment, Slice
from flight_finder.sorter import sort_offers


def _offer(oid, price, minutes):
    seg = Segment(
        origin="BOG",
        destination="MAD",
        departure_time=datetime(2026, 10, 5, 8, 0, 0),
        arrival_time=datetime(2026, 10, 5, 18, 0, 0),
    )
    slc = Slice(segments=[seg], duration_minutes=minutes // 2)
    other = Slice(segments=[seg], duration_minutes=minutes - minutes // 2)
    return Offer(
        id=oid,
        price=Decimal(price),
        currency="USD",
        provider="serpapi",
        retrieved_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        outbound=slc,
        inbound=other,
        total_duration_minutes=minutes,
    )


def test_ordena_por_precio_ascendente():
    offers = [_offer("c", "700.00", 600), _offer("a", "500.00", 900),
              _offer("b", "600.00", 700)]
    assert [o.id for o in sort_offers(offers)] == ["a", "b", "c"]
    assert [o.id for o in offers] == ["c", "a", "b"]  # no muta la entrada


def test_desempata_por_duracion():
    offers = [_offer("slow", "500.00", 900), _offer("fast", "500.00", 600)]
    assert [o.id for o in sort_offers(offers)] == ["fast", "slow"]


def test_sin_secundario_y_por_duracion():
    offers = [_offer("slow", "500.00", 900), _offer("fast", "600.00", 600)]
    assert [o.id for o in sort_offers(offers, secondary=None)] == ["slow", "fast"]
    assert [
        o.id for o in sort_offers(offers, primary="duration", secondary=None)
    ] == ["fast", "slow"]


def test_criterio_desconocido_falla():
    with pytest.raises(ValueError, match="desconocido"):
        sort_offers([_offer("a", "1.00", 60)], primary="color")
