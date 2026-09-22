# ARCHITECTURE — Buscador de Vuelos con Filtro de Escalas Restringidas

**Relacionado:** `PRD.md`, `TECHNICAL_SPEC.md`, `IMPLEMENTATION_PLAN.md`

---

## 1. Contexto y pregunta a resolver

El requerimiento original era usar Google Flights o ITA Matrix porque tienen la
mejor cobertura de precios del mercado. Esta sección documenta por qué **no**
usamos ninguno de los dos como fuente de datos, qué alternativas se evaluaron, y
por qué la elegida es la correcta para este proyecto, con evidencia de septiembre
2026.

---

## 2. Cómo funciona realmente Google Flights / ITA Matrix (resumen de investigación)

- Google compró ITA Software en 2010, dueña del motor de búsqueda **QPX** y de su
  interfaz de demostración pública **ITA Matrix**.
- Google ofreció una API pública simplificada (**QPX Express**), pero la
  **descontinuó en abril de 2018** por bajo uso. Desde entonces no existe una API
  REST oficial y documentada para desarrolladores externos.
- Hoy, Google Flights (el sitio web) funciona llamando a un **RPC interno**, no a
  una API pública: el navegador envía un parámetro (`tfs`) que es un mensaje
  **Protobuf codificado en Base64**. La comunidad open-source lo reversó
  manualmente (proyecto `fast-flights` / `AWeirdDev/flights`), escribiendo un
  encoder/decoder de ese protobuf sin usar scraping de HTML tradicional.
- **ITA Matrix** sigue existiendo como herramienta web gratuita
  (matrix.itasoftware.com) y sí soporta exactamente lo que buscas: "Routing
  Codes" como `-CITIES ATL` (excluir Atlanta como conexión) o `~US` (evitar
  territorio de EE. UU.). Pero:
  - No tiene API pública ni oficial tampoco.
  - No existe hoy una librería Python mantenida y estable que exponga esos
    routing codes programáticamente. Los proyectos que lo intentan (ej.
    `flight-cli` en GitHub) son personales, pequeños, recientes, y dependen de
    ingeniería inversa de un backend no documentado — el mismo riesgo que
    Google Flights, pero sin el respaldo de una comunidad tan grande detrás.
  - No permite reservar, solo consultar.

**Conclusión:** cualquier ruta hacia "Google Flights o ITA Matrix por API" pasa
por ingeniería inversa de tráfico interno de Google, no por un contrato estable.
Es viable técnicamente, pero fresa el sistema en una base frágil desde el primer
día — un cambio interno de Google puede romper el script sin aviso ni changelog.

---

## 3. Alternativas evaluadas como fuente de datos

| Opción | Tipo de acceso | Estado en sept. 2026 | Routing codes / avoid-country nativo | Veredicto |
|---|---|---|---|---|
| **QPX Express (Google)** | API oficial | Descontinuada desde 2018 | N/A | Descartada — no existe |
| **ITA Matrix reversado** | Ingeniería inversa de backend web | Sitio activo, sin API pública | Sí, vía Routing Codes (`-CITIES`, `~`) | Descartada para v1 — sin librería estable, riesgo de romperse sin aviso |
| **Google Flights vía `fast-flights`** | Ingeniería inversa de RPC protobuf | Librería activa y usada, pero no oficial | No — solo filtros básicos (aerolíneas, escalas, horario) | Candidata como fuente secundaria/comparativa, no como base |
| **Kiwi.com Tequila API** | API oficial B2B | **Cerró el registro self-serve en mayo 2024.** Solo invitación a partners desde entonces | Sí, tiene soporte fuerte para excluir aeropuertos (su especialidad es "virtual interlining") | Descartada — inaccesible para un desarrollador individual hoy |
| **Amadeus Self-Service API** | API oficial, antes self-serve | **El portal Self-Service se decomisiona el 17 de julio de 2026.** A la fecha de este documento (sept. 2026) ya no está disponible; solo queda acceso Enterprise vía contrato de ventas | No nativo — se filtraría igual que Duffel, post-procesando la respuesta | Descartada — ya no existe la vía de acceso individual |
| **Duffel API** | API oficial, self-serve instantáneo | **Activa y con registro self-serve en minutos**, sin necesidad de acreditación de agencia de viajes | No nativo, pero la respuesta trae el itinerario completo segmento por segmento (aeropuertos de cada escala), suficiente para filtrar nosotros mismos | Elegida en Fase 0; **reemplazada en Fase 11** — LIVE exigía tarjeta on file (`INFORME_FASE_8.md` §11) y TEST solo devolvía sandbox `ZZ` |
| **SerpApi (`google_flights` engine)** | API comercial de scraping de Google Flights, signup self-serve | Activa, plan Free 250 búsquedas/mes sin tarjeta | No nativo — mismos filtros client-side (layovers IATA + `country_airports.json`) | **Elegida (Fase 11)** |
| **SearchApi (`google_flights` engine)** | API comercial de scraping de Google Flights, signup self-serve | Activa, 100 requests gratis sin tarjeta | Idem SerpApi | **Elegida (Fase 11)** |

