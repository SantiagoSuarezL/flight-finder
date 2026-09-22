# TECHNICAL SPEC — Buscador de Vuelos con Filtro de Escalas Restringidas

**Relacionado:** `PRD.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`

Este documento es la referencia técnica que Claude Code / opencode debe seguir al
implementar el script. Incluye estructura de carpetas, contratos de datos,
schema de configuración, firmas de funciones clave y manejo de errores.
Incluye también, en la sección 9, los principios de ingeniería a seguir — no se
separan en un documento aparte por ser un proyecto de un solo script.

---

## 1. Stack técnico

- **Lenguaje:** Python 3.11+
- **Gestión de dependencias:** `pyproject.toml` + entorno virtual (venv o uv)
- **Cliente HTTP:** `httpx` directo contra las APIs de SerpApi
  (`https://serpapi.com/search`) y SearchApi
  (`https://www.searchapi.io/api/v1/search`) — ambas REST GET simples con
  `api_key`, sin SDK oficial. Comparativa y decisión: `INFORME_FASE_11.md`
  (Fase 11). La evaluación original del SDK `duffel-api` (Fase 0) quedó
  obsoleta con la migración desde Duffel (INFORME_FASE_8 §11: LIVE exigía
  tarjeta on file; TEST solo devolvía sandbox `ZZ`).
- **Configuración:** YAML (`PyYAML`), validado con `pydantic` (recomendado, para
  obtener validación de tipos y mensajes de error claros sin escribir
  validación manual)
- **Variables sensibles:** `.env` + `python-dotenv`, nunca en el YAML de
  configuración de búsqueda
- **CLI:** `argparse` es suficiente (no se requiere `click`/`typer` para el
  alcance actual, pero se puede usar si simplifica el manejo de flags)
- **Salida en terminal:** `rich` (recomendado) para tablas legibles y resaltado;
  alternativa aceptable: formateo manual con `tabulate` si se prefiere una
  dependencia más liviana
- **Testing:** `pytest`

---

## 2. Estructura de carpetas propuesta

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
│       ├── flights_client.py      # único punto de contacto con SerpApi/SearchApi (Google Flights)
│       ├── filters.py             # motor de filtrado de escalas prohibidas
│       ├── models.py              # dataclasses/pydantic models internos (Offer, Segment, Slice)
│       ├── sorter.py              # ordenamiento de resultados
│       ├── search.py              # núcleo compartido CLI/web: plan + estimación + run_search (Fase 13)
│       ├── web.py                 # UI web local stdlib (form, estimación+confirm, run idempotente, CSV; Fase 13)
│       └── presenter.py           # formateo de salida en terminal + export (+ google_flights_url, Fase 13)
├── data/
│   └── country_airports.json      # mapeo IATA -> país ISO (dataset versionado)
└── tests/
    ├── test_filters.py
    ├── test_dates.py
    ├── test_config.py
    └── fixtures/
        └── sample_offers.json     # respuestas de ejemplo de Google Flights (SerpApi y SearchApi) para tests sin red
```

---

## 3. Schema de configuración (`config.yaml`)

Este es el archivo que el usuario edita a mano en cada búsqueda. Debe validarse
estrictamente al cargar (fallar rápido con mensaje claro si algo está mal).

```yaml
provider: serpapi             # serpapi | searchapi — obligatorio, dos valores exactos
currency: USD                 # ISO 4217, 3 letras; default USD
search:
  origin: BOG                # código IATA, 3 letras, obligatorio
  destination: MAD           # código IATA, 3 letras, obligatorio
  passengers: 1              # fijo en 1 para v1, pero se declara explícito
  cabin_class: economy       # fijo en economy para v1
  max_combinations: 6        # límite de combinaciones a consultar (secuencial)
  drill_down: top_n          # top_n | off — expandir vuelta vía departure_token para el top N

departure:
  # Una de las dos formas siguientes, no ambas:
  fixed_date: null           # "2026-09-28" si la fecha de salida es exacta
  before: "2026-09-28"       # o bien: cualquier fecha de salida antes de esta

stay:
  min_days: 10
  max_days: 15

avoid:
  countries:                 # códigos ISO 3166-1 alpha-2
    - US
  airports:                  # códigos IATA específicos, independientes del país
    - ATL

max_stops: 2                 # máximo de escalas permitidas por tramo (ida y vuelta)

