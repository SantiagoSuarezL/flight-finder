# INFORME Fase 11 — Cambio de proveedor: Duffel → SerpApi/SearchApi (Google Flights)

**Fecha:** 2026-09-21
**Estado:** GO para migrar a SerpApi + SearchApi (ambos, con abstracción `provider`). Informe previo sin código: nada se ejecutó ni se editó en esta fase. **Fase 10b (LIVE Duffel) queda CANCELADA** — el stack Duffel completo queda obsoleto tras la migración.

**Pregunta a responder:** ¿Pueden SerpApi (`serpapi.com/google-flights-api`) y SearchApi (`searchapi.io/docs/google-flights-api`) reemplazar a Duffel y devolver vuelos **reales** (inventario Google Flights) dentro de la arquitectura actual, sin tarjeta ni KYC?

**Respuesta corta:** **Sí.** Ambos exponen el mismo scraping de Google Flights con API key simple (registro web, sin tarjeta — SearchApi lo dice explícito: "No credit card required. Sign up for 100 free requests"; SerpApi tiene plan Free de 250 búsquedas/mes). Los datos son precios y horarios reales mostrados por Google Flights — resuelve de raíz el bloqueo sandbox de Duffel (addendum Fase 8 §Billing). El costo real de la migración **no** es el auth sino la **semántica round-trip**: Google Flights devuelve la ida con precio total del round trip + `departure_token`; los segmentos de vuelta requieren una segunda llamada (§6).

---

## 1. Current architecture (verificada 2026-09-21, 99/99 tests)

Flujo `cli.py` orquesta: `config.py load_config()` → `dates.py:25 generate_date_combinations()` (pares `(ida, vuelta)`: salida única + estadía min..max → `max_days-min_days+1` combos) → `duffel_client.py DuffelClient` (único módulo con red; `search_round_trip()` = **1 POST con 2 slices** por combo) → `models.py normalize_offer()` → `filters.py is_offer_valid()` (fail-closed por país con `data/country_airports.json`) → `sorter.py sort_offers()` → `presenter.py print_offers()` + CSV/HTML.

- Guard SEARCH-ONLY (`duffel_client.py:39` + `tests/test_no_booking.py`): lista cerrada de endpoints, ningún `orders`/`payments`.
- `models.py` Fase 9: `Offer` con `live_mode` (fail-closed, Regla de Oro 9.1), `owner`, `expires_at`, `BaggageInfo`, marketing/operating carrier.
- `presenter.py`: banner `SOURCE: Duffel / MODE: TEST|LIVE`, cards con `EXPIRATION`/`BAGGAGE`/`LIVE-TEST`, CSV/HTML con `owner`/`carriers`/`baggage`/`expires_at`/`live_mode`.
- Config: `mode: test|live`, `max_combinations`, tokens Duffel en `.env`.

**Por qué migrar (decision del usuario):** Duffel exige tarjeta on file para desbloquear LIVE (addendum INFORME_FASE_8 §Billing, verificado 21-09). TEST devuelve `ZZ`/sandbox no real. Los dos proveedores nuevos devuelven inventario Google Flights real con solo una API key.

## 2. Cómo se usan — SerpApi (`https://serpapi.com/google-flights-api`)

**Request:** `GET https://serpapi.com/search?engine=google_flights&api_key=KEY&...` (todo por query params; `engine` y `api_key` requeridos).

