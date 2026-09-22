# IMPLEMENTATION PLAN — Buscador de Vuelos con Filtro de Escalas Restringidas

**Relacionado:** `PRD.md`, `ARCHITECTURE.md`, `TECHNICAL_SPEC.md`

Este plan está pensado para ejecutarse con Claude Code u opencode, fase por
fase, verificando cada una antes de avanzar a la siguiente. Cada fase indica su
objetivo, qué construir, y un criterio de "hecho" verificable.

> **Estado 2026-09-21:** Fases 0-10 completadas con **Duffel** como fuente
> (estado detallado en `.agent/memory/roadmap.md`). La fuente cambió a
> **SerpApi/SearchApi (Google Flights)** — ver `INFORME_FASE_11.md` (GO) y
> las **Fases 11-12** al final de este plan. **Fase 10b (LIVE Duffel)
> CANCELADA** (sin tarjeta on file no había nada que desbloquear allí, y el
> stack Duffel sale del proyecto). Las Fases 8-10 de abajo quedan como
> registro histórico de la era Duffel.

---

## Fase 0 — Preparación del entorno

**Objetivo:** tener el proyecto inicializable y la cuenta de Duffel lista antes
de escribir lógica de negocio.

- [ ] Crear cuenta en Duffel (app.duffel.com/join) y generar un **test access
      token** desde el dashboard (Developers → Access tokens). El token de test
      no cobra ni reserva vuelos reales, es suficiente para todo el desarrollo.
- [ ] Confirmar en la documentación vigente de Duffel (developers.duffel.com)
      si el SDK oficial de Python (`duffel-api` o el nombre que tenga en PyPI a
      la fecha) está actualizado y soporta `offer_requests`; si no, usar
      `httpx`/`requests` directo. Documentar la decisión en el README.
- [ ] Inicializar el repo: `pyproject.toml`, entorno virtual, estructura de
      carpetas según `TECHNICAL_SPEC.md` §2.
- [ ] Crear `.env.example` con `DUFFEL_ACCESS_TOKEN=` (vacío) y añadir `.env`
      real (con el token de test) a `.gitignore`.

**Criterio de hecho:** se puede hacer una llamada mínima de prueba a la API de
Duffel desde un script suelto (no integrado aún al proyecto) y recibir una
respuesta 200, confirmando que el token funciona.

---

## Fase 1 — Modelos y normalización de datos

**Objetivo:** poder tomar una respuesta cruda de Duffel y convertirla en los
modelos internos (`Offer`, `Slice`, `Segment`) definidos en `TECHNICAL_SPEC.md` §4,
sin lógica de filtrado todavía.

- [ ] Implementar `models.py` con los modelos internos.
- [ ] Guardar 1-2 respuestas reales de Duffel (anonimizadas si hace falta) como
      fixtures en `tests/fixtures/sample_offers.json`, incluyendo al menos un
      caso con escala y uno directo.
- [ ] Implementar la función de normalización (respuesta cruda → `list[Offer]`).
- [ ] Test: dado el fixture, la normalización produce el número correcto de
      `Offer`, con `stopover_airports` calculados correctamente para itinerarios
      con 0, 1 y 2 escalas.

**Criterio de hecho:** `pytest tests/test_models.py` (o donde se ubique) pasa en
verde usando solo los fixtures, sin llamar a la red.

---

## Fase 2 — Dataset de aeropuertos/países y motor de filtrado

**Objetivo:** implementar el corazón del proyecto: el filtro de escalas
prohibidas, con la garantía de que nunca deja pasar un falso negativo.

- [ ] Construir `data/country_airports.json`: mapeo IATA → ISO de país. Puede
      generarse desde una fuente pública abierta (ej. datasets de OpenFlights o
      similar) — **decidir la fuente y documentarla en el README**, dado que no
      existe un requerimiento previo sobre cuál usar.