sort:
  primary: total_price       # total_price | duration
  secondary: duration        # opcional, desempate

output:
  top_n: 10                  # cuántos resultados mostrar
  export: null                # null | "csv" | "html" — si se define, además exporta a archivo
```

### 3.1 Reglas de validación obligatorias
- `provider`: exactamente `serpapi` o `searchapi` (cualquier otro valor →
  error claro antes de cualquier llamada de red).
- `currency`: ISO 4217 de 3 letras mayúsculas; si falta → default `USD`
  documentado, nunca inventar otra moneda.
- `origin`/`destination`: exactamente 3 letras mayúsculas, no pueden ser iguales.
- `departure.fixed_date` y `departure.before` son mutuamente excluyentes: exactamente
  uno debe estar presente (fallar si ambos o ninguno).
- `stay.min_days <= stay.max_days`, ambos > 0.
- `avoid.countries` en formato ISO 3166-1 alpha-2 (2 letras mayúsculas); si el
  usuario pone un código inválido, fallar con mensaje explicando el formato
  esperado, no ignorarlo silenciosamente.
- `max_stops >= 0`.
- `search.max_combinations >= 1`; si las combinaciones generadas por
  `departure`+`stay` lo exceden, se consultan solo las primeras N (orden
  cronológico determinista) y se informa al usuario cuántas quedaron fuera.
- `search.drill_down`: exactamente `top_n` o `off`.
- Fechas no pueden ser en el pasado respecto a la fecha de ejecución.

### 3.2 Nota sobre "países que piden visa"
El proyecto **no** incluye ni mantiene una base de datos de política de visados
por pasaporte (eso cambia con el tiempo y no es responsabilidad de este script).
El usuario decide qué países poner en `avoid.countries` según su propio criterio
o consulta externa (ej. sitios de política de visados). El script solo garantiza
que, una vez definida esa lista, ningún resultado la viole.

---

## 4. Contrato de datos: modelos internos

Independientemente de la forma exacta de la respuesta del proveedor (SerpApi y
SearchApi difieren en detalles como el formato de hora del segmento — ver
`INFORME_FASE_11.md` §4), el proyecto normaliza cada itinerario a un modelo
interno propio, para que el resto del sistema (filtro, orden, presentación) no
dependa directamente del schema externo.

```python
# models.py (forma conceptual, no código final)

class Segment:
    origin: str          # IATA
    destination: str     # IATA
    departure_time: datetime
    arrival_time: datetime
    airline: str         # nombre, ej. "Iberia" (Google Flights envía nombre, no código)
    airline_code: str | None  # derivado del prefijo de flight_number o del logo URL, ej. "IB"
    flight_number: str   # ej. "IB 212"
    duration_minutes: int | None
    airplane: str | None

class Layover:
    id: str              # IATA del aeropuerto de conexión
    name: str | None
    duration_minutes: int | None
    overnight: bool

class Slice:
    segments: list[Segment]
    duration_minutes: int
    layovers: list[Layover]    # alimenta directamente el filtro de países

    @property
    def stopover_airports(self) -> list[str]:
        """Aeropuertos de escala: destino de cada segmento excepto el último."""

class Offer:
    id: str              # sintético: provider + índice/timestamp (Google no expone id)
    price: Decimal       # precio total del round trip listado
    currency: str        # de config `currency`
    provider: str        # serpapi | searchapi
    retrieved_at: datetime
    outbound: Slice
    inbound: Slice | None  # completa tras drill-down (departure_token); None = vuelta implícita
    total_duration_minutes: int
    carbon_emissions_kg: int | None
    baggage_note: str | None   # string textual de `extensions`; sin estructura
    departure_token: str | None  # opaco, solo drill-down inmediato (Fase 11 §6 informe)
    booking_token: str | None    # opaco, nunca usado para booking