**Parámetros principales (verificados en la doc oficial):**
- `departure_id`/`arrival_id`: IATA 3 letras (`BOG`, `MAD`) o kgmid (`/m/02_286`); múltiples separados por coma. No requeridos formalmente, pero sin ellos no hay búsqueda.
- `type`: `1` round trip (default) | `2` one way | `3` multi-city (usa `multi_city_json`, cada tramo con key `date`).
- `outbound_date` (requerido si `type` 1/2) + `return_date` (requerido si `type=1`), formato `YYYY-MM-DD`.
- Localización: `gl` (país), `hl` (idioma), `currency` (default `USD`).
- `travel_class` `1`-`4`; pasajeros `adults`/`children`/`infants_in_seat`/`infants_on_lap`.
- `sort_by` `1`-`6` (top/price/departure/arrival/duration/emissions).
- Filtros: `stops` `0`-`3` (any/nonstop/1-stop/2-stops-or-fewer); `include_airlines`/`exclude_airlines` (IATA 2 chars o `STAR_ALLIANCE`/`SKYTEAM`/`ONEWORLD`, mutuamente excluyentes); `bags` (solo carry-on); `max_price`; `outbound_times`/`return_times` (`4,18` o `4,18,3,19`); `emissions=1`; `layover_duration` (`"90,330"`); `exclude_conns` (conexiones excluidas, IATA); `max_duration` (min); `show_hidden`; `exclude_basic` (solo US doméstico con `gl=us`); `deep_search`.
- `selected_flights_json`: fija itinerario segmento a segmento (no lo usamos).
- **Tokens:** `departure_token` (para round trip: obtener las vueltas de una ida elegida; incompatible con `booking_token`) y `booking_token` (opciones de reserva). **Doc oficial: "To obtain the returning flight information for Round Trip (1), you need to make another request using a departure_token".**
- `no_cache` (cache 1h; **las cacheadas no cobran**), `async`, `output: json|html|md`, `zero_trace` (enterprise).

**Respuesta:** `best_flights[]` + `other_flights[]`; cada itinerario: `flights[]` (segmentos: `departure_airport{name,id,time}` con `time` **combinado** `"2026-03-03 10:10"`, `arrival_airport`, `duration` min, `airplane`, `airline` **nombre** (`"British Airways"`), `airline_logo` URL, `travel_class`, `flight_number` (`"BA 301"`), `ticket_also_sold_by[]`, `legroom`, `extensions[]`), `layovers[]` (`duration`, `name`, `id` IATA, `overnight`), `total_duration`, `carbon_emissions{this_flight, typical_for_this_route, difference_percent}`, `price` (número), `type`, `extensions[]` (p. ej. `"Checked baggage for a fee"`), y `departure_token` (round trip) o `booking_token` (one way). Además `price_insights{lowest_price, price_level, typical_price_range[], price_history[[ts]]}` y `airports[]`.

## 3. Cómo se usan — SearchApi (`https://www.searchapi.io/docs/google-flights-api`)

**Request:** `GET https://www.searchapi.io/api/v1/search?engine=google_flights&api_key=KEY&...` (api_key por query param **o** header `Authorization: Bearer`). **`departure_id` y `arrival_id` son Required**; spec OpenAPI descargable en `/openapi/google_flights.yaml`.

**Diferencias de parámetros vs SerpApi (mismos conceptos, nombres string):** `flight_type: round_trip|one_way|multi_city`; `travel_class: economy|premium_economy|business|first_class`; `stops: any|nonstop|one_stop_or_fewer|two_stops_or_fewer`; `sort_by: top_flights|price|departure_time|arrival_time|duration|emissions`; `multi_city_json` usa `outbound_date` por tramo (SerpApi usa `date`).

**Extras que SearchApi tiene y SerpApi no (verificados):**
- `carry_on_bags` **y** `checked_bags` separados (SerpApi solo carry-on).
- `included_connecting_airports` (además de `excluded_connecting_airports`).
- `layover_duration_min`/`layover_duration_max` (cap 1800 min) en vez de rango string.
- `show_cheapest_flights` + `expanded_search` (más resultados, más lento).
- `separate_tickets=1` (oculta self-transfer/split tickets).
- Máx 9 pasajeros documentado.