---

## 4. Decisión de fuente de datos: Duffel (Fase 0) → SerpApi/SearchApi (Fase 11)

> **§4.1-§4.3 son historia de la decisión original (Duffel, 2026-09-21).**
> La vigente es §4.4.

### 4.1 Por qué (Duffel, decisión original)
- Es, a la fecha, la única opción con **signup self-serve real y funcionando**
  para un desarrollador individual (las otras dos opciones serias —Kiwi y
  Amadeus— cerraron esa puerta en 2024 y 2026 respectivamente).
- Devuelve el itinerario completo por `slices` → `segments`, con el código IATA
  de origen y destino de cada tramo. Esto es exactamente el dato que necesitamos
  para hacer el filtro de "no escalas en X" nosotros mismos, sin depender de que
  la API tenga ese filtro nativo.
- Tiene SDK oficial en Python, documentación completa y activa, y modelo de
  precios pay-as-you-go sin mínimos mensuales — razonable para uso personal
  esporádico.
- Cubre más de 300 aerolíneas, incluyendo contenido NDC y de bajo costo,
  agregando contenido de GDS también.

### 4.2 Limitación honesta que hay que documentar
Duffel, igual que cualquier fuente única, **no tiene el 100% del inventario que
Google Flights agrega** (Google agrega literalmente todo lo que puede tocar,
incluyendo scraping/agregación de decenas de fuentes). Es posible que en algunos
casos Google Flights muestre un precio más bajo que no aparece en Duffel. Esto se
documenta en el PRD como riesgo conocido y se acepta como trade-off consciente a
cambio de tener una fuente estable, oficial y con contrato de soporte — en vez de
un script que puede dejar de funcionar de un día para otro.

### 4.3 Rol de `fast-flights` (Google Flights) en el proyecto [histórico]
Se documentó como **fuente secundaria opcional para v2** (comparación
Duffel vs Google). Con la migración de Fase 11 la fuente **ya es** Google
Flights (vía SerpApi/SearchApi), por lo que `fast-flights` directo (protobuf
`tfs`) sigue fuera de alcance — ver §4.4 y `INFORME_FASE_11.md`.

### 4.4 Decisión vigente (Fase 11): SerpApi + SearchApi

**Por qué se cambió (2026-09-21):** Duffel bloqueó los precios reales en dos
pasos verificados: TEST solo devuelve inventario sandbox `ZZ` (precios no
reales, `INFORME_FASE_8.md` §3.2) y LIVE exige **tarjeta on file** en el KYC
del dashboard (addendum §11 del mismo informe, verificado por el usuario).
Sin tarjeta no hay precios reales con Duffel.

