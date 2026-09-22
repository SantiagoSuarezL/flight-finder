# Roadmap — flight-finder

> Estado (✅/[ ]) + referencia. Detalle vive en lessons/session_log.
> La lista de fases se completa UNA vez durante el bootstrap, copiando los
> nombres/orden de fases desde IMPLEMENTATION_PLAN.md. Después de eso, solo
> se actualiza el estado (✅/[ ]) de cada fase — no se vuelve a copiar el
> plan completo.

## Fases

Copiadas literalmente de IMPLEMENTATION_PLAN.md (nombres y orden):

- [x] **Fase 0 — Preparación del entorno** (21-09-2026: verificación live HTTP 200 con test token por el usuario)
- [x] **Fase 1 — Modelos y normalización de datos** (21-09-2026: `models.py`, fixtures 0/1/2 escalas, `pytest tests/test_models.py` 10/10 sin red)
- [x] **Fase 2 — Dataset de aeropuertos/países y motor de filtrado** (21-09-2026: `country_airports.json` 8802 IATA desde OurAirports, `filters.py` fail-closed, 6 tests incl. caso ATL)
- [x] **Fase 3 — Configuración** (21-09-2026: `config.py` pydantic + `ConfigError` humano, `config.example.yaml` BOG→MAD, 15 tests, verificado error sin traceback)
- [x] **Fase 4 — Generación de combinaciones de fecha** (21-09-2026: `dates.py` pura, `before` = fecha única de salida (documentado), 5 tests con ejemplo PRD 6 combinaciones)
- [x] **Fase 5 — Cliente de Duffel** (21-09-2026: `duffel_client.py` auth/backoff/batch+stats, 9 tests mock, búsqueda real BOG→MAD 445 ofertas normalizadas OK, fixtures reales capturadas, token falso → error limpio)
- [x] **Fase 6 — Orden y presentación** (21-09-2026: `sorter.py`, `presenter.py` tabla rich + resumen filtros + CSV/HTML, 10 tests)
- [x] **Fase 7 — Integración final (`cli.py`) y pulido** (21-09-2026: entry point `flight-finder --config`, Ctrl+C limpio, README final, e2e real 6 combinaciones → top 10 ordenados)
- [x] **Fase 8 — LIVE search-only: informe previo (sin código)** (21-09-2026: inspección con graphify + docs oficiales Duffel verificados; informe `docs/INFORME_FASE_8.md` con respuesta GO para búsquedas live sin compra/saldo — requiere KYC manual + token live read-only; rate limit vigente 10/60s, excess search $0.005)
- [x] **Fase 9 — LIVE search-only: implementación mínima + tests** (21-09-2026: `config.py` `mode`+`max_combinations`, `models.py` `live_mode`/owner/marketing-operating/baggage/`expires_at`, `duffel_client.py` SEARCH-ONLY `_guard` + `get_offer`, `presenter.py` banners TEST/LIVE + `ZZ` TEST + `format_offer_card` + CSV/HTML enriquecidos, `cli.py` `DUFFEL_LIVE_ACCESS_TOKEN` + estimación previa + `max_combinations` + banner; `live_offers.json` + 40 tests nuevos `SPEC §15.2`; 99/99 tests)
- [x] **Fase 10 — Validación TEST adaptada (LIVE bloqueado por billing)** (21-09-2026: `config.yaml` `mode:test` `before 2026-09-28` 10-15d 6 combos con `duffel_test_*` → 3049 ofertas, banner `MODE: TEST / SANDBOX WARNING`, `ZZ` → `TEST/SANDBOX`, `BAGGAGE`/`EXPIRATION`/`LIVE/TEST` en 10 cards + `vuelos.html` con columnas live; addendum en `docs/INFORME_FASE_8.md` §11; LIVE queda live-ready — requiere tarjeta on file para `live_*`, no implementado por decisión del usuario)
- [!] **Fase 10b — LIVE real (Duffel)** — **CANCELADA** (21-09-2026): exige tarjeta on file que el usuario no tiene; además Duffel sale del stack con la migración de Fase 11 (ver `INFORME_FASE_11.md` §12).
- [x] **Fase 11 — Migración Duffel → SerpApi/SearchApi (docs + código)** (21-09-2026: PASO 1 docs — `INFORME_FASE_11.md` GO + specs migrados; PASO 2-3 por sub-fases: 11.1 models, 11.2 flights_client, 11.3 config, 11.4 filters/sorter, 11.5 presenter, 11.6 cli, **11.7 cierre** — tests/borrado Duffel/scripts; suite **121/121**, `graphify update` 571 nodos/960 edges)
- [x] **Fase 12 — Validación real con ambos proveedores** (22-09-2026: PASO 1 dry-run + `separate_tickets=1` en searchapi; PASO 2 1 combo/proveedor — cheapest 1119 USD IB152 idéntico en ambos, semántica RT confirmada; PASO 3 corroborado vía `vuelos.csv` previo sin re-gastar; suite 121/121. Pendiente usuario PASO 4: dashboards + spot-check google.com/travel/flights)
- [x] **Fase 13 — Interfaz web local + links** (22-09-2026: `google_flights_url` + LINK en cards; `search.py` núcleo compartido (CLI wrapper idéntico); `web.py` stdlib 127.0.0.1 — form, estimación+confirm, token un solo uso + PRG, store 32/TTL 15min, topes UI 50/31; 13.5 corrida async (redirect inmediato, progreso, cancelar parcial) + preset 6+top3 (9 req); suite **140/140**; e2e real 1 request OK; docs README/ARCHITECTURE/SPEC/PLAN)

---

## Pendientes Críticos Detectados

- (Resuelto en Fase 8 — pendiente absorbido por Fases 9-10): presentación `ZZ`/sin `owner`/`live_mode`/equipaje documentado ahora en `docs/INFORME_FASE_8.md` §1-2 y en `IMPLEMENTATION_PLAN.md` Fase 9; no reabrir como pendiente separado.