**Respuesta:** mismo core (`best_flights`/`other_flights`) **más** `detected_extensions` (estructurado: `legroom_short`, `carbon_emission`, `wifi`, `seat_type`), `is_overnight`/`is_often_delayed` por segmento, `selected_flights[]` (tras `booking_token`), `booking_options[]` (con `fare_type`, `baggage_prices` `"1st checked bag: 150"`, `booking_request{url,post_data}`, `booking_phone`, `is_split_booking`, `local_prices`), `airlines{alliances,airlines,hubs}` (dropdown de filtros con códigos), `passenger_assistance_links`, `baggage_allowance_links`, `cheaper_alternatives[]`, `carbon_emissions.lowest_route`. **Segmento con `date` (`"2024-11-19"`) y `time` (`"17:00"`) SEPARADOS.** `price_insights` con `typical_price_range{low_price,high_price}` (objeto) y `price_history[{price,iso_date}]` (objetos) — formas distintas a SerpApi.

**Flujo de tokens idéntico a SerpApi:** round trip → ida con `departure_token` → segunda llamada para vueltas → `booking_token` → booking options. One way → `booking_token` directo.

## 4. Comparativa lado a lado

| Concepto | SerpApi | SearchApi |
|---|---|---|
| Base URL | `https://serpapi.com/search` | `https://www.searchapi.io/api/v1/search` |
| Auth | `api_key` query param | `api_key` query **o** `Bearer` header |
| Tipo de vuelo | `type=1/2/3` (numérico) | `flight_type=round_trip/one_way/multi_city` |
| Hora del segmento | `time: "2026-03-03 10:10"` (junto) | `date` + `time` separados |
| `price_insights` | ranges como array, history `[[ts]]` | objetos `{low,high}` / `[{price,iso_date}]` |
| Equipaje param | `bags` (solo carry-on) | `carry_on_bags` + `checked_bags` |
| Conexiones excluidas | `exclude_conns` | `excluded_connecting_airports` (+ included) |
| Layover | `layover_duration="90,330"` | `layover_duration_min/max` |
| Profundidad | `deep_search` | `show_cheapest_flights`+`expanded_search` |
| Separate tickets | no documentado | `separate_tickets=1` para ocultar |
| Extra en respuesta | `legroom`, `output=md`, cache 1h gratis | `detected_extensions`, `booking_options`, `airlines`, `cheaper_alternatives` |
| Cobro | solo búsquedas exitosas; **cacheadas gratis** (1h) | solo respuestas 200; rate limit 20% de créditos/hora |
| Free tier | **250/mes**, 50/hr | **100 requests** al registrarse, sin tarjeta |
| Plan pago mínimo | $25/mo (1.000) | $40/mo (10.000, $4/1.000) |

**Conclusión de la comparativa:** la respuesta de ambos es el mismo scraping de Google Flights con shapes casi idénticos → **una sola capa de normalización sirve para los dos**; el cliente por proveedor se reduce a: base URL + estilo de auth + mapeo de nombres de params + parseo de `time` del segmento + forma de `price_insights`.

## 5. Mapeo config actual → parámetros Google Flights

| `config.yaml` actual | Param SerpApi | Param SearchApi |
|---|---|---|
| `search.origin` BOG | `departure_id=BOG` | igual |
| `search.destination` MAD | `arrival_id=MAD` | igual |
| `search.passengers: 1` | `adults=1` | igual |
| `search.cabin_class: economy` | `travel_class=1` | `travel_class=economy` |
| `search.max_combinations` | (client-side, igual que hoy) | igual |
| `departure.before`/`fixed_date` | `outbound_date` | igual |
| `stay.min/max_days` (genera vuelta) | `return_date` | igual |
| `max_stops: 2` | `stops=3` (2 stops or fewer) | `stops=two_stops_or_fewer` |
| `avoid.airports: [ATL]` | `exclude_conns=ATL` (server-side) | `excluded_connecting_airports=ATL` |
| `avoid.countries: [US]` | **sin equivalente** → client-side `filters.py` con `layovers[].id` + `country_airports.json` (igual que hoy) | igual |
| *(nuevo)* `currency` | `currency` (default USD) | igual |
| *(nuevo)* `provider: serpapi\|searchapi` | — | — |

