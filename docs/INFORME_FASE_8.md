# INFORME Fase 8 — LIVE search-only (sin código)

**Fecha:** 2026-09-21
**Estado:** GO para búsquedas LIVE de solo-lectura (con precondición KYC manual). No requiere compra ni saldo para buscar. Informe previo obligatorio del `IMPLEMENTATION_PLAN.md` Fase 8 — ningún cambio de código ni credenciales se ejecutó en esta fase.

**Pregunta a responder:** ¿Puedo ejecutar búsquedas LIVE reales sin comprar ni pagar vuelos?

**Respuesta corta:** **Sí** — Duffel permite `offer_requests` / `offers` en live sin crear `orders` y sin saldo suficiente para reservar. El coste es $0 por búsqueda hasta exceder el ratio 1500:1 (búsquedas por orden confirmada). El bloqueo no es económico sino de **activación KYC** en el dashboard (ver §3).

---

## 1. Current architecture (verificada 2026-09-21, 59/59 tests)

Flujo `cli.py:50` orquesta: `config.py:181 load_config()` → `dates.py:25 generate_date_combinations()` → `duffel_client.py:55 DuffelClient` (único módulo con red; `httpx`, `Bearer`, `Duffel-Version: v2` en `duffel_client.py:73`) → `models.py:94 normalize_offer()` → `filters.py:57 is_offer_valid()` → `sorter.py:15 sort_offers()` → `presenter.py:82 print_offers()` + CSV/HTML.

- `duffel_client.py:147 search_round_trip()` hace `POST /air/offer_requests?return_offers=true` con 2 slices (ida+vuelta). `duffel_client.py:198 search_combinations()` hace batch secuencial con stats `consultadas / con_resultados / fallidas`; 401 → `DuffelAuthError` inmediato, 429 → backoff exponencial con `Retry-After`, 5xx/timeout → reintento acotado `max_attempts=3` (configurable). Confirmado por `tests/test_duffel_client.py` (429, red, auth, vacío).
- `models.py:39 Segment` actual solo guarda `origin/destination/departure_time/arrival_time/marketing_carrier/flight_number` — **pierde** `operating_carrier`, `owner`, `live_mode`, `expires_at`, `baggage`, duración por segmento. `models.py:58 Offer` solo `id/total_amount/total_currency/outbound/inbound/total_duration` — sin `live_mode`/`owner`/`expires_at`.
- `presenter.py:42 carriers()` etc. solo muestra IATA (p. ej. `BA`/`IB`) y duración agregada; no distingue `marketing vs operating`, no muestra `owner.name`, ni `live_mode`, ni banner TEST/LIVE.
- `cli.py:79 print_filter_summary()` ya imprime filtros y `n_combinations`, pero no estimación `Maximum API requests` ni `Mode: LIVE`, ni declaración runtime `This operation only searches...`.
- Graphify: `cli.py --imports--> duffel_client.py` (1 hop), `DuffelClient` grado 14 conectado a `cli.py`/`capture_fixtures.py`/`manual_search.py`; `Offer` y `normalize_offer` en community 0/4 separados de `duffel_client` — arquitectura limpia, sin bypass.

## 2. Current problems (para el objetivo LIVE)

1. **Sin `live_mode` en pipeline:** el token `duffel_test_*` produce precios no reales (ver §3.2) pero el código nunca lee ni propaga `offer_request.live_mode` / `offer.live_mode`; el usuario vio `ZZ`/`22h34m` clavado sin saber si era sandbox.
2. **Modelos pobres:** se descarta `owner`/`marketing_carrier.name`/`operating_carrier.name`/`expires_at`/`baggage`/`live_mode`; no se puede afirmar "precio real" ni presentar `SOURCE/MODE/SEARCHED AT`.
3. **Sin barrera anti-booking explícita:** `duffel_client.py` no tiene métodos de órdenes, pero no hay test que lo garantice ni declaración runtime; un futuro contribuidor podría añadir `POST /air/orders` sin romper nada.
4. **Sin control LIVE conservador:** `search_combinations()` es secuencial (bien) pero sin rate limiting explícito, sin límite `max_combinations` configurable, y sin estimación previa impresa; con `before` como fecha única hoy no es grave, pero si se amplía la ventana podría disparar decenas de requests.
5. **Presentación confunde TEST con LIVE:** sin banner `MODE: TEST/SANDBOX WARNING` ni `MODE: LIVE SEARCHED AT`.