**Por qué estos dos:** ambos exponen el inventario de **Google Flights** con
API key web, sin tarjeta ni KYC:
- **SerpApi** — plan Free 250 búsquedas/mes (50/hr), cache 1h gratis.
- **SearchApi** — 100 requests gratis al registrarse, sin tarjeta.

Se eligen **los dos** con abstracción `provider: serpapi|searchapi`: la
respuesta es el mismo scraping de Google Flights con shapes casi idénticos
(una sola capa de normalización sirve para ambos), y tener dos proveedores
mitiga el riesgo de que un cambio de UI de Google rompa a uno solo (fallback
manual cambiando `provider`, sin automático en v1). Comparativa, costos,
semántica round-trip (`departure_token`) y plan de migración completo:
**`INFORME_FASE_11.md`**.

**Consecuencias arquitectónicas:**
- `duffel_client.py` → `flights_client.py` (GET-only, registry `PROVIDERS`).
- `mode: test|live` y `live_mode`/`expires_at`/`owner`/`ZZ` desaparecen —
  siempre hay datos reales; lo que queda es la honestidad "precios display
  de Google Flights, no ofertas reservables".
- Filtro de escalas **sin cambios**: `layovers[].id` (IATA) + 
  `country_airports.json` fail-closed; los filtros server-side
  (`stops`, `exclude_conns`) son solo optimización de cuota.
- `dates.py`, `filters.py`, `sorter.py` intactos — la migración toca la capa
  de red, modelos, presenter y config.

---

## 5. Arquitectura del sistema

### 5.1 Vista general

```
┌───────────────────────┐
│  config.yaml          │  ← el usuario edita esto a mano
│  (rutas, fechas,      │
│   países/aeropuertos  │
│   prohibidos, límites)│
└──────────┬────────────┘
           │
           ▼
┌──────────────────────┐
│  loader de config    │  → valida schema, tipos, fechas
└──────────┬───────────┘
           │
           ▼
┌───────────────────────┐      ┌───────────────────────┐
│  generador de         │      │  data/country_airports│
│  combinaciones de     │      │  .json (mapeo IATA →  │
│  fecha (salida x      │      │  país ISO)            │
│  duración de estadía) │      └──────────┬────────────┘
└──────────┬────────────┘                 │
           │                              │
           ▼                              │ 
┌──────────────────────┐                  │
│  cliente Google      │                  │
│  Flights             │                  │
│  (SerpApi|SearchApi) │                  │
└──────────┬───────────┘                  │
           │  ofertas crudas              │
           ▼                              │
┌───────────────────────┐◄────────────────┘
│  motor de filtrado    │
│  (excluye por país/   │
│   aeropuerto/escalas) │
└──────────┬────────────┘
           │  ofertas válidas
           ▼
┌─────────────────────┐
│  ordenador          │
│  (precio, duración) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  presentador        │  → tabla en terminal
│  (CLI output)       │  → export opcional CSV/HTML
└─────────────────────┘
```

### 5.2 Componentes y responsabilidades

| Componente | Responsabilidad | Por qué está separado |
|---|---|---|
| **Config loader** | Leer y validar `config.yaml`, convertir a objetos tipados | Si el usuario comete un error en el YAML, debe fallar aquí con un mensaje claro, no a mitad de una llamada a la API |
| **Date combinator** | A partir de fecha de salida (o "antes de X") y rango de estadía, generar la lista de pares (fecha_ida, fecha_vuelta) a consultar | Aísla la lógica combinatoria, que es pura y fácil de testear sin red |
| **Flights client** (`flights_client.py`) | Únicopunto de contacto con SerpApi/SearchApi (api_key, GET, mapeo de params por proveedor, manejo de rate limit/cuota/errores HTTP) | Si un proveedor cambia su contrato o se agrega otro, solo se toca este módulo (registry `PROVIDERS`) |
| **Country/airport map** | Dataset estático IATA→país ISO, usado por el filtro | Es un dato, no lógica — vive en su propio archivo versionado, fácil de auditar y corregir |
| **Filter engine** | Dado un `offer` (itinerario Google Flights normalizado) y la config de exclusión, decide si es válido | Lógica de negocio central del proyecto — pura, sin I/O, 100% testeable con datos de ejemplo |
| **Sorter** | Ordena ofertas válidas por precio (y duración como desempate) | Trivial pero separado para mantener cada módulo con una sola responsabilidad |
| **Presenter (CLI)** | Formatea y muestra resultados en terminal; exporta si se pide | Es la única capa que "sabe" de formato visual; todo lo anterior es agnóstico de presentación |

