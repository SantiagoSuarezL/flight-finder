# Session Log — ARCHIVO — flight-finder

> Detalle completo verbatim de sesiones pasadas. No se lee automático.
> Consultar solo si hace falta el detalle exacto de archivos/tests/decisiones
> de una fase vieja.

## Archivo de sesiones

### Sesión 11 — 2026-09-21 — Mimo v2.6 Flash via OpenCode (Fase 11.6 cli) (verbatim)

- **Regla de trabajo vigente:** un comando de terminal por vez (uv, luego graphify); cerrar cada sub-fase con PROTOCOLO_SALIDA.
- **Fase 11.6 — cli ✅:** `cli.py` reescrito sobre `FlightsClient` (fuera Duffel/`cfg.mode`/tokens LIVE): key por `PROVIDERS[provider].env_var` (`SERP_API`/`SEARCH_API_IO`) vía dotenv; **estimación impresa ANTES del primer request** (`Search combinations` / `Maximum API requests: N (+top_n drill-down)` / `Provider:` / `Search-only operation`); búsqueda **por combo** (`search_round_trip` en loop — asocia cada offer con su `(departure, return_date)` para poder drill-downar; `search_combinations` aplanaría y perdería esa asociación); drill-down del top N solo si `drill_down: top_n` y hay `departure_token`, con `attach_inbound` y fallos no fatales (queda sin expandir); banner `print_banner(cfg.provider)`.
- **Tests:** `test_cli.py` ampliado a 6 (parser×2, config faltante, key faltante limpia sin red, **orden**: estimación antes del marker `--- REQUEST ---` con FakeClient, `drill_down: off` no invoca `drill_down` y muestra label `not expanded`).
- **Estado tests:** **118/118** (config 25 + models 30 + flights_client 26 + dates 5 + filters 12 + sorter 4 + presenter 12 + cli 6); entry point `uv run flight-finder --help` OK; `graphify update` (655 nodos, 1111 edges).
- **Pendiente (esperando mención del usuario):** 11.7 tests restantes (`test_duffel_client`/`test_no_booking`/`test_live_mode`) + borrar `duffel_client.py` + fixtures Duffel huérfanos (`sample_offers.json`/`live_offers.json`) + `scripts/check_duffel.py` → `check_provider.py` + suite completa, cierre Fase 11.

### Sesión 1 — 2026-09-21 — Muse Spark vía OpenCode (verbatim)

- Fase 0 (parcial): scaffolding con `pyproject.toml`, `uv.lock`, `.venv` (Python 3.11.15) vía `uv sync --extra dev`, `.env.example`, `src/flight_finder/`, `data/`, `tests/`, `scripts/check_duffel.py`; decisión SDK documentada en README (duffel-api archivado 2023 → `httpx` directo). Falta verificación live (token del usuario).
- Fase 1 (✅): `models.py` (Offer/Slice/Segment + `normalize_offers`, duraciones ISO8601), fixtures sintéticas 0/1/2 escalas en `tests/fixtures/sample_offers.json`, `tests/test_models.py` 10/10 sin red.
- Regla proyecto: `uv` gestor principal excluyente (tech_stack.md, README); Regla de Oro 1.1 (no usar `pip` en `.venv`).
- Observación abierta: API keys en `opencode.json` versionado (observations.md).
- Roadmap: Fase 1 ✅, Fase 0 [ ] pendiente token; próxima Fase 2 (filtros).

### Sesión 10 — 2026-09-21 — Mimo v2.6 Flash via OpenCode (Fase 11.5 presenter) (verbatim)