Nada de esto rompe los 59 tests (todos pasan sin red), pero impide el criterio de éxito `PRD.md §11.10`.

## 3. Duffel LIVE requirements (solo fuentes oficiales vigentes, sept 2026)

> No se asume nada. Todo viene de `duffel.com/docs` y `help.duffel.com`.

### 3.1 Activación de LIVE MODE (precondición manual)

- **Paso 5 del dashboard:** verificar email + verificación KYC — "Collecting information about the individual and business / Verifying information to establish that we know who our customers are" (`docs/guides/getting-started-with-the-dashboard` Step 5). Requiere tipo de negocio, datos personales/empresariales; "Know Your Customer (KYC) obligations ... Every country has its own requirements" (mismo doc).
- **Paso 6:** "Choose how to collect payments and go live with your integration. You've now unlocked Live Mode." Luego dos caminos: (a) Duffel Payments (cobrar tarjetas de clientes) o (b) **"If you choose not to integrate with our Payments API, you can top up the Balance and just utilise the Flights API."** (mismo doc, Step 6). **No hay paso 5/6 que exija tarjeta registrada para solo buscar.**

### 3.2 TEST vs LIVE (precios)

- **Test mode:** "lets you use the Duffel API risk-free, with no danger of spending any money or booking flights you don't want!" (`docs/api/overview/test-mode` Overview). Tokens `duffel_test_*`. "You'll see offers from Duffel Airways. ... `owner.name` will be `Duffel Airways` and its `iata_code` will be `ZZ`." + "you won't see realistic flight schedules or prices." (mismo doc, Duffel Airways).
- **Precios TEST no reales:** Help Centre "Are the flight prices in test mode (sandbox) real?" — "When you're searching for flights in test mode (sandbox) ... the prices you'll see are **not real, live prices**. If you want to see real, live flight prices, you'll need to **activate your account**." (`help.duffel.com` 4410085835282, 2021-11-16, aún referenciado).
- **`live_mode` es la fuente de verdad:** `docs/api/offer-requests` Schema: "`live_mode` boolean — Whether the offer request was created in live mode." (ej. `false`). `docs/api/offers` Schema: idem para `offer.live_mode` (ej. `true`). No se infiere del prefijo del token.

### 3.3 Tarifas — búsqueda vs reserva

- **Pricing page (`duffel.com/pricing`, 2023-05-17, vigente):** Zero up-front costs. "Pay as you go". Fees mensuales:
  - Orders: **$3.00 per confirmed order**
  - Managed Content: **1% total order value** per confirmed order
  - Ancillaries: **$2.00 per paid ancillary**
  - **Excess search fee: $0.005 per excess search** si se excede **1500:1 search-to-book ratio**. Ejemplo: 10 órdenes → 15 000 búsquedas gratis; 25 000 búsquedas → `(25000-15000)*$0.005 = $50`. **No hay fee por búsqueda por debajo del ratio.** No hay mínimo mensual, no hay "coste de activar live".
  - FX 2% solo si hay conversión de moneda.
- **Balance:** "Balance displays the current amount ... you can use to make orders." (`getting-started` Balance). Help "What happens if I don't have enough money ... to book?" — "When paying with your Duffel Balance, you'll need to have enough money to cover the cost of the booking. If you don't, **you won't be able to create your order until you top up**." Puede seguir consultando balance/transacciones sin bloquear búsquedas. Top-up por transferencia bancaria en horario UK (no instantáneo) — irrelevante para solo buscar.

### 3.4 Autenticación y tokens

