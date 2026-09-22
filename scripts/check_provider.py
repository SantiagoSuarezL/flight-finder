"""Smoke check de Fase 11: verifica que las API keys estan en .env.

Sin requests a la red (regla de cuota: dry-run primero; para validar la key
contra el proveedor esta la Fase 12). Uso:

    uv run python scripts/check_provider.py

No forma parte del paquete; es el script suelto que reemplaza a
`check_duffel.py` (INFORME_FASE_11.md §9).
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

REQUIRED = ("SERP_API", "SEARCH_API_IO")


def main() -> int:
    load_dotenv()
    missing = [var for var in REQUIRED if not os.getenv(var, "")]
    for var in REQUIRED:
        state = "FALTA" if var in missing else "OK"
        print(f"{state}: {var}")
    if missing:
        print("Copia .env.example a .env y completa las keys faltantes.")
        return 1
    print("Ambas keys presentes. Listo para dry-run/Fase 12 (sin red aun).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