- **Regla de trabajo vigente:** un comando de terminal por vez (uv, luego graphify); cerrar cada sub-fase con PROTOCOLO_SALIDA.
- **Fase 11.5 — presenter ✅:** reescrito según TECHNICAL_SPEC §14/§7: `print_banner(provider, searched_at)` → `SOURCE: SerpApi|SearchApi (Google Flights)` + `SEARCHED AT` + honesty NOTE (fuera banners TEST/SANDBOX/MODE); cards `PRICE/AIRLINE (nombre+código)/OUTBOUND/RETURN/STOPS/LAYOVERS/DURATION/BAGGAGE/CARBON/AIRPLANE` con vuelta `not expanded (cheapest return included in price)` si `inbound is None`; tabla con columnas Aéreolíneas+Carbon; `_row` CSV/HTML: dentro `emissions_kg`/`escalas_*`/`airline_logo`, fuera `owner`/`expires_at`/`live_mode`; eliminados `format_owner`/`format_expires`/`format_live_mode`/lógica `ZZ`.
- **Tests:** `test_presenter.py` reescrito (12 tests: banner×2, tabla, vuelta no expandida, card drill-down con ausencia de EXPIRATION/LIVE/TEST/ZZ, CSV/HTML columnas nuevas y ausentes Duffel, ASCII `->`); fixtures serpapi (+drill-down).
- **Estado tests:** **112/112** (config 25 + models 30 + flights_client 26 + dates 5 + filters 12 + sorter 4 + presenter 12); `graphify update` (647 nodos, 1092 edges).
- **Pendiente (esperando mención del usuario):** 11.6 `cli.py` (wiring provider+estimación+drill_down; hoy aún lee `cfg.mode`/duffel), 11.7 tests restantes+borrado Duffel+scripts (`check_duffel.py`→`check_provider.py`, fixtures Duffel huérfanos), cierre Fase 11 (suite completa).

### Sesión 9 — 2026-09-21 — Mimo v2.6 Flash via OpenCode (Fase 11.4 filters/sorter) (verbatim)

- **Regla del usuario (sesión):** un comando de terminal por vez (primero `uv`, después `graphify`, etc.) — los llamados paralelos traban la máquina.
- **Fase 11.4 — filters/sorter ✅ (sin cambios de arquitectura):** `filters.py` pasa a tolerar `inbound=None` (contrato Fase 11: el filtro corre antes del drill-down → solo ida; la vuelta se verifica solo si `attach_inbound` la expandió); `sorter.py` `total_amount` → `price` (1 línea, resto intacto).
- **Tests:** `test_filters.py` reescrito sobre fixtures Google Flights (`serpapi_response.json`: directo/FRA/ATL/MEX/FRA+ZRH; `serpapi_drilldown.json` con vuelta vía ATL) — 12 tests incl. MEX-vs-US, fail-closed ZZZ, `inbound=None`, vuelta tras drill-down; `test_sorter.py` helper al nuevo `Offer`; `test_live_filters.py` **eliminado** (normalize_offer/live_mode Duffel, casos plegados en test_filters).
- **Estado tests:** **100/100** (`config 25 + models 30 + flights_client 26 + dates 5 + filters 12 + sorter 4`); `graphify update` (637 nodos, 1080 edges). Fixtures Duffel (`sample_offers.json`, `live_offers.json`) quedan huérfanos — borrar en 11.7.
- **Pendiente (esperando mención del usuario):** 11.5 `presenter.py`, 11.6 `cli.py`, 11.7 tests restantes (`test_presenter`/`test_cli`/`test_no_booking`/`test_duffel_client`/`test_live_mode`) + borrado Duffel + scripts, cierre Fase 11 (suite completa).

### Sesión 8 — 2026-09-21 — Mimo v2.6 Flash via OpenCode (Fase 11.3 config) (verbatim)

- **Fase 11.3 — config ✅:** `config.py` migrado al contrato Fase 11: `provider: serpapi|searchapi` obligatorio (fuerza `Literal`, sin default), `currency` ISO 4217 3 mayúsculas (default `USD`), `search.drill_down: top_n|off` (default `top_n`); fuera `mode: test|live`; `main()` ahora imprime `provider=` en vez de `mode=`.
- **Tests config:** `test_config.py` ampliado (+9: provider obligatorio/inválido/searchapi, currency default/inválida, drill_down off/default/inválido, max_combinations; ejemplo valida `provider`/`currency`/`drill_down` y ausencia de `mode`, +carga directa del ejemplo); `test_config_live.py` **eliminado** (tests de `mode`, obsoletos).
- **Estado tests:** 81/81 en `test_config.py + test_models.py + test_flights_client.py`; `test_dates.py` 5/5. Rojos pre-existentes (no de esta sub-fase): `test_filters.py` (import `normalize_offers` viejo) y `test_sorter.py` (constructor `Offer` viejo) — se migran en 11.4/11.7; `cli.py`/`presenter.py` aún usan `cfg.mode`/`live_mode` — 11.5/11.6.
- **Verificación manual:** `uv run python -m flight_finder.config config.example.yaml` → `... provider=serpapi, max_combinations=6` (exit 0, sin traceback).
- **Pendiente (esperando mención del usuario):** 11.4 filters/sorter, 11.5 `presenter.py`, 11.6 `cli.py`, 11.7 tests restantes+borrado Duffel+scripts, cierre Fase 11 (suite completa + graphify update — grafo ya actualizado hoy: 640 nodos, 1094 edges).