- `docs/api/overview/making-requests` Authentication: "Send your access token in the `Authorization: Bearer` header." Al crear token puedes elegir **read-only o read-write** (ver `getting-started` Access tokens: "you'll be able to choose whether to give it read-only or read-write access."). Para SEARCH-ONLY ideal: **token read-only** si el dashboard lo ofrece para offer_requests.
- Tokens aislados: "With a testing access token, you'll only be able to access resources created in test mode. With a live access token, you'll only be able to access resources created in live mode." (`test-mode` Overview).

### 3.5 Rate limits

- Help "What is the API rate limit?" (actualizado 08 Sep 2026 10:40): "If you send too many API requests in quick succession, you'll receive a `rate_limit_error` The **default rate limit for search is 10 requests per 60 seconds**, in our live environment. Every response includes a `ratelimit-limit` and `ratelimit-reset` ... Rate limits vary across the API, each endpoint has a separate limit." (antes del 08-09 decía 120; el valor vigente a la fecha de este informe es 10/60s para search — coherente con el cambio documentado el 08-09).
- `docs/api/overview/response-handling`: 429 = `Too Many Requests`. Nuestra implementación actual ya maneja 429 con backoff y `Retry-After` (`duffel_client.py:108`), pero debe reforzarse con límite configurable y no paralelizar.

### 3.6 Ofertas, refresh y caducidad

- Cada `offer` tiene `expires_at`, `owner` (airline object), `total_amount`/`total_currency`, `slices[].segments[]` con `marketing_carrier`/`operating_carrier`/`flight_number`/`departing_at`/`arriving_at`/`duration` (ver `docs/api/offers` muestras). La guía US exige mostrar `operating_carrier.name` prominente (`docs/api/offer-requests/create-offer-request` nota DOT). Para validación live debemos conservar todo eso y verificar `live_mode==true` en request **y** offers.

## 4. What can be done for free

- **Crear cuenta + token TEST:** gratis, instantáneo, sin tarjeta.
- **Búsquedas LIVE (`offer_requests` + `offers`) sin crear órdenes:** gratis hasta el ratio 1500:1; no requieren saldo ni tarjeta. Solo requieren cuenta activada (KYC) y token live (read-only ideal).
- **Uso personal del CLI con `config.yaml` (6 combinaciones ejemplo BOG→MAD, `before 2026-09-28`, `min 10 max 15`):** 6 requests live caen muy por debajo del rate limit 10/60s y del umbral de excess search (necesitarías 0 órdenes para que 6 búsquedas ya computen como exceso, pero el excess fee solo se factura mensualmente y es $0.005 por exceso — 6 búsquedas sin órdenes = 6*0.005 = **$0.03 teórico si facturasen sin órdenes**, pero la doc lo formula como "si excedes 1500 por orden"; con 0 órdenes es ambiguo — ver Riesgos).
- **Conservar TEST para todos los tests automatizados:** sin coste, sin inventario live.

## 5. What could potentially cost money (STOP si aplica)

| Concepto | ¿Cuándo se cobra? | ¿Nos afecta en esta fase? |
|----------|-------------------|---------------------------|
| **Saldo/balance top-up** | Solo al **crear una orden** (`POST /air/orders`) sin fondos suficientes. Búsquedas no lo tocan. | **No** si no implementamos órdenes (barrera §7). |
| **$3 + 1% por orden confirmada** | Por cada `order` creada y confirmada. | **No** — no creamos órdenes. |
| **$0.005 excess search** | Por cada búsqueda por encima de 1500 por orden en el mes. | **Sí, marginalmente:** con 0 órdenes, cualquier búsqueda técnicamente es "exceso" según la fórmula. En la práctica, con 6-10 búsquedas el coste sería $0.03-$0.05/mes si facturasen así; con 1 orden de prueba (que no haremos) son 1500 gratis. **Mitigación:** limitar a **1 combinación** en la primera prueba live y luego a 6; documentar y monitorear `Billing` en dashboard; si Duffel factura el umbral con 0 órdenes, avisa y detén. |
| **FX 2%** | Solo si hay conversión de moneda al pagar. | No en búsquedas. |
| **Tarjeta / datos empresariales** | KYC pide datos personales/empresariales, no tarjeta para buscar. Duffel Payments sí pide Stripe KYC si eliges cobrar tarjetas (opcional). | KYC es **precondición manual** para desbloquear live, pero sin coste. |
| **Activar live** | Sin fee según pricing ("Zero up-front costs"). | Gratis. |