Filtros server-side (`stops`, `exclude_conns`) se envían como **optimización de cuota** (menos resultados que luego se descartan), pero `filters.py` client-side sigue siendo la fuente de verdad fail-closed (defense in depth, no confiamos en el filtro del tercero).

## 6. Semántica round-trip y matemática de requests (el cambio más importante)

**Hoy (Duffel):** 1 request por combo → oferta completa (segmentos ida+vuelta, precio total, `expires_at`).
**Google Flights (ambos):** 1 request por combo `(outbound_date, return_date)` → listado de **idas**; cada una con `price` = total del round trip (en los ejemplos oficiales de SearchApi, la ida con `departure_token` precio 490 coincide con las `booking_options` del round trip elegido, precio 490 — **a verificar en la primera llamada real**) y con `departure_token`. **La vuelta no viene**; requiere 1 llamada extra por itinerario elegido.

Opciones:

- **A (recomendada):** mantener semántica round-trip. 1 request por combo (ranking por precio total RT) + drill-down `departure_token` solo para el top N post-filtro/orden (p. ej. N=10 → +10 requests). Presenta ida+vuelta completas como hoy. Estimación previa impresa: `combos 6 / max requests 6+N / provider: X`.
- **B:** drill-down `off` — v1 muestra solo ida + precio RT con etiqueta honesta "vuelta implícita, precio total round trip". Mínimo costo, menos información.
- **C:** one-way (`type=2`): 1 request por fecha, cambia el producto (PRD es round trip). Descartada.

Config nuevo: `search.drill_down: top_n|off` (default `top_n`). Con Free tiers: 6 combos + 10 drill = 16 requests/ejecución → SerpApi da para ~15 ejecuciones/mes, SearchApi ~6 (o cache 1h de SerpApi hace gratuitas las re-ejecuciones). **Regla del usuario: antes de cada request real, revisar el código/params primero (dry-run) — no gastar la cuota en pruebas.**

## 7. Costos (verificados en pricing pages oficiales, 2026-09-21)

| | SerpApi | SearchApi |
|---|---|---|
| Sin tarjeta | Free $0 | "No credit card required" |
| Free | **250 búsquedas/mes**, 50/hr | **100 requests** (signup) |
| Cobro | solo exitosas; cacheadas (1h) y fallidas **gratis**; 1 búsqueda = 1 crédito sin importar resultados | solo HTTP 200; fallidas gratis |
| Rate limit | throughput/hr por plan (50 en free) | **20% de los créditos del plan por hora** |
| Legal | "Legal Shield" desde plan Production ($150/mo) | "Legal Protection Guarantee" desde Production ($100/mo); free/developer sin cobertura |

Para el uso de este proyecto (6 combos + drill-down, decenas de búsquedas/mes): **gratis en ambos**. No hay KYC, no hay "billing on file", no hay fee por búsqueda como Duffel ($0.005 excess).

## 8. Proposed changes