### Sesión 7 — 2026-09-21 — Mimo v2.6 Flash via OpenCode (Fase 11 código, por sub-fases) (verbatim)

- **Regla de trabajo del usuario:** avanzar la Fase 11 en sub-fases (11.1 models, 11.2 flights_client, 11.3 config, …), sin pasar a la siguiente hasta que él lo mencione; al cerrar CADA sub-fase, aplicar PROTOCOLO_SALIDA.md (memoria).
- **Fase 11.1 — models ✅:** `models.py` reescrito (contrato Google Flights §4/§13): `Segment` (nombre+código derivado de flight_number/logo, `is_overnight`, `legroom`, `airline_logo`), `Layover`, `Slice.layovers`, `Offer` con `price`/`currency`/`provider`/`retrieved_at`/`inbound: Slice|None`/tokens opacos; fuera `live_mode`/`owner`/`expires_at`/`BaggageInfo`/ISO8601. Fail-closed: sin `price`/`currency`/`flights` → `ValueError`. Helpers: `normalize_response`, `normalize_itinerary`, `attach_inbound`, `extract_itineraries`, `parse_price_insights`. Fixtures nuevos (`serpapi/searchapi_response.json` + `*_drilldown.json`, 5 itinerarios c/u); `test_models.py` **30/30**.
- **Fase 11.2 — flights_client ✅:** `flights_client.py` nuevo con registry `PROVIDERS` (serpapi/searchapi: base URL + `SERP_API`/`SEARCH_API_IO`), `map_search_params` puro (`type`/`flight_type`, stops numérico vs enum, `exclude_conns`/`excluded_connecting_airports`, travel_class 1/economy), `FlightsClient` GET-only con guard SEARCH-ONLY (solo `engine=google_flights`), auth 401/403, backoff 429/5xx (3 intentos, `Retry-After`), batch stats, `drill_down(departure_token)`, mensaje de key faltante con env var. Sin métodos de reserva (test estructural incluido). `test_flights_client.py` **26/26**.
- **Estado tests:** sub-fases 11.1+11.2 verdes en conjunto (56/56: `uv run pytest tests/test_models.py tests/test_flights_client.py`). El resto de la suite aún no corre (imports/cli con Duffel viejos) — se migra en las sub-fases siguientes.
- **Pendiente (esperando mención del usuario):** 11.3 `config.py`, 11.4 filters/sorter, 11.5 `presenter.py`, 11.6 `cli.py`, 11.7 tests restantes+borrado Duffel+scripts, cierre Fase 11 (suite completa + graphify update).

### Sesión 6 — 2026-09-21 — Mimo v2.6 Flash via OpenCode (Fase 11 docs) (verbatim)

