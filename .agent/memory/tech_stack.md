# Tech Stack — flight-finder

> Se completa la primera vez durante el bootstrap (ver BOOTSTRAP.md),
> leyendo ARCHITECTURE.md/TECHNICAL_SPEC.md UNA vez. Después de eso, este
> archivo se actualiza SOLO si un cambio de stack/arquitectura es inamovible
> (ver PROTOCOLO_SALIDA.md §1) — no en cada sesión.

## Stack Actual

**Lenguaje:** Python 3.11+ (TECHNICAL_SPEC.md §1)

**Gestión de dependencias:** `pyproject.toml` + `uv.lock`, entorno virtual `.venv` gestionado por **uv (gestor principal y excluyente — no usar `pip` directo)**. Comandos: `uv sync --extra dev`, `uv add <pkg>`, `uv run <cmd>`. TECHNICAL_SPEC.md §1 indica "venv o uv"; convención del proyecto (instrucción usuario 21-09-2026): uv siempre, por ser más rápido y liviano.

**Dependencias principales (TECHNICAL_SPEC.md §1 — actualizado Fase 11):**
- Cliente HTTP: `httpx` directo (GET-only) contra `https://serpapi.com/search` o `https://www.searchapi.io/api/v1/search` según `provider` (SerpApi/SearchApi, ambos exponen Google Flights; `duffel-api` SDK queda fuera del stack — decisión documentada en README e INFORME_FASE_11).
- Configuración: YAML (`PyYAML`), validado con `pydantic` (recomendado)
- Variables sensibles: `.env` + `python-dotenv`, nunca en YAML — claves: **`SERP_API`** (SerpApi) y **`SEARCH_API_IO`** (SearchApi); `DUFFEL_*` eliminadas (ya en `.env` del usuario, no leer `.env` ni pedir acceso)
- CLI: `argparse` es suficiente (no se requiere `click`/`typer` para el alcance actual, pero se puede usar si simplifica)
- Salida en terminal: `rich` (recomendado) para tablas; alternativa aceptable `tabulate`
- Testing: `pytest`

**Arquitectura (TECHNICAL_SPEC.md §2 — estructura de carpetas propuesta):**
```
flight-finder/
├── pyproject.toml
├── .env.example
├── README.md
├── config.example.yaml
├── src/
│   └── flight_finder/
│       ├── __init__.py
│       ├── cli.py                 # entrypoint, argparse, orquesta el flujo
│       ├── config.py              # carga y valida config.yaml (pydantic models)
│       ├── dates.py               # generación de combinaciones de fechas
│       ├── flights_client.py      # único punto de contacto con SerpApi/SearchApi (GET-only, registry PROVIDERS)
│       ├── filters.py             # motor de filtrado de escalas prohibidas
│       ├── models.py              # dataclasses/pydantic models internos (Offer, Segment, Slice)
│       ├── sorter.py              # ordenamiento de resultados
│       ├── search.py              # núcleo compartido CLI/web: plan + estimación + run_search (Fase 13)
│       ├── web.py                 # UI web local stdlib en 127.0.0.1 (form, estimación+confirm, run idempotente; Fase 13)
│       └── presenter.py           # formateo de salida en terminal + export (+ google_flights_url, Fase 13)
├── data/
│   └── country_airports.json      # mapeo IATA -> país ISO (dataset versionado)
└── tests/
    ├── test_filters.py
    ├── test_dates.py
    ├── test_config.py
    └── fixtures/
        └── serpapi_response.json / searchapi_response.json (+ drill-down)
                                  # shapes de ambos proveedores, tests sin red (Fase 11)
```
Flujo y componentes según ARCHITECTURE.md §5.1-5.2: config.yaml → loader de config → generador de combinaciones de fecha (usa stay) + data/country_airports.json → cliente Google Flights (SerpApi/SearchApi, offer search + drill-down departure_token) → motor de filtrado → ordenador → presentador (tabla terminal + export opcional CSV/HTML). CLI pura, sin backend/frontend separados, sin servidor HTTP, sin estado persistente entre ejecuciones (ARCHITECTURE.md §7).

**Configuración tooling:** `pyproject.toml` + `uv.lock`, entorno virtual `.venv` gestionado por uv (TECHNICAL_SPEC.md §1); test runner `pytest` vía `uv run pytest` (TECHNICAL_SPEC.md §1).

**Suite de tests:** `pytest` (TECHNICAL_SPEC.md §1). Estructura de tests prevista en TECHNICAL_SPEC.md §2 y criterios por fase en IMPLEMENTATION_PLAN.md: Fase 1 `test_models.py` con fixtures, Fase 2 `test_filters.py` (caso ATL), Fase 3 `test_config.py`, Fase 4 `test_dates.py`. Al momento del BOOTSTRAP el repo no está inicializado (solo README.md de 1 línea; sin pyproject.toml ni código), por lo que no hay tests ejecutables aún.

---

## Protocolos Críticos (Inamovibles)

> Protocolos Críticos solo para invariantes que costó aprender — no transcribir
> el spec. Regla corta y prescriptiva acá. La historia completa (bug, root
> cause, código) vive en `lessons_learned.md` o `lessons_learned_archive.md` —
> referenciada por número `(Ref: X.Y)`, nunca repetida palabra por palabra.

1. Toda gestión de entorno y ejecución se hace con `uv` (`uv sync --extra dev`, `uv add`, `uv run`); nunca `pip` directo en `.venv` (Ref: 1.1).
2. Todo string visible en consola (errores, `print`, logs, presenter) usa solo ASCII seguro (`->` no `→`); verificar en consola real (Ref: 5.1).
3. Antes de CUALQUIER request real a SerpApi/SearchApi, revisar el código y los params primero (dry-run) — la cuota gratuita es limitada (SerpApi 250/mes, SearchApi 100) y no se gasta en debugging; para eso están fixtures y mocks (Ref: INFORME_FASE_11 §12, TECHNICAL_SPEC §12.4).