### 5.3 Por qué esta separación importa aquí
El corazón del proyecto —lo que lo diferencia de simplemente usar Google
Flights— es el **filter engine**. Aislarlo como una función pura que recibe una
oferta y una configuración, y devuelve válido/inválido (con motivo), permite:
- Probarlo con casos de ejemplo sin llamar a la API real ni gastar cuota.
- Auditar manualmente que nunca se cuele un falso negativo (un vuelo con escala
  prohibida que se muestre igual), que es el requerimiento no-negociable del
  proyecto (RF-11 en el PRD).

---

## 6. Flujo de datos para el filtro de escalas (el núcleo del proyecto)

1. Google Flights (vía SerpApi/SearchApi) devuelve un itinerario de ida con
   precio total del round trip y `departure_token`; tras drill-down
   (`INFORME_FASE_11.md` §6) se expanden también los segmentos de vuelta.
   El `Offer` interno los acomoda en `outbound`/`inbound` (Slice), cada uno
   con uno o más `segments`.
2. Por cada `segment`, se conoce el aeropuerto de origen y destino (IATA).
3. Los aeropuertos de **escala** de un slice son todos los aeropuertos
   intermedios: es decir, el destino de cada segmento excepto el último, y el
   origen de cada segmento excepto el primero (en un itinerario con N segmentos
   hay N-1 puntos de escala).
4. Para cada aeropuerto de escala, se resuelve su país (ISO) usando el dataset
   `country_airports.json`.
5. Si el aeropuerto está en la lista `avoid.airports` **o** su país está en
   `avoid.countries`, la oferta completa se descarta — sin importar que el resto
   del itinerario sea perfecto o que el precio sea el más bajo.
6. Esto se aplica **a ambos slices** (ida y vuelta) de forma independiente; basta
   con que uno de los dos tramos toque una escala prohibida para descartar la
   oferta completa.

Este flujo se especifica con más detalle y con la firma de funciones concreta en
`TECHNICAL_SPEC.md`.

---

## 7. Decisión de interfaz (resumen — detalle completo en PRD §8)

CLI pura, sin frontend web. Justificación completa en `PRD.md`. Aquí solo se deja
constancia de la consecuencia arquitectónica: **no hay backend/frontend
separados, no hay servidor HTTP, no hay estado persistente entre ejecuciones**.
Cada corrida del script es un proceso independiente que lee config, consulta la
API, filtra, ordena e imprime — sin memoria de corridas anteriores (salvo un
caché opcional de corta duración para no repetir llamadas idénticas a la API
durante desarrollo/debug, ver `TECHNICAL_SPEC.md`).

> **Excepción Fase 13 (UI web local):** `src/flight_finder/web.py` expone el
> mismo pipeline (`search.run_search`, compartido con el CLI) vía
> `http.server` stdlib en `127.0.0.1` — sin dependencias nuevas, sin
> backend/frontend separados. Guarda como máximo 32 tokens/resultados por
> 15 min en memoria (sin estado en disco); las keys siguen solo en el
> proceso servidor. La estimación + confirmación previa preserva la regla
> de cuota (§11).

---

## 8. Decisiones explícitamente pospuestas (no ambigüedad, sino alcance)

Estas preguntas tienen respuesta, pero la respuesta es "no en v1", para que
Claude Code no las resuelva por su cuenta ni las asuma como pendientes:

- **¿Fallback automático entre SerpApi y SearchApi?** No en v1 — el cambio es
  manual vía `provider` en `config.yaml` (ver §4.4 / `INFORME_FASE_11.md`).
- **¿Integrar `fast-flights` (protobuf `tfs`) directamente?** No — la fuente
  ya es Google Flights vía los dos proveedores (§4.4).
- **¿Caché persistente entre ejecuciones?** No en v1. Cada corrida es fresca.
- **¿Notificaciones/monitoreo continuo?** No en v1, es v2 explícito en el PRD.
- **¿Soporte multi-pasajero o multi-clase?** No en v1, alcance fijo a 1 adulto,
  económica.

---

## 9. Fase LIVE: modos TEST/LIVE con un solo pipeline (2026-09-21)

> **OBSOLETO desde Fase 11** (migración a SerpApi/SearchApi,
> `INFORME_FASE_11.md`): ya no existe modo TEST/LIVE ni `live_mode` — Google
> Flights vía SerpApi/SearchApi siempre devuelve datos reales. Se conserva
> esta sección como historia de las decisiones ejecutadas en Fases 9-10
> (banners, fail-closed `live_mode`, estimación previa — varias de esas
> medidas sobreviven adaptadas: estimación, backoff, SEARCH-ONLY).
> Requerimientos originales en `PRD.md` §11; contratos (actualizados) en
> `TECHNICAL_SPEC.md` §11-§15.

### 9.1 Un pipeline, dos fuentes

```text
config.yaml (incluye mode: test | live)
    ↓
config loader (valida mode)
    ↓
date combinator (igual en ambos modos)
    ↓
Duffel client SEARCH-ONLY (offer_requests + offers, nunca orders)
    ↓
models / normalization (conserva live_mode, owner, carriers, baggage, expires_at)
    ↓
filter engine (igual en ambos modos; fail-closed)
    ↓
sorter (igual en ambos modos)
    ↓
presenter (banner TEST o LIVE según live_mode real de la respuesta)
```

La única diferencia entre modos es la credencial/modo de la fuente de datos.
No se duplica lógica de filtrado, orden ni presentación.

### 9.2 Detección del modo efectivo

El modo efectivo **no** se infiere del nombre del token (`duffel_test_*` vs
`live_*`) sino de la respuesta oficial: `offer_request.live_mode` y
`offer.live_mode`. El cliente propaga ese flag hasta `Offer.live_mode` y el
presenter lo usa para elegir el banner (§12). Si alguna respuesta carece del
campo o es inconsistente, se trata como modo desconocido → se presenta con
precaución TEST (fail-closed también en presentación).

### 9.3 Requisito económico (verificación previa obligatoria)

Antes de implementar el modo live o de rotar credenciales, responder con
documentación oficial vigente de Duffel (Test Mode, Offer Requests, Offers,
Airlines, Getting Started / Go Live, Pricing, rate limits):

- Requisitos de activación de LIVE (tarjeta, saldo/top-up, datos
  empresariales, mínimos).
- Coste de **buscar** vs coste de **reservar** vs fees de Duffel.
- Si la búsqueda live es posible sin saldo para reserva.

Si algún requisito implica coste real o riesgo de cargo, detenerse antes de
modificar credenciales o lanzar requests live y reportarlo. Ver
`IMPLEMENTATION_PLAN.md` Fase 8 (paso de informe previo al código).

## 10. Barrera arquitectónica SEARCH-ONLY (anti-booking)

Principio: **el CLI de esta aplicación no puede ejecutar una compra, ni por
accidente ni por extensión futura descuidada.**

Medidas (contratos en `TECHNICAL_SPEC.md` §12):

1. `flights_client.py` expone solo operaciones **GET** de lectura/búsqueda
   (búsqueda round trip + drill-down `departure_token`). **Ningún POST**: el
   flujo de reserva de Google Flights (`booking_request{url, post_data}`) no
   se implementa; no existen métodos de `Orders`/`Payments`/`Bookings` ni
   siquiera "por si acaso".