- **Cambio de proveedor Duffel → SerpApi/SearchApi (ambos Google Flights).** Docs oficiales + pricing de ambos revisados; usuario pidió soportar los dos (`provider: serpapi|searchapi`, sin fallback automático) e informe primero. Informe **`docs/INFORME_FASE_11.md`** escrito con **GO**: §6 semántica round-trip (`departure_token`, vuelta requiere 2da llamada por itinerario → `search.drill_down: top_n`), §7 costos (SerpApi Free 250/mes, SearchApi 100, cache 1h), §12 Fase 10b **CANCELADA** (SIN tarjeta; sin tarjeta on file no hay nada que desbloquear en Duffel).
- **Specs migrados completos:** `README.md`, `docs/TECHNICAL_SPEC.md` (§1 GET-only, §3 schema+provider, §4 modelos Google Flights, §11 banner obsoleto, §12 contrato+cuota, §13 modelos sin live_mode/owner/expires_at/BaggageInfo, §14 presenter, §15 credenciales SERP_API/SEARCH_API_IO), `docs/ARCHITECTURE.md` (§3 tabla con fila SerpApi/SearchApi, §4.4 decisión vigente, §10 SEARCH-ONLY, §11 control de cuota, §12 presentación), `docs/IMPLEMENTATION_PLAN.md` (nota de estado, fases 8-10 históricas, **+Fase 11 PASO 1-3 y Fase 12**), `config.example.yaml` (`provider: serpapi`, `currency: USD`, `search.drill_down: top_n`, fuera `mode`), `.env.example` (solo `SERP_API`/`SEARCH_API_IO` — **keys reales ya en `.env` del usuario; no leer `.env` ni pedirle acceso**).
- **Nueva regla del usuario:** antes de CUALQUIER request real, revisar el código/params primero (dry-run) — cuota gratuita limitada, no se gasta en debugging; documentada en TECHNICAL_SPEC §12.4, ARCHITECTURE §11, IMPLEMENTATION_PLAN Fases 11-12.
- `graphify update .` ejecutado (542 nodos, 916 edges).
- **Pendiente:** Fase 11 PASO 2-3 (código: `flights_client.py`, `models.py`, `config.py`, `presenter.py`, `cli.py`, tests sin red con fixtures de ambos proveedores) + Fase 12 (validación real: 1 combo/proveedor, revisando código antes de cada request). Código `src/` sin tocar aún.

### Sesión 5 — 2026-09-21 — Muse Spark vía OpenCode (Fase 10 TEST) (verbatim)

- Fase 10 ✅ adaptada a TEST: `config.yaml` `mode:test` `before 2026-09-28` 10-15d 6 combos con `duffel_test_*` → 3049 ofertas en bruto, `SOURCE/MODE: TEST / SANDBOX WARNING` + cards con `AIRLINE/MARKETING/OPERATING/STOPS/DURATION/BAGGAGE 1 checked, 1+ carry-on/EXPIRATION 21:57/LIVE-TEST: TEST` + `ZZ (TEST/SANDBOX: Duffel Airways)` en #4 y #10 + `vuelos.html` con columnas `owner/marketing/operating/baggage/expires_at/live_mode`; `FILTERED BY US:0` (todas directas en esta ventana, filtro probado en `test_live_filters.py` con ATL/MIA→REJECT y MEX→OK).
- LIVE bloqueado por billing on file (KYC pide tarjeta: "no up-front costs ... only pay for what you use", verificado por el usuario; addendum en `docs/INFORME_FASE_8.md` §11). Usuario sin tarjeta → decisión TEST; Fase 9 ya live-ready (`duffel_client.py:39` SEARCH-ONLY, 99/99 tests).
- Estado: 99/99 tests, roadmap 11/12 fases (0-10 ✅ TEST, 10b LIVE opcional futura con `live_*`); `graphify update` pendiente.

### Sesión 12 — 2026-09-21 — Mimo v2.6 Flash via OpenCode (Fase 11.7 cierre) (verbatim)

- **Regla de trabajo vigente:** un comando de terminal por vez (uv, luego graphify); cerrar cada sub-fase con PROTOCOLO_SALIDA.
- **Fase 11.7 — cierre ✅:** `test_no_booking.py` reescrito (3 tests: ningún módulo fuera de `flights_client` importa httpx/requests; secretos `api_key`/`SERP_API`/`SEARCH_API_IO`/`Bearer ` ausentes de card y CSV); borrados `test_duffel_client.py`, `test_live_mode.py`, `src/flight_finder/duffel_client.py`, fixtures `sample_offers.json`/`live_offers.json`, scripts `check_duffel.py`/`capture_fixtures.py`/`manual_search.py`, artefacto `vuelos.html`; nuevo `scripts/check_provider.py` (presencia de `SERP_API`/`SEARCH_API_IO` en `.env`, sin red); `pyproject.toml` description → SerpApi/SearchApi.
- **Estado tests:** **121/121** (`uv run pytest -q`); `graphify update` (571 nodos, 960 edges). Referencias "duffel" restantes: solo como provider inválido en tests de rechazo + docs históricos.
- **Cierre Fase 11:** roadmap ✅, INDEX → próxima Fase 12 (validación real con dry-run previo).