**Conclusión económica:** si el objetivo es **solo buscar**, Duffel **es gratuito en la práctica** para el volumen de este proyecto (decenas de búsquedas/mes), con el único coste potencial residual del excess search con 0 órdenes. **No toques Balance ni Payments**, y no crees órdenes ni "holds" (`POST /air/orders` sin pago también reserva inventario aunque sea hold — está fuera de alcance y generaría riesgo).

## 6. Proposed changes (mínimos, en orden de prioridad del prompt)

1. **TEST/LIVE separation** — `config.py`: `mode: test|live` + `search.max_combinations`; validación estricta; `.env` con `DUFFEL_ACCESS_TOKEN` (test) y `DUFFEL_LIVE_ACCESS_TOKEN` (live) documentados en `README`; detección de modo efectivo por `live_mode` de la respuesta, no por prefijo.
2. **`live_mode`** — `models.py`: nuevo campo `live_mode: bool` en `Offer` (y propagar `offer_request.live_mode` al presenter); `normalize_offer` falla explícito si falta.
3. **Richer Segment/Offer** — `models.py`: `CarrierInfo(iata_code, name)`, `OwnerInfo`, `BaggageInfo`, `duration`, `flight_number`, `marketing/operating_carrier`, `created_at/expires_at` (todo `Optional`).
4. **Airline/owner** — `presenter.py`: prioriza `owner.name`/`marketing_carrier.name`/`operating_carrier.name`; `ZZ` → etiqueta `TEST/SANDBOX`.
5. **Baggage** — `models.py`+`presenter.py`: conservar si viene, mostrar "not confirmed by API" si no.
6. **`expires_at`** — idem.
7. **Live/test presentation** — `presenter.py`: banner `SOURCE: Duffel / MODE: TEST/SANDBOX WARNING...` vs `SOURCE: Duffel / MODE: LIVE SEARCHED AT: <ts>`; fallback TEST si `live_mode` desconocido.
8. **Search-only safety** — `duffel_client.py`: lista cerrada de endpoints (`/air/offer_requests`, `/air/offers` GET/refresh); ningún `POST /air/orders|/payments`; test estructural que falla si aparece `orders`/`payments` en el cliente; declaración runtime antes de live.
9. **Rate limiting** — `duffel_client.py`+`cli.py`: secuencial por defecto, `max_combinations` respetado, backoff 429 con `Retry-After`, estimación previa `Search combinations / Maximum API requests / Mode: LIVE` impresa antes del primer request, logging de `consultadas/con_resultados/fallidas`.
10. **Tests** — nuevos sin credenciales (ver §8).
11. **Documentación** — `README.md` con sección TEST vs LIVE honesta (`Google Flights ≠ Duffel inventory`, `Cheapest valid offer returned by Duffel`).

## 7. Files affected

| Archivo | Cambio | Riego |
|---------|--------|-------|
| `src/flight_finder/config.py` | +`mode`+`max_combinations` | Bajo |
| `src/flight_finder/models.py` | contrato enriquecido §13 spec | Medio (cambio de forma de `Offer`/`Segment`) |
| `src/flight_finder/duffel_client.py` | estimación, declaración runtime, blindaje search-only | Medio |
| `src/flight_finder/presenter.py` | banners, marketing/operating, ZZ, baggage, expires, conteos | Medio |
| `src/flight_finder/cli.py` | orquestación con estimación y modo | Bajo |
| `tests/fixtures/*` | fixtures `live_mode` true/false + carriers | Bajo |
| `tests/test_*.py` | matriz `TECHNICAL_SPEC.md §15.2` | Medio |
| `config.example.yaml` | ejemplo `mode`+`max_combinations`+BOG→MAD `before 2026-09-28` | Bajo |
| `README.md` + `docs/` | sección LIVE honesta | Bajo |
| `.env.example` | documenta `DUFFEL_LIVE_ACCESS_TOKEN` | Bajo |