- [ ] Decidir explícitamente y documentar en el código (docstring en
      `filters.py`) el comportamiento ante un aeropuerto no encontrado en el
      dataset: ¿se trata como riesgo (se excluye por seguridad) o como
      "no verificado" (se incluye con advertencia visible)? `TECHNICAL_SPEC.md`
      §5.2 y §8 dejan esto abierto a esta fase — debe quedar resuelto y
      justificado con un comentario, no implícito.
- [ ] Implementar `is_offer_valid()` según la firma de `TECHNICAL_SPEC.md` §5.1.
- [ ] Tests obligatorios (no opcionales):
  - Oferta con escala en `ATL` y `avoid_countries={"US"}` → inválida.
  - Oferta con escala en un aeropuerto explícitamente en `avoid_airports` (aunque
    su país no esté en `avoid_countries`) → inválida.
  - Oferta sin ninguna escala prohibida → válida.
  - Oferta con más escalas que `max_stops` → inválida, incluso si ninguna escala
    está en la lista prohibida.
  - Oferta con escala en un aeropuerto ausente del dataset → se comporta según
    lo decidido y documentado en el punto anterior (test que lo confirme).

**Criterio de hecho:** la suite de tests de `filters.py` pasa en verde y cubre
explícitamente el caso "escala en Atlanta se descarta", que es el requerimiento
original que motivó todo el proyecto.

---

## Fase 3 — Configuración

**Objetivo:** poder leer y validar `config.yaml` según el schema de
`TECHNICAL_SPEC.md` §3, con errores claros ante configuración inválida.

- [ ] Implementar `config.py` con modelos `pydantic` (o validación equivalente).
- [ ] Implementar todas las reglas de validación de §3.1 del `TECHNICAL_SPEC.md`.
- [ ] Crear `config.example.yaml` con el ejemplo del propio usuario (BOG→MAD,
      evitando US/ATL, estadía 10-15 días) como plantilla de referencia.
- [ ] Tests: config válida carga correctamente; cada regla de validación tiene
      al menos un test que confirma que se rechaza con mensaje claro cuando se
      viola (fecha en el pasado, min_days > max_days, país ISO mal formado,
      ambos/ningún campo de fecha de salida presente, etc.).

**Criterio de hecho:** correr el script con un YAML inválido a propósito produce
un mensaje de error humano y específico, no un traceback de Python crudo.

---

## Fase 4 — Generación de combinaciones de fecha

**Objetivo:** a partir de `departure` + `stay`, generar la lista de pares
(fecha_ida, fecha_vuelta) a consultar contra la API.

- [ ] Implementar `dates.py`: función pura, sin I/O, testeable con datos fijos.
- [ ] Definir y documentar cómo se interpreta `departure.before` (¿se prueban
      todas las fechas posibles hasta ese límite, o solo esa fecha límite como
      única fecha de salida? Esto afecta directamente cuántas llamadas de API se
      hacen — debe quedar explícito, ya que impacta costo y tiempo de respuesta,
      RNF-04 del PRD).
- [ ] Tests con `fixed_date` y con `before`, verificando el número exacto de
      combinaciones generadas para un rango de `stay` dado.

**Criterio de hecho:** dado el ejemplo del PRD (`before: 2026-09-28`,
`min_days: 10`, `max_days: 15`), la función devuelve una lista de combinaciones
concreta y verificable a mano.

---

## Fase 5 — Cliente de Duffel

**Objetivo:** integrar el módulo que sí habla con la red, aislado del resto.

- [ ] Implementar `duffel_client.py` según `TECHNICAL_SPEC.md` §6.
- [ ] Implementar manejo de errores: autenticación, rate limit con backoff
      acotado, timeout, sin resultados.
- [ ] Prueba manual (no automatizada, porque implica red real): correr una
      búsqueda real BOG→MAD con el token de test y confirmar que se reciben
      ofertas y que `models.py` las normaliza sin errores.