1. **Abstracción `provider`** — `config.py`: `provider: serpapi|searchapi` (reemplaza `mode: test|live`) + `currency` (default USD; hoy Duffel devolvía EUR). `.env`: **`SERP_API`** (SerpApi) / **`SEARCH_API_IO`** (SearchApi) — nombres ya creados por el usuario en su `.env` local (2026-09-21); nunca en YAML, nunca en git. `DUFFEL_*` fuera de `.env.example`.
2. **Un único módulo de red** (doctrina actual conservada) — `duffel_client.py` → `flights_client.py`: registro `PROVIDERS` con base_url/auth/mapper de params/parse de `time` + normalización compartida `normalize_google_flights_response()`; `httpx` GET; backoff 429/5xx reutilizado; batch con stats `consultadas/con_resultados/fallidas` reutilizado; estimación previa `combos / max requests (con drill) / provider`.
3. **Guard SEARCH-ONLY adaptado** — GET-only; ningún POST (el booking de Google es `booking_request{url,post_data}` — **no se implementa nunca**); test estructural actualizado: sin `post_data`, sin `requests.post`, sin `orders`/`payments`.
4. **`models.py` rework** — `Segment`: `departure/arrival_airport{name,id,date,time}`, `airline` (nombre), `airline_code` (derivado del prefijo de `flight_number` "IB 212" → IB, o del filename del `airline_logo` ".../70px/IB.png"), `flight_number`, `duration`, `travel_class`, `airplane`, `is_overnight`, `legroom`. `Layover{id,name,duration,overnight}` (alimenta `filters.py`). `Offer`: `price` (número) + `currency`, `total_duration`, `carbon_emissions`, `layovers`, `baggage: Optional[str]` (strings de `extensions`, sin estructura Duffel), `booking_token/departure_token: Optional[str]` (opaco, no usado), `provider`, `retrieved_at`. **Fuera:** `live_mode` (Regla de Oro 9.1 queda obsoleta — se archiva con su reemplazo: *fail-closed ahora sobre `price`/`segments` ausentes + todo Offer lleva `provider`+`retrieved_at`*), `expires_at`, `owner`, `BaggageInfo`.
5. **`presenter.py`** — banner `SOURCE: SerpApi|SearchApi (Google Flights) / SEARCHED AT: <ts>` (adiós TEST/SANDBOX); etiqueta honesta obligatoria: "precios mostrados por Google Flights, no ofertas reservables; precio final puede variar al reservar". Cards: `AIRLINE (nombre+código)/STOPS/LAYOVERS/DURATION/BAGGAGE string/CARBON`. CSV/HTML: fuera `expires_at`/`live_mode`/`owner`; dentro `emissions`/`layovers`/`airline_logo`.
6. **Filtros** — `filters.py`/`dates.py`/`sorter.py` **sin cambios funcionales** (los layovers alimentan el mismo chequeo por país fail-closed; `country_airports.json` intacto). Envío server-side de `stops`/`exclude_conns` como optimización de cuota.
7. **Docs** — `README`, `docs/TECHNICAL_SPEC.md` (§1 cliente HTTP, §13 live_mode), `docs/ARCHITECTURE.md` (§5.1-5.2 flujo), `docs/IMPLEMENTATION_PLAN.md` (nuevas fases + 10b cancelada), `config.example.yaml`, `.env.example`.

## 9. Files affected

| Archivo | Cambio | Riesgo |
|---|---|---|
| `src/flight_finder/duffel_client.py` | **Eliminado** → `flights_client.py` (+ `providers.py` mapeo fino) | Medio (núcleo de red) |
| `src/flight_finder/models.py` | Contrato Google Flights (§8.4) | Medio |
| `src/flight_finder/config.py` | `provider`+`currency`, fuera `mode` | Bajo |
| `src/flight_finder/presenter.py` | Banners/columnas nuevas (§8.5) | Medio |
| `src/flight_finder/cli.py` | Orquestación + estimación con drill-down | Bajo |
| `src/flight_finder/filters.py`, `dates.py`, `sorter.py` | Sin cambios funcionales | Bajo |
| `tests/` | Fixtures nuevas de ambos proveedores (respuestas reales capturadas), tests Duffel eliminados | Medio |
| `scripts/check_duffel.py` | → `scripts/check_provider.py` | Bajo |
| `config.example.yaml`, `.env.example`, `README.md`, `docs/*.md` | Actualización post-aprobación | Bajo |

## 10. Tests affected

Conservar verde todo lo que no es Duffel (filtros/país, dates, sorter, config core, presenter base). Reemplazar/adaptar:
- Normalización: fixtures de ambos proveedores; hora combinada (SerpApi) vs separada (SearchApi); `price_insights` array vs objeto; malformados → `None`/`ValueError` según §8.4 (fail-closed en `price`/`segments`).
- Mapeo de params por proveedor (`type=2` vs `flight_type=one_way`, `stops`, `exclude_conns`...).
- Auth: `api_key` en URL (SerpApi) vs Bearer opcional (SearchApi); key faltante → error limpio sin traceback.
- 429/5xx/backoff, vacío, batch stats: mismos tests adaptados al cliente nuevo.
- Guard: sin POST / sin `post_data` / sin `orders|payments` en `src/flight_finder/`.
- Drill-down: token por itinerario, conteo de requests acotado a top N, estimación impresa.