```

Esta capa de normalización es la que se testea contra los fixtures de ejemplo
(`tests/fixtures/sample_offers.json`, con shapes de **ambos** proveedores —
hora combinada de SerpApi vs `date`+`time` separados de SearchApi), sin
depender de la disponibilidad de la API real para correr la suite de tests.

**Fail-closed de la normalización (reemplaza a la Regla de Oro 9.1 de
`live_mode`):** oferta sin `price`, sin `currency` o sin `segments` en el
outbound → `ValueError` (esa oferta se descarta con error explícito, nunca se
presenta incompleta). Todo `Offer` siempre lleva `provider` + `retrieved_at`.

---

## 5. Motor de filtrado (`filters.py`) — el componente más crítico

### 5.1 Firma esperada

```python
def is_offer_valid(
    offer: Offer,
    avoid_countries: set[str],
    avoid_airports: set[str],
    max_stops: int,
    airport_country_map: dict[str, str],
) -> tuple[bool, str | None]:
    """
    Devuelve (True, None) si la oferta cumple todas las restricciones.
    Devuelve (False, motivo) si no, donde `motivo` es human-readable,
    ej. "Escala en ATL (Estados Unidos, país excluido)".
    """
```

### 5.2 Reglas de decisión (en orden)
1. Si `len(outbound.segments) - 1 > max_stops` o lo mismo para `inbound` →
   inválida por exceso de escalas.
2. Para cada aeropuerto en `outbound.stopover_airports + inbound.stopover_airports`:
   - Si el aeropuerto está en `avoid_airports` → inválida.
   - Si `airport_country_map[aeropuerto]` está en `avoid_countries` → inválida.
   - Si el aeropuerto no existe en `airport_country_map` → **FAIL-CLOSED:
     se rechaza la oferta** (decisión tomada en Fase 2 e inamovible; ver
     `PRD.md` §11.5). `TECHNICAL_SPEC.md` §8 queda subordinado a esta
     decisión: ante falta de datos nunca se acepta ni se muestra sin
     advertencia; se rechaza y se loggea el motivo.
3. Si ninguna regla anterior descarta la oferta → válida.

### 5.3 Requisito de testing no negociable
Debe existir al menos un test que verifique explícitamente: dado un `Offer` de
ejemplo con escala en `ATL`, y `avoid_countries = {"US"}`, el resultado de
`is_offer_valid` es `False`. Este test es la garantía automatizada de RF-11 del
PRD ("nunca mostrar un itinerario con escala prohibida").

---

## 6. Cliente de API (`flights_client.py`)

### 6.1 Responsabilidades
- Autenticación: `api_key` desde `.env` — `SERP_API` (SerpApi) o
  `SEARCH_API_IO` (SearchApi) según `provider`; nunca hardcodeado.
- Construcción del request GET de búsqueda por proveedor (registry
  `PROVIDERS`: base URL, estilo de auth, mapeo de nombres de params —
  `type`/`flight_type`, `stops` numérico vs enum, etc., ver
  `INFORME_FASE_11.md` §4-§5).
- **GET-only:** este módulo nunca hace POST (el `booking_request` de Google
  Flights no se implementa — barrera SEARCH-ONLY, §12).
- Manejo de errores HTTP: distinguir claramente entre:
  - Error de autenticación (token inválido/expirado) → mensaje claro, detener
    ejecución.
  - Rate limit (429) → backoff y reintento limitado (máx. 3 intentos), luego
    fallar con mensaje claro.
  - Sin resultados para una combinación de fechas → no es un error, es un
    resultado vacío legítimo, se continúa con la siguiente combinación de
    fechas si aplica.
  - Error de red/timeout → reintento limitado, luego fallar esa combinación de
    fechas puntual sin abortar toda la búsqueda si hay más combinaciones en
    curso.
- Este módulo es el **único** que importa `httpx`. Nada
  más en el proyecto debe hacer llamadas HTTP directas.
- **Cuota gratuita:** cada request real consume cuota limitada (SerpApi Free
  250/mes, SearchApi 100 requests; fallidas no cobran). Antes de cualquier
  request real se revisa el código/params (dry-run) — nunca gastar cuota en
  debugging.

### 6.2 Sobre múltiples combinaciones de fecha
Como `stay.min_days`/`max_days` puede generar varias combinaciones de
(fecha_ida, fecha_vuelta) a consultar, y cada una es una llamada de API
independiente (o potencialmente varias si se resuelve `departure.before` como
ventana de fechas de salida también), el cliente debe:
- Exponer una función que reciba una lista de combinaciones y devuelva los
  resultados combinados, manejando fallos parciales sin abortar todo el batch.
- Registrar (log, no print directo) cuántas combinaciones se consultaron, cuántas
  tuvieron resultados, y cuántas fallaron, para que el usuario entienda qué pasó.

---

## 7. Presentación de resultados (`presenter.py`)

### 7.1 Salida en terminal (obligatoria)
Para cada oferta válida mostrada (top N según config):
- Precio total y moneda, destacado.
- Fechas y horas de salida/llegada de ida y vuelta.
- Aerolínea(s) operadoras.
- Aeropuertos de escala (si los hay) — mostrar explícitamente que fueron
  verificados contra la lista de exclusión, no solo omitirlos.
- Número de escalas y duración total.
- Al inicio de la salida: un resumen de los filtros aplicados (ruta, fechas,
  países/aeropuertos excluidos, max_stops), para que quede claro qué se buscó.
- Si no hay resultados válidos: mensaje explícito indicando cuántas ofertas se
  encontraron en bruto y cuántas se descartaron por qué motivo (agregado, ej.
  "8 ofertas encontradas, todas descartadas: 6 por escala en EE. UU., 2 por
  exceder máximo de escalas"), para que el usuario sepa qué relajar.

### 7.2 Exportación opcional
Si `output.export` está definido (`csv` o `html`), generar un archivo adicional
con la misma información, además de la salida en terminal (no en vez de). El
HTML puede ser una tabla estática simple, sin JavaScript ni interactividad — no
es un dashboard, es un registro legible y compartible.

---

## 8. Manejo de datos faltantes o inciertos

El dataset `data/country_airports.json` es mantenido a mano (o generado una vez
desde una fuente pública confiable y congelado). Es razonable que no cubra
absolutamente todos los aeropuertos del mundo. El comportamiento ante un
aeropuerto de escala que no está en el mapeo debe decidirse explícitamente en
implementación (ver `IMPLEMENTATION_PLAN.md`), pero la spec exige como mínimo:
- Nunca fallar silenciosamente (ni ocultar la oferta sin explicar por qué, ni
  mostrarla sin advertir que no se pudo verificar su país).
- Dejar constancia en la salida de terminal de cualquier oferta con un
  aeropuerto de escala "no verificado" por falta de datos, en vez de mezclarla
  sin distinción con las verificadas como seguras.

---

## 9. Principios de ingeniería para este proyecto

Dado que es un proyecto de un solo script para un solo usuario, estos principios
priorizan claridad y bajo mantenimiento sobre escalabilidad o generalidad:

1. **El filtro de escalas es sagrado.** Es la razón de ser del proyecto (ver
   PRD §2.3). Cualquier cambio a `filters.py` debe ir acompañado de un test que
   lo cubra. No se optimiza velocidad a costa de arriesgar un falso negativo ahí.
2. **Una sola fuente de verdad por responsabilidad.** Un solo módulo habla con
   la API externa. Un solo módulo decide qué es válido. Un solo módulo decide
   el formato de salida. Ningún módulo debe mezclar dos de estas
   responsabilidades, aunque sea "más rápido" hacerlo en el momento.
3. **Fallar rápido y explícito en configuración.** Un error de tipeo en
   `config.yaml` debe detener la ejecución con un mensaje claro antes de
   siquiera llamar a la API, no a mitad de un batch de búsquedas.
4. **No silenciar errores de red.** Loggear cada fallo de forma legible; nunca
   tragar una excepción sin dejar rastro visible para el usuario.
5. **Sin dependencias innecesarias.** Si `argparse` alcanza, no se agrega
   `click`. Si formateo manual de tabla es suficiente y `rich` se siente
   pesado, usar algo más liviano — pero mantener la salida legible es
   innegociable.
6. **El código debe poder modificarse sin leer todo el proyecto.** Un usuario
   que quiera cambiar su lista de países prohibidos solo debe tocar
   `config.yaml`. Uno que quiera agregar un nuevo criterio de orden solo debe
   tocar `sorter.py`. Esto es la razón de ser de la separación en módulos de
   la sección 2.
7. **No hardcodear secretos ni asumir claves en el repo.** `.env.example` se
   versiona, `.env` real no. Se documenta esto explícitamente en el README que
   se genere durante la implementación.

---

## 10. Fuera de alcance técnico explícito (para que Claude Code no lo asuma)

- No se implementa caché persistente en disco entre ejecuciones distintas del
  script (más allá de, opcionalmente, un caché en memoria durante una sola
  corrida para no repetir una combinación de fechas idéntica dos veces).
- No se implementa reintento infinito ni cola de trabajo — los reintentos de
  red son acotados (ver §6.1).
- No se construye servidor HTTP, ni modo "watch"/monitoreo continuo.
- No se integra `fast-flights` ni ITA Matrix directamente: la fuente actual ya
  **es** Google Flights vía SerpApi/SearchApi (Fase 11, `INFORME_FASE_11.md`);
  el protobuf `tfs` sigue fuera de alcance (ver `ARCHITECTURE.md` §4.3-§4.4).

---

## 11. Fase LIVE — extensiones de configuración (`config.yaml`)

> **OBSOLETO desde Fase 11** (migración a SerpApi/SearchApi,
> `INFORME_FASE_11.md`): `mode: test|live` ya no existe — Google Flights vía
> SerpApi/SearchApi siempre devuelve datos reales, no hay sandbox que
> clasificar. `max_combinations` sigue vigente y se valida en §3.1. Historia
> Duffel (Fases 8-10): `INFORME_FASE_8.md`. El contenido debajo se conserva
> como registro histórico, no debe guiar implementación nueva.

### 11.1 Campos nuevos

```yaml
mode: live                   # test | live — sin duplicar pipeline [OBSOLETO]
search:
  max_combinations: 6        # límite configurable de combinaciones a consultar
  # ... resto igual que §3 (origin, destination, passengers: 1,
  # cabin_class: economy, departure, stay, avoid, max_stops, sort, output)