- [ ] Si se desea test automatizado de este módulo, usar mocks de la librería
      HTTP — no golpear la API real en la suite de `pytest` estándar.

**Criterio de hecho:** una búsqueda real contra la API de test de Duffel
devuelve ofertas normalizadas correctamente, y un error simulado (token
inválido) produce el mensaje esperado sin crashear.

---

## Fase 6 — Orden y presentación

**Objetivo:** conectar filtrado + orden + salida en terminal legible.

- [ ] Implementar `sorter.py` (precio ascendente, desempate por duración según
      config).
- [ ] Implementar `presenter.py` con la salida de terminal descrita en
      `TECHNICAL_SPEC.md` §7.1, incluyendo el resumen de filtros aplicados y el
      mensaje explicativo cuando no hay resultados.
- [ ] Implementar exportación opcional a CSV/HTML (`TECHNICAL_SPEC.md` §7.2).

**Criterio de hecho:** correr el script end-to-end con el `config.example.yaml`
produce en terminal una tabla legible de vuelos, con el resumen de filtros al
inicio, y (si se activa `output.export`) un archivo adicional generado
correctamente.

---

## Fase 7 — Integración final (`cli.py`) y pulido

**Objetivo:** orquestar todo el flujo desde un único entrypoint ejecutable.

- [ ] Implementar `cli.py`: carga config → genera combinaciones de fecha →
      consulta Duffel para cada combinación → normaliza → filtra → ordena →
      presenta.
- [ ] Manejo de interrupciones (Ctrl+C) limpio, sin traceback feo.
- [ ] Flag de línea de comandos para apuntar a un archivo de config distinto al
      default (`--config otra_busqueda.yaml`), para poder tener varias
      búsquedas guardadas sin pisarlas entre sí.
- [ ] README final: cómo instalar, cómo configurar `.env`, cómo editar
      `config.yaml`, cómo correr el script, qué significa cada filtro, y la
      limitación honesta de cobertura de inventario mencionada en
      `ARCHITECTURE.md` §4.2.

**Criterio de hecho:** el usuario puede clonar el repo, copiar
`config.example.yaml` a `config.yaml`, editarlo con su propia ruta, poner su
token en `.env`, correr un solo comando, y obtener una lista de vuelos
ordenada por precio que nunca incluye una escala en un país o aeropuerto de su
lista de exclusión.

---

## Orden de verificación recomendado entre fases

No avanzar a la fase siguiente si la anterior no cumple su criterio de hecho.
En particular, **no saltarse la Fase 2** (motor de filtrado) ni reducir su
cobertura de tests: es la razón de ser de todo el proyecto, según se documenta
en `PRD.md` §2.3 y `TECHNICAL_SPEC.md` §9.1.

---

## Fase 8 — LIVE search-only: informe previo (sin código) [COMPLETADA 2026-09-21 — histórica, era Duffel]

> Estado 2026-09-21: requerimientos aprobados y documentados (`PRD.md` §11,
> `ARCHITECTURE.md` §9-§12, `TECHNICAL_SPEC.md` §11-§15). **No implementar
> nada todavía.** Esta fase termina con un informe, no con código.

**Objetivo:** responder con evidencia "¿Puedo ejecutar búsquedas LIVE reales
sin comprar ni pagar vuelos?" antes de tocar credenciales o código.

- [ ] PASO 1 — Inspección: leer memoria según `PROTOCOLO_INICIO.md`; usar
      `graphify` (`query`/`explain`/`path`) para relaciones entre módulos;
      revisar estado real del repo sin asumir que el resumen coincide con el
      código.
- [ ] PASO 2 — Documentación externa: consultar docs oficiales vigentes de
      Duffel (Test Mode, Offer Requests, Offers, Airlines, Getting Started /
      Go Live, Pricing, rate limits). No usar información antigua si hay más
      reciente. Determinar: requisitos de activación LIVE (tarjeta, saldo /
      top-up, datos empresariales, mínimos); coste de buscar vs reservar vs
      fees; si live search es posible sin saldo para reserva.