2. Verificación en runtime antes de cada búsqueda real: el flujo declara
   `This operation only searches for flights. No booking/payment operation
   will be performed. Provider: <p> / Max requests: <n>`. No se pide
   confirmación interactiva por request, pero
   la ausencia de código de compra hace la garantía estructural.
3. Test de no-booking: la suite verifica que el cliente no contiene
   `post_data` ni `httpx.post`/`requests.post` (lista en `TECHNICAL_SPEC.md`
   §15.2) y que ningún otro módulo hace HTTP directo.
4. Regla de revisión: cualquier PR que añada un POST al cliente se rechaza
   por arquitectura, no solo por alcance.

## 11. Control de requests (cuota gratuita conservadora)

Ambos proveedores tienen cuota gratuita limitada (SerpApi Free 250
búsquedas/mes, SearchApi 100 requests). El diseño es:

- Requests **secuenciales o controlados** (sin paralelización agresiva).
- Rate limiting + backoff con manejo explícito de HTTP 429 (reintentos
  acotados), timeouts y fallos parciales por combinación sin abortar el batch.
- Logging de cuántos requests se realizaron / cuántos fallaron / cuántos
  quedaron vacíos por combinación.
- **Revisión previa obligatoria (regla del usuario, 2026-09-21):** antes de
  cada búsqueda real, **revisar el código y los params primero (dry-run)** —
  la cuota gratuita es limitada y no se gasta en debugging; para eso están
  las fixtures y los mocks.
- **Límite configurable de combinaciones** (`search.max_combinations`):
  antes de una búsqueda grande, el CLI imprime la estimación:

```text
Search combinations: 6
Maximum API requests: 6 (+ drill-down hasta 10)
Provider: serpapi
```

- Estrategia de validación: primero **1 sola combinación por proveedor**
  (máx 2 requests; `IMPLEMENTATION_PLAN.md` Fase 12) comprobando precio RT,
  formatos reales, coherencia con google.com/travel/flights y cero operaciones
  de booking. Solo después se amplía a 6.
- Prohibido: ráfagas de requests o ejecutar el CLI repetidamente para
  "probar a ver si funciona" — eso es debugging con cuota real.

## 12. Presentación y semántica ida+vuelta (Fase 11)

- **Fuente:** `SOURCE: SerpApi|SearchApi (Google Flights) / SEARCHED AT:
  <timestamp>` + nota honesta: `displayed prices from Google Flights - not
  bookable offers; final price and availability may change at booking`. No
  hay banners TEST/SANDBOX ni etiquetas `ZZ` (no hay sandbox).
- **Ida y vuelta:** un `Offer` = `outbound Slice` + `price` total del round
  trip (Google lista itinerarios de ida con el precio total RT e
  `departure_token`; la vuelta se expande vía drill-down `search.drill_down:
  top_n`, `INFORME_FASE_11.md` §6). La UI muestra bloques `OUTBOUND (BOG →
  XXX → MAD)` / `RETURN (…)` (o "not expanded") / `PRICE (monto + moneda)`.
- **Datos enriquecidos** (cuando Google los provee): precio + moneda,
  airline nombre+código (derivado de `flight_number`/logo), layovers con IATA
  (alimentan el filtro), duraciones, carbon emissions, airplane, legroom,
  baggage como string textual (`"Checked baggage for a fee"` — sin estructura
  garantizada; si falta: "not confirmed by API"), tokens opacos solo para
  drill-down inmediato.
- **Cobertura honesta:** la fuente es Google Flights, así que el inventario
  sí coincide con lo que Google muestra; lo que **no** se garantiza es la
  reserva (precios display, disponibilidad puede variar). Nunca prometer
  booking desde este CLI (SEARCH-ONLY, §10).