```

Caso real de referencia (valores de ejemplo, nunca hardcodeados en código):
`origin: BOG, destination: MAD, departure.before: "2026-09-28",
stay: {min_days: 10, max_days: 15}, avoid.countries: [US],
avoid.airports: [ATL]`.

### 11.2 Reglas de validación nuevas

- `mode` obligatorio, exactamente `test` o `live` (cualquier otro valor →
  error claro antes de cualquier llamada de red).
- `search.max_combinations >= 1`; si las combinaciones generadas por
  `departure`+`stay` lo exceden, se consultan solo las primeras N (orden
  cronológico determinista) y se informa al usuario cuántas quedaron fuera.
- Resto de reglas de §3.1 sin cambios (origen/destino IATA, fechas
  mutuamente excluyentes, `min_days <= max_days`, ISO alpha-2, fechas no
  pasadas).

## 12. Cliente de API — contrato SEARCH-ONLY + control de cuota (`flights_client.py`)

### 12.1 Operaciones permitidas (lista cerrada)

- GET de búsqueda round trip (`engine=google_flights` + `outbound_date` +
  `return_date`).
- GET de drill-down con `departure_token` (expandir vuelta del top N,
  `search.drill_down`).
- Nada más.

### 12.2 Operaciones prohibidas (verificables por test, ver §15)

Queda prohibido implementar o invocar: **cualquier POST** (el flujo de
reserva de Google Flights usa `booking_request{url, post_data}` con POST — no
se implementa), `Orders`/`Payments` de cualquier proveedor, o cualquier
endpoint que genere obligación de pago. `flights_client.py` no contiene
métodos de booking ni siquiera "por si acaso" (barrera arquitectónica,
`ARCHITECTURE.md` §10).

### 12.3 Declaración runtime antes de cada búsqueda real

Antes de ejecutar una búsqueda real (no fixtures), el flujo registra/muestra:

```text
This operation only searches for flights.
No booking/payment operation will be performed.
Provider: <serpapi|searchapi> / Max requests: <n>
```

Sin confirmación interactiva por request; la garantía es estructural (§12.2).

### 12.4 Control de requests (cuota gratuita conservadora)

- Requests secuenciales o con concurrencia estrictamente acotada (defecto:
  secuencial). Paralelización agresiva prohibida.
- Rate limiting + backoff acotado; HTTP 429 → backoff y reintentos limitados
  (máx. 3), luego se marca esa combinación como fallida sin abortar el batch;
  401/403 (auth) → detener con mensaje claro; timeouts → reintento limitado
  por combinación.
- **Revisión previa obligatoria (regla del usuario, 2026-09-21):** antes de
  cada request real, revisar el código y los params primero (dry-run). La
  cuota gratuita es limitada (SerpApi 250/mes, SearchApi 100) — no gastarla
  en debugging; para eso están las fixtures y los mocks.
- Logging por corrida: combinaciones consultadas, con resultados, vacías y
  fallidas; total de requests HTTP realizados.
- Estimación previa obligatoria antes del primer request:

```text
Search combinations: 6
Maximum API requests: 6 (+ drill-down hasta 10)
Provider: serpapi
```

- Los tokens `departure_token`/`booking_token` son opacos y efímeros: se
  conservan solo para el drill-down inmediato de la misma corrida; nunca se
  persisten ni se promete booking con ellos.

## 13. Modelos internos enriquecidos (`models.py`)

> Reescrito en Fase 11. El contrato Duffel (`live_mode`, `owner`,
> `expires_at`, `BaggageInfo`, marketing/operating carrier) se **eliminó** de
> `models.py` con la migración: Google Flights no expone esos campos. La
> Regla de Oro 9.1 (fail-closed sobre `live_mode`) quedó obsoleta y fue
> reemplazada por el fail-closed sobre `price`/`segments` documentado en §4.

Extienden el contrato de §4 (campos previos intactos). Todo campo nuevo es
opcional/nullable: si el proveedor no lo provee, se conserva `None` y la
presentación lo indica (nunca se inventa).

```python
class Layover:                # ya en §4, aquí el detalle enriquecido
    id: str                   # IATA — necesario para el filtro de países
    name: str | None
    duration_minutes: int | None
    overnight: bool

