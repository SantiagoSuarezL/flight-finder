"""Genera `data/country_airports.json` desde OurAirports.

Fuente: https://davidmegginson.github.io/ourairports-data/airports.csv
Dataset OurAirports (dominio público). Se filtra a aeropuertos reales
(large/medium/small, con código IATA) y se mapea IATA → país ISO 3166-1
alpha-2 (`iso_country`).

Uso:
    uv run python scripts/build_country_airports.py
"""

import csv
import io
import json
import urllib.request
from pathlib import Path

SOURCE_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "country_airports.json"

_TYPE_PRIORITY = {"large_airport": 0, "medium_airport": 1, "small_airport": 2}


def main() -> None:
    print(f"Descargando {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as resp:
        text = resp.read().decode("utf-8")

    mapping: dict[str, str] = {}
    best_rank: dict[str, int] = {}
    rows = kept = 0
    for row in csv.DictReader(io.StringIO(text)):
        rows += 1
        rank = _TYPE_PRIORITY.get(row["type"])
        iata = (row["iata_code"] or "").strip().upper()
        iso = (row["iso_country"] or "").strip().upper()
        if rank is None or len(iata) != 3 or len(iso) != 2:
            continue
        kept += 1
        if iata not in mapping or rank < best_rank[iata]:
            mapping[iata] = iso
            best_rank[iata] = rank

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(mapping, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Filas: {rows}, válidas: {kept}, IATA únicos: {len(mapping)}")
    print(f"Escrito en {OUT_PATH}")


if __name__ == "__main__":
    main()