- [ ] PASO 3 — Informe (entregable de la fase, antes de editar código):

```text
Current architecture
Current problems
Duffel LIVE requirements
What can be done for free
What could potentially cost money
Proposed changes
Files affected
Tests affected
Risk analysis
```

**Criterio de hecho:** el informe responde la pregunta económica con citas de
docs vigentes, y dice explícitamente GO (live sin compra ni fondos) o STOP
(requisito con coste → detenerse antes de modificar credenciales o lanzar
requests facturables). Sin GO no existe Fase 9.

---

## Fase 9 — LIVE search-only: implementación mínima + tests [COMPLETADA 2026-09-21 — histórica, era Duffel (99/99 tests)]

> Precondición: GO explícito de la Fase 8. Prioridad de implementación
> (en este orden): 1) separación TEST/LIVE, 2) `live_mode`, 3) modelos
> Offer/Segment enriquecidos, 4) aerolínea/owner, 5) baggage, 6) `expires_at`,
> 7) presentación live/test, 8) search-only safety, 9) rate limiting,
> 10) tests, 11) documentación.

- [ ] PASO 4 — Implementación (cambios mínimos, ficheros previstos):
      `config.py` (`mode`, `max_combinations`), `models.py` (contrato
      `TECHNICAL_SPEC.md` §13), `duffel_client.py` (solo lectura/búsqueda +
      §12.4, sin métodos de booking), `presenter.py` (banners y ficha §14),
      `cli.py` (estimación previa + declaración runtime), fixtures de test
      con `live_mode=true/false`, carriers, baggage, `expires_at`.
- [ ] Tests nuevos según matriz `TECHNICAL_SPEC.md` §15.2 (sin credenciales
      reales): `live_mode` true/false/ausente, owner/marketing/operating,
      `ZZ`→TEST, baggage, `expires_at`/flight number, outbound+inbound,
      filtros US/aeropuerto, banners, no-booking, carriers malformados,
      mapping faltante (REJECT), 429/rate limiting, resultados vacíos.
- [ ] Conservar los 59 tests existentes intactos (prohibido eliminarlos).

**Criterio de hecho (PASO 5 — validación TEST):** suite completa en verde:

```text
all existing tests pass + new tests pass
```

sin red ni credenciales reales.

---

## Fase 10 — Validación LIVE mínima y primera búsqueda real [COMPLETADA 2026-09-21 — replanificada a validación TEST por billing on file; ver INFORME_FASE_8 §11-§12]

> Precondición: Fase 9 en verde + GO económico de Fase 8 vigente (sin cambios
> en requisitos de Duffel desde el informe).

- [ ] PASO 6 — Validación LIVE mínima (1 sola combinación razonable, nunca el
      batch completo): comprobar API live responde, devuelve ofertas,
      `live_mode == true` (request y offers), aerolíneas con nombres reales,
      precios coherentes, itinerarios con outbound+inbound, filtro `US`
      elimina rutas estadounidenses, **ninguna operación de booking**.
- [ ] PASO 7 — Primera búsqueda real pequeña (una vez verificado lo anterior):
      BOG→MAD, economy, 1 pasajero, estadía 10–15 días, `before 2026-09-28`,
      avoid US + ATL, con el menor número razonable de combinaciones.
      Presentar por oferta: PRICE, CURRENCY, AIRLINE, MARKETING/OPERATING
      CARRIER, OUTBOUND, RETURN, STOPS, DURATION, BAGGAGE, EXPIRATION,
      LIVE/TEST; y al final `VALID OFFERS / FILTERED BY US / FILTERED BY
      AIRPORT / FILTERED BY MAX STOPS`.
- [ ] Comparación cruzada manual con Google Flights (detectar diferencias de
      cobertura/precio, sin automatizar ni scrapear) y lenguaje
      `Cheapest valid offer returned by Duffel`.