class Segment:                # extiende §4
    origin: str
    destination: str
    departure_time: datetime  # SearchApi: date+time separados; SerpApi: "YYYY-MM-DD HH:MM"
    arrival_time: datetime
    duration_minutes: int | None
    flight_number: str | None
    airline: str | None       # nombre Google Flights, ej. "Iberia"
    airline_code: str | None  # derivado: prefijo de flight_number o filename del logo
    airplane: str | None
    is_overnight: bool | None     # SearchApi lo trae explícito; SerpApi no
    legroom: str | None           # SearchApi: legroom_short de detected_extensions

class Offer:                  # extiende §4
    id: str                   # sintético (provider + índice)
    price: Decimal
    currency: str
    provider: str             # serpapi | searchapi
    retrieved_at: datetime
    outbound: Slice
    inbound: Slice | None     # None hasta drill-down con departure_token
    total_duration_minutes: int
    carbon_emissions_kg: int | None
    baggage_note: str | None  # string textual ("Checked baggage for a fee")
    departure_token: str | None
    booking_token: str | None
```

Reglas:

- **Fail-closed (§4):** sin `price`/`currency`/outbound `segments` →
  `ValueError`. Todo `Offer` lleva `provider` + `retrieved_at`.
- Identificación de aerolíneas: nombre de Google Flights + código derivado
  (`"IB 212"` → `IB`, o filename del `airline_logo` `.../70px/IB.png`).
  Sin código derivable → mostrar solo el nombre, nunca inventar IATA.
- Semántica ida+vuelta: un `Offer` contiene `outbound` + `price` (total del
  round trip listado). `inbound` se completa solo con drill-down
  (`departure_token`, `search.drill_down: top_n`); si es `None`, el presenter
  etiqueta "return not expanded (cheapest return included in price)".
- `price_insights` (lowest_price, price_level, history) es datos de RUTA, no
  de oferta: se modela aparte, opcional, y solo se muestra en el resumen.

## 14. Presentación (`presenter.py`) — banners y ficha por oferta

> Reescrito en Fase 11: se eliminaron los banners TEST/SANDBOX y `ZZ` (no hay
> sandbox en Google Flights) y las columnas `EXPIRATION`/`LIVE-TEST` (no hay
> `expires_at` ni `live_mode`). Historia: `INFORME_FASE_8.md`.

### 14.1 Encabezado de fuente (siempre visible, primera línea del reporte)

```text
SOURCE: SerpApi (Google Flights)
SEARCHED AT: <timestamp>
NOTE: displayed prices from Google Flights - not bookable offers; final price and availability may change at booking
```

(`SOURCE: SearchApi (Google Flights)` cuando `provider: searchapi`.)

### 14.2 Ficha por oferta (campos cuando estén disponibles)

```text
PRICE:     <price> <currency> (round trip total)
AIRLINE:   <name> (<code o "n/a">)
OUTBOUND:  BOG -> XXX -> MAD (fechas/horas, flight numbers)
RETURN:    MAD -> XXX -> BOG | "not expanded (cheapest return included in price)"
STOPS: <n> / LAYOVERS: <ids> / DURATION: <d>
BAGGAGE: <string de extensions o "not confirmed by API">
CARBON: <kg o "n/a"> / AIRPLANE: <model o "n/a">
```

Cierre del reporte con conteos agregados:

```text
VALID OFFERS: <n>
FILTERED BY US: <n>
FILTERED BY AIRPORT: <n>
FILTERED BY MAX STOPS: <n>
```

### 14.3 Restricciones de formato vigentes

- Strings visibles en consola: solo ASCII seguro (`->`, no `→`) — Regla de
  Oro 5.1 vigente.
- Secretos: prohibido incluir tokens en terminal, CSV/HTML, logs o tests
  (ver §15).

## 15. Seguridad de credenciales y matriz de tests (era LIVE, ahora proveedores)

### 15.1 Credenciales

- API keys únicamente en `.env` — **`SERP_API`** (SerpApi) y
  **`SEARCH_API_IO`** (SearchApi). `.env.example` versionado con valor vacío;
  `.env` real en `.gitignore` (sin relajarlo).
- Prohibido: hardcodear, imprimir, loggear, exportar a CSV/HTML, usar en
  tests o versionar. La key de qué proveedor se usa la decide `provider` en
  `config.yaml`, no el nombre de la variable.
- No hay tokens de test/live separados: ambos proveedores son datos reales
  desde el primer request (por eso vale doble la regla de revisar el código
  antes de gastar cuota).

### 15.2 Tests nuevos (sin credenciales reales; conservar los existentes)

| Área | Casos mínimos |
|------|----------------|
| Normalización | fixtures de **ambos** proveedores: hora combinada SerpApi `"2026-03-03 10:10"` vs SearchApi `date`+`time` separados; `price_insights` array (SerpApi) vs objetos (SearchApi); campos ausentes → `None` sin crashear |
| Fail-closed | oferta sin `price`/`currency`/outbound segments → `ValueError` con mensaje explícito |
| Mapeo params | `type=2` vs `flight_type=one_way`, `stops` numérico vs enum, `exclude_conns` vs `excluded_connecting_airports`, `travel_class`, `currency` |
| Auth | `SERP_API` → query param (SerpApi); `SEARCH_API_IO` → query o Bearer (SearchApi); key faltante → error limpio sin traceback, sin request |
| Ida+vuelta | drill-down: 1 request/combo + N acotados con `departure_token`; `drill_down: off` → `inbound is None` y etiqueta del presenter; estimación impresa antes del primer request |
| Filtros | `avoid.countries=[US]` rechaza `BOG->ATL->MAD` y `MAD->MIA->BOG` en ambos slices; `MEX` no afectado; `avoid.airports=[ATL]` rechaza aunque el país no esté evitado; escala sin entrada en `country_airports.json` → REJECT (fail-closed) |
| Aerolíneas | nombre Google Flights + código derivado de `flight_number` (`"IB 212"`→`IB`) o logo URL; sin código → solo nombre; malformado → `None` sin crashear |
| Presentación | banner `SOURCE ... SEARCHED AT` + honesty note; vuelta no expandida etiquetada; conteos agregados |
| No-booking | el cliente no contiene `post_data`, `requests.post`, `httpx.post`, `orders`, `payments`; ningún módulo fuera de `flights_client.py` hace HTTP |
| Rate limiting | 429 → backoff+reintento acotado; límite `max_combinations` respetado |
| Vacíos | cero ofertas → mensaje explícito con desglose de filtrado, sin traceback |

### 15.3 Orden de validación (recordatorio; el plan vive en `IMPLEMENTATION_PLAN.md` Fases 11-12)

1. Suite completa en verde (existentes + nuevos), sin red ni credenciales.
2. **Revisar código/params (dry-run) antes del primer request real** — regla
   de cuota (§12.4).
3. Validación mínima real: **1 sola combinación por proveedor** (máx 2
   requests): verificar precio RT (INFORME §6), formatos reales de
   `time`/`price_insights`, comparación manual con google.com/travel/flights.
4. Solo entonces, búsqueda pequeña de 6 combinaciones con `provider` elegido.