### Sesión 13 — 2026-09-22 — Muse Spark via OpenCode (Fase 12 validación real) (verbatim)

- **PASO 1 dry-run ✅:** params verificados sin red para ambos proveedores (1 combo searchapi + 6 combos serpapi, estimations 1 y 8); hallazgo: `separate_tickets=1` (INFORME_FASE_11 §11) no se enviaba a SearchApi → agregado en `flights_client.py` + assert en `test_flights_client.py`; suite **121/121**.
- **PASO 2 ✅ (2 requests):** `config.validate.yaml` (searchapi 1 combo 10-15/10-25) → 8 válidas, cheapest 1119 USD Iberia IB152 directo; mirror serpapi (temp, borrado) → 9 válidas, mismo cheapest + Avianca vía CLO (doméstica, filtro OK). Semántica price RT confirmada cross-provider; estimación previa correcta en ambas.
- **PASO 3 ✅ sin gastar cuota:** `vuelos.csv` previo (serpapi 6 combos + drill top_n, 2 filas Iberia 1119) corroborado contra PASO 2 (misma IB152 17:20); columnas CSV según spec. No re-ejecutado (regla: no repetir CLI para probar).
- **Cuota sesión:** 2 requests (1+1); total Fase 12 ~10 (8 previos + 2). Pendiente usuario (PASO 4): dashboards + spot-check manual vs google.com/travel/flights.
- **Cierre:** roadmap Fase 12 ✅, INDEX actualizado, `graphify update` (571 nodos, 960 edges); `config.validate.yaml` queda como helper 1-combo (untracked).

### Sesión 14 — 2026-09-22 — Muse Spark via OpenCode (Fase 13 web UI + links) (verbatim)

- **Links + núcleo ✅:** `presenter.google_flights_url()` puro + `LINK:` honesto en cards (wiring CLI vía `combo_of`); `search.py` extraído (`plan/estimate/run_search`, CLI wrapper con salida idéntica); `rows_for_export` para CSV en memoria.
- **Web ✅ (`web.py` stdlib, 127.0.0.1):** form → estimación+confirm (0 requests previos), token un solo uso + PRG 303 (doble click/refresh = replay, nunca re-ejecuta), store 32/TTL 15min con evicción, topes UI 50/31, escapes + error genérico sin detalle; entry `flight-finder-web`.
- **Verificación ✅:** suite **137/137** (121 + 4 links + 12 web); smoke real GET/estimación/404 OK con **0 requests** (sin POST /run); `uv sync` regeneró el entry point.
- **Docs:** README (sección web), ARCHITECTURE §7 (excepción local), TECHNICAL_SPEC §2, IMPLEMENTATION_PLAN Fase 13; `graphify update`.
- **Cuota sesión:** 0 requests. Pendiente usuario: probar `flight-finder-web` en navegador + PASO 4 Fase 12 (dashboards/spot-check).

### Sesión 15 — 2026-09-22 — Muse Spark via OpenCode (Fase 13.5 async + preset) (verbatim)

- **Preset óptimo ✅:** `config.example.yaml` top_n 10→3 (6 combos + drill 3 = 9 req) + assert en `test_config.py`; fallback web igual; README con números nuevos.
- **Async ✅:** `/run` lanza thread y redirige en ~30ms; `run_search` con `on_progress`/`should_cancel` (CLI intacto); página pending con progreso X/Y + Cancelar → resultado parcial etiquetado; error interno genérico sin detalle.
- **Verificación ✅:** suite **140/140**; e2e real con 1 request (searchapi 1 combo): pending visto, SOURCE/LINK/1119/CSV OK; `graphify update`.
- **Cuota sesión:** 1 request (autorizado). Pendiente usuario: probar web en navegador + PASO 4 Fase 12.