No se toca: `data/country_airports.json`, `filters.py` (ya fail-closed), `sorter.py`/`dates.py`.

## 8. Tests affected

Conservar los 59 existentes intactos. Añadir (sin red ni credenciales):

- `live_mode` true → banner LIVE; false → TEST+warning; ausente → error explícito.
- `owner.name`+`owner.iata_code`, marketing/operating name+IATA, `ZZ`→TEST.
- Baggage presente/ausente, `expires_at`/`created_at`, flight number, duraciones.
- Outbound+inbound en un solo Offer (nunca ida como TOTAL).
- Filtros `US` en ida y vuelta (`BOG→ATL→MAD` y `MAD→MIA→BOG` rechazadas; `BOG→MEX→MAD` permitida si no hay US), `avoid.airports=[ATL]` independiente.
- Mall-formado/ausente en carriers → `None` sin crashear.
- Aeropuerto sin mapeo → REJECT.
- 429 → backoff+reintento, estimación impresa, `max_combinations` truncado.
- Vacío → mensaje con desglose sin traceback.
- No-booking: `grep -r "orders\|payments\|/air/orders" src/flight_finder/duffel_client.py` debe ser vacío.

## 9. Risk analysis

| Riesgo | Prob. | Impacto | Mitigación |
|--------|-------|---------|------------|
| **Accidental booking** (alguien añade `orders` y lo ejecuta) | Baja si blindamos | Alto | Barrera arquitectónica (§6.8) + test estructural + token read-only en live; revisión que rechaza PR con `POST /air/orders`. |
| **Excess search fee con 0 órdenes** ($0.03-$0.30 para 6-60 búsquedas) | Media | Bajo | Primera prueba **1 combinación**; luego 6; monitorear `Billing`; si aparece cargo, reportar y ajustar. Ratio 1500 es generoso si algún día se confirma 1 orden (no previsto). |
| **KYC bloquea live** (Duffel pide docs adicionales) | Media | Medio | Usuario hace KYC manual en dashboard; sin ello seguimos en TEST sin romper nada. No automatizar KYC. |
| **Rate limit 10/60s en live** (antes era 120) | Media | Medio | Secuencial + backoff con `ratelimit-reset`; no paralelizar; límite `max_combinations` evita ráfagas. |
| **False sense of " cheapest"** (Duffel ≠ Google Flights) | Alta | Medio | Lenguaje obligatorio `Cheapest valid offer returned by Duffel`; comparar manualmente con Google Flights sin scrapear. |
| **Carrier ZZ filtrado como real** | Baja | Medio | Etiquetar `ZZ`/Duffel Airways como TEST siempre. |
| **Top-up por error** (usuario transfiere a Balance pensando que hace falta para buscar) | Baja | Medio | Documentar que buscar no necesita saldo; nunca ofrecer flujo de top-up en el CLI. |

## 10. GO / STOP

**GO — con condiciones:**

1. El usuario debe **activar su cuenta manualmente** en `app.duffel.com` (verificar email + KYC) para desbloquear live. Sin esto, TEST sigue siendo la única fuente y no hay bloqueo.
2. Tras activar, crear un **token LIVE** separado (recomendado **read-only** si el dashboard lo ofrece) y guardarlo como `DUFFEL_LIVE_ACCESS_TOKEN` en `.env` (nunca en YAML, nunca en git). La app elegirá token según `mode`.
3. Primera validación live: **1 sola combinación** (no 6) para confirmar `live_mode==true`, `owner`/`carriers` reales, precios coherentes, outbound+inbound, filtro US, y cero llamadas a `/orders`. Solo después, búsqueda pequeña de 6 combinaciones.
4. No tocar `Balance` ni `Payments` en esta fase.

Si en cualquier punto Duffel exige saldo/tarjeta para **buscar** (no solo para **reservar**) o el dashboard muestra un fee inesperado, **STOP** y re-evaluar antes de más requests.