**Criterio de hecho (éxito de la fase, `PRD.md` §11.10):**
`flight-finder --config config.yaml` devuelve ofertas Duffel LIVE con
`live_mode=true`, ida+vuelta completas, US excluido (+ATL excluible),
ordenadas por precio, sin compras, sin booking implementado, secretos fuera
del repo, tests en verde y docs con las limitaciones honestas.

**NO hacer en Fases 8-10:** migrar arquitectura, cambiar Python/uv, frontend,
base de datos, scraping, reservas, pagos, multi-passenger, multi-city,
eliminar tests, hardcodear fechas/países/aerolíneas, secretos en código,
cientos de requests LIVE, presentar TEST como real.

---

## Fase 11 — Migración de proveedor: Duffel → SerpApi/SearchApi (docs + código)

> Precondición cumplida: informe `INFORME_FASE_11.md` con **GO**. API keys ya
> en `.env` del usuario con los nombres **`SERP_API`** (SerpApi) y
> **`SEARCH_API_IO`** (SearchApi) — no pedir acceso al `.env`, no renombrar.

**Objetivo:** reemplazar Duffel por SerpApi/SearchApi (ambos exponen Google
Flights) en specs, código y tests, conservando `dates.py`/`filters.py`/
`sorter.py` intactos.

- [x] PASO 1 — Specs migrados: `README.md`, `docs/TECHNICAL_SPEC.md`,
      `docs/ARCHITECTURE.md`, `config.example.yaml`, `.env.example`
      (`provider: serpapi|searchapi`, `currency`, `search.drill_down`,
      fuera `mode: test|live`, env vars `SERP_API`/`SEARCH_API_IO`).
- [ ] PASO 2 — Código:
  - `config.py`: `provider` (obligatorio, `serpapi|searchapi`), `currency`
    (default USD), `search.drill_down` (`top_n|off`); eliminar `mode`.
  - `flights_client.py` reemplaza `duffel_client.py`: registry `PROVIDERS`
    (base URL, auth `SERP_API`/`SEARCH_API_IO` según provider, mapeo de
    params — `type`/`flight_type`, `stops` numérico vs enum,
    `exclude_conns` vs `excluded_connecting_airports`, hora combinada vs
    `date`+`time`), **GET-only** (sin POST — ver §15.2 del TECHNICAL_SPEC),
    backoff 429/5xx, batch stats, drill-down `departure_token` acotado al
    top N, estimación previa `Search combinations / Maximum API requests /
    Provider`.
  - `models.py`: contrato Google Flights (TECHNICAL_SPEC §4/§13): fuera
    `live_mode`/`owner`/`expires_at`/`BaggageInfo`, dentro `price` +
    `currency` + `provider` + `retrieved_at` + `layovers` + tokens opacos;
    fail-closed sobre `price`/`segments` ausentes.
  - `presenter.py`: banner `SOURCE … SEARCHED AT` + honesty note, columnas
    nuevas (AIRLINE nombre+código, LAYOVERS, CARBON), fuera
    `EXPIRATION`/`LIVE-TEST`/`ZZ`.
  - `cli.py`: wiring con provider + estimación; `scripts/check_duffel.py` →
    `scripts/check_provider.py`.
- [ ] PASO 3 — Tests sin red: fixtures con shapes de **ambos** proveedores
      (INFORME_FASE_11 §2-§3), normalización de las 2 variantes de hora y
      `price_insights`, mapeo de params, auth por provider (key faltante →
      error limpio), guard GET-only (sin `post_data`/`httpx.post`), filtros
      (ATL/MEX/REJECT) y dates/sorter intactos, drill-down acotado,
      429/backoff, vacíos. Matriz completa: `TECHNICAL_SPEC.md` §15.2.

**Regla de cuota (obligatoria, del usuario 2026-09-21):** antes de
CUALQUIER request real (Fase 12 y siempre), **revisar el código y los params
primero (dry-run)** — la cuota gratuita es limitada (SerpApi 250/mes,
SearchApi 100) y no se gasta en debugging.