## 11. Risk analysis

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| **Semántica RT distinta** (precio del listado ida = total RT con vuelta implícita; verificar significado exacto) | Alta | Medio | Primera llamada real con 1 combo y verificación manual vs google.com/travel/flights; drill-down top N; etiqueta honesta en presenter. |
| **APIs de scraping** (ambos dependen del DOM/estado de Google Flights; cambios de UI rompen los dos a la vez) | Media | Medio | Abstracción con 2 proveedores (fallback); fixtures fijan el schema; tests sin red. |
| **Equipaje degradado** (strings; `baggage_prices` solo en SearchApi tras drill/book) | Alta | Bajo | Mostrar string textual + "no confirmed by API" cuando falte; no inventar. |
| **Aerolíneas por nombre, no IATA** | Alta | Bajo | Código derivado de `flight_number`/`airline_logo` filename; mapeo nombre→IATA solo para display. |
| **Separate tickets** (SearchApi las puede incluir; SerpApi sin param documentado) | Media | Bajo | SearchApi: `separate_tickets=1` (ocultar). SerpApi: detectar en primera llamada real y decidir (label u omitir). |
| **Tokens efímeros** (`departure_token`/`booking_token` opacos, caducan) | Media | Bajo | Search-only: se guardan solo para drill-down inmediato; nunca persistir ni prometer booking. |
| **Costo/cuota** (agotar free tier con ventanas grandes) | Baja | Bajo | `max_combinations` + drill `top_n` acotado + estimación previa; cache 1h SerpApi para re-runs; monitorear dashboard. |
| **Legal** (scraping vía tercero; free tiers sin Legal Shield) | Baja | Bajo | Uso personal, volumen mínimo; responsabilidad ToS entre usuario y proveedor; documentado. |

## 12. GO / STOP

**GO — con condiciones:**

1. Usuario con API keys ya en `.env` (`SERP_API`, `SEARCH_API_IO` — free, sin tarjeta).
2. Fase 11 (docs + código, sin red): actualizar specs (§8.7) e implementar abstracción + clientes + normalización + presenter + guard + tests sin red (fixtures sintéticas con shapes de §2-§3).
3. **Regla de cuota (del usuario, 2026-09-21):** antes de CUALQUIER request real, revisar el código y los params primero (dry-run). La cuota gratuita es limitada (SerpApi 250/mes, SearchApi 100) — no gastar intentos en pruebas; para eso están fixtures y mocks.
4. Fase 12 (validación real): **1 combinación** por proveedor primero — verificar `price` semántica RT (§6), forma real de `time`/`price_insights`, presencia de separate tickets en SerpApi, y comparación manual contra google.com/travel/flights. Solo después, 6 combinaciones.
5. **Fase 10b CANCELADA.** Duffel sale del stack (código y docs); sin tarjeta on file no hay nada que desbloquear allí.
6. STOP si: el free tier exige tarjeta, la respuesta real difiere estructuralmente de la documentación, o el precio RT del listado no es comparable con Google Flights UI (re-evaluar §6 antes de seguir).

---

**Fuentes (verificadas 2026-09-21):** `serpapi.com/google-flights-api` (params, tokens, response, cache 1h), `serpapi.com/pricing` (Free 250/mes, cobro por búsqueda exitosa, cacheadas gratis), `searchapi.io/docs/google-flights-api` (params Required departure/arrival, flight_type enums, booking_options, airlines, OpenAPI spec), `searchapi.io/pricing` (100 requests free sin tarjeta, $4/1.000 en Developer, solo 200 cobra, rate limit 20% créditos/hora).