---

**Fuentes (verificadas 2026-09-21, se citan arriba):** `duffel.com/docs/api/overview/test-mode`, `duffel.com/docs/guides/getting-started-with-the-dashboard` (Steps 5-6), `help.duffel.com` 10229200096786 (rate limit 10/60s, 08 Sep 2026) + 4410085835282 (precios TEST no reales), `duffel.com/pricing` (fees), `duffel.com/docs/api/offer-requests` + `duffel.com/docs/api/offers` (schemas `live_mode`), `duffel.com/docs/api/overview/making-requests` (auth/read-only).

---

## Addendum 2026-09-21 — LIVE bloqueado por billing on file (verificado por el usuario)

**Hallazgo (no predicho en docs):** al completar KYC (`Step 5` del dashboard) Duffel exige **Add billing details** — formulario de tarjeta (número/fecha/CVV) con el mensaje:

> Add billing details — We have pay as you go pricing which means there are no up-front costs or monthly commitments, and you only ever pay for what you use. Learn more

El usuario no tiene tarjeta y no desea añadirla. La pricing page sigue diciendo *"Zero up-front costs"* y el informe original decía "GO con KYC" — ahora el GO queda **condicionado a dejar tarjeta on file** (sin cobro por buscar, solo por `orders` $3+1%, ver §3.3-§3.4). El guard SEARCH-ONLY (`duffel_client.py:39` + `tests/test_no_booking.py`) garantiza que aun con tarjeta no hay booking accidental.

**Decisión (acordada con el usuario):** permanecer en **modo TEST** (`config.yaml: mode: test`, `DUFFEL_ACCESS_TOKEN=duffel_test_*`). **Fase 10 se replanificó a validación TEST** (ver §11 abajo): misma búsqueda BOG→MAD `before 2026-09-28` 10-15 días, 6 combinaciones, verificando banners TEST, `ZZ` → `TEST/SANDBOX`, filtros `US`/`ATL`, `BAGGAGE`/`EXPIRATION`/`LIVE/TEST`. LIVE queda live-ready (código y tests ya implementados en Fase 9, 99/99) — desbloquearlo es solo `DUFFEL_LIVE_ACCESS_TOKEN=live_*` + `mode: live` cuando el usuario disponga de tarjeta virtual/límite bajo.

## 11. Validación TEST Fase 10 (2026-09-21, 6 combinaciones BOG→MAD)

Ejecución real con `duffel_test_*` (ver `config.yaml: mode: test`, `max_combinations: 6`):

```text
Search combinations: 6 / Maximum API requests: 6 / Mode: TEST
SOURCE: Duffel / MODE: TEST / SANDBOX / WARNING: prices and availability are not real market fares
3049 ofertas en bruto, 10 mostradas ordenadas por precio (3049 VALID, 0 FILTERED — todas directas en esta ventana)
```

Top 3 (todos `LIVE/TEST: TEST`, `22h 34m` es el `total_duration` real del fixture, no hardcodeado):
- #1 `564.43 EUR` IB `BOG->MAD` / `MAD->BOG` directo — `AIRLINE: Iberia (IB)` / `BAGGAGE: 1 checked, 1+ carry-on` / `EXPIRATION: 2026-09-21 21:57`
- #2 `565.10 EUR` BA `BOG->MAD` / `MAD->BOG` directo — `British Airways (BA)`
- #4 `571.01 EUR` ZZ `BOG->MAD` / `MAD->BOG` — `ZZ (TEST/SANDBOX: Duffel Airways)` (etiquetado correctamente)

`vuelos.html` exportado con columnas `owner`/`marketing_carrier`/`operating_carrier`/`baggage`/`expires_at`/`live_mode` (`TEST` en 10 filas, `ZZ TEST/SANDBOX` presente). Filtro `US` validado en tests (`is_offer_valid` con `ATL` → `US` rechazado, `MEX` → `MX` permitido); en esta ventana no hubo escalas US que filtrar — comportamiento esperado, conteo `FILTERED BY US: 0` impreso.