**Criterio de hecho:** suite completa en verde sin red ni credenciales; el
CLI imprime la estimación de requests ANTES del primer request; ningún POST
en `flights_client.py`.

---

## Fase 12 — Validación real con ambos proveedores

> Precondición: Fase 11 PASO 3 en verde. Máximo de cuota a gastar en esta
> fase: ~8 requests (2 de validación + 6 de búsqueda completa).

- [ ] PASO 1 — **Revisar código/params antes de cada request** (dry-run;
      regla de cuota). Verificar que la estimación impresa es correcta.
- [ ] PASO 2 — Validación mínima: **1 sola combinación por proveedor**
      (2 requests total): verificar `price` semántica round trip
      (INFORME_FASE_11 §6), formato real de `time`/`price_insights`,
      separate tickets en SerpApi, comparación manual contra
      google.com/travel/flights (diferencias esperadas: cache/UI).
- [ ] PASO 3 — Solo si PASO 2 OK: búsqueda de 6 combinaciones con el
      `provider` elegido (BOG→MAD, economy, 1 pasajero, avoid US+ATL),
      drill-down `top_n`: verificar filtros, banner, cards, CSV/HTML.
- [ ] PASO 4 — Revisar cuota consumida en dashboards de SerpApi/SearchApi.

**Criterio de hecho:** `flight-finder --config config.yaml` devuelve
itinerarios reales de Google Flights ordenados por precio, US/ATL excluidos,
banner con honesty note, drill-down expandiendo el top N, sin POST ni
booking, secretos fuera del repo, tests en verde y docs con las limitaciones
honestas.

**NO hacer:** reservas/bookings, gastar cuota en debugging (usar fixtures),
añadir POST al cliente, reintroducir Duffel, ejecutar el CLI repetidamente
"para probar".

---

## Fase 13 — Interfaz web local + links (stdlib, sin dependencias)

> Precondición: Fase 12 en verde. Costo de desarrollo: 0 requests (todo con
> fakes/fixtures; la verificación con red la hace el usuario con sus clicks).

- [ ] 13.0 — Links: `presenter.google_flights_url()` puro (deep link a la
      búsqueda, no al vuelo/precio) + línea `LINK:` en cards con etiqueta
      honesta; wiring CLI vía `combo_of`.
- [ ] 13.1 — `search.py`: `plan_combinations` + `estimate_requests` +
      `run_search` compartidos (CLI pasa a wrapper delgado, salida idéntica).
- [ ] 13.2 — `web.py` stdlib (`http.server` en 127.0.0.1): `GET /` form,
      `POST /search` estimación (0 requests), `POST /run` con token de un
      solo uso + `303` a `/result` (PRG), `GET /csv`; store acotado
      (32 tokens, TTL 15 min); tope UI `top_n ≤ 50`, `max_combinations ≤ 31`.
- [ ] 13.3 — Tests sin red: builder/cards, GET+estimación con 0 calls,
      flujo PRG completo con FakeClient, doble-POST sin re-ejecución,
      TTL/evicción, escapes, body gigante.
- [ ] 13.4 — Docs (README, ARCHITECTURE §7, TECHNICAL_SPEC §2) + memoria.
- [ ] 13.5 — Corrida asíncrona (thread + redirect inmediato, página de
      progreso con `stats` vía `on_progress`, botón Cancelar con
      `should_cancel` parcial) + preset óptimo 6 combos + top 3
      (`config.example.yaml`, tope web 50/31).

**Criterio de hecho:** `uv run flight-finder-web` sirve el form; la
estimación precede a cada corrida confirmada; doble click/refresh nunca
repite requests; suite verde; sin dependencias nuevas.

**NO hacer:** exponer fuera de localhost, persistir estado en disco,
mostrar keys en el HTML, añadir frameworks web.
