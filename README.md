# flight-finder

Buscador de vuelos con filtro de escalas restringidas. Fuente de datos:
**Google Flights**, accedida mediante dos proveedores intercambiables:
**SerpApi** y **SearchApi** (comparativa y decisión en
`docs/INFORME_FASE_11.md`).

> Historia: las fases 0-10 usaron Duffel API. El inventario sandbox de TEST y
> el bloqueo de LIVE por "billing on file" (tarjeta obligatoria,
> `docs/INFORME_FASE_8.md` §11) llevaron a migrar a SerpApi/SearchApi en la
> Fase 11. Fase 10b (LIVE Duffel) cancelada.

## Decisión de cliente HTTP

SerpApi y SearchApi no tienen SDK oficial: ambos son REST simple de una sola
llamada GET con `api_key`, así que se usa `httpx` directo. El único punto de
contacto con la red es `src/flight_finder/flights_client.py` (registry
`PROVIDERS` con base URL, auth y mapeo de params por proveedor).

## Instalación (gestor principal: `uv`)

```bash
uv sync --extra dev   # crea/usa .venv, instala el paquete en editable + deps
uv run pytest -q      # correr tests
```

Toda instalación, sincronización y ejecución se hace con `uv`
(`uv add`, `uv sync`, `uv run`); no usar `pip` directo.

## Configuración

1. Copiar `.env.example` a `.env` y completar las API keys:
   - **`SERP_API`** — key de SerpApi (serpapi.com → sign up → dashboard → API
     Key). Plan Free: 250 búsquedas/mes.
   - **`SEARCH_API_IO`** — key de SearchApi (searchapi.io → sign up → dashboard
     → API Key). 100 requests gratis al registrarse, sin tarjeta.
   `.env` nunca se versiona.
2. Copiar `config.example.yaml` a `config.yaml` y editar la búsqueda:
   - `provider`: `serpapi` o `searchapi` — mismos datos (Google Flights),
     distinto proveedor. Sin fallback automático en v1: si uno falla, se
     cambia `provider` a mano.
   - `currency`: moneda de los precios (default `USD`).
   - `search`: origen/destino IATA, 1 pasajero, economy (fijos en v1) +
     `max_combinations` (cuántas combinaciones consultar, secuencial) +
     `drill_down` (`top_n` = expandir la vuelta real de los mejores N vía
     `departure_token`; `off` = solo ida con precio total round trip).
   - `departure`: exactamente una de `fixed_date` (salida exacta) o `before`
     (fecha límite, interpretada como **única fecha de salida**, no como
     ventana — ver `dates.py`).
   - `stay`: rango de días de estadía (cada día suma una combinación
     ida/vuelta = una llamada de API).
   - `avoid.countries` (ISO alpha-2, ej. `US`) y `avoid.airports` (IATA,
     ej. `ATL`): ninguna oferta mostrada tendrá escala en ellos.
   - `max_stops`: máximo de escalas por tramo.
3. Correr: `uv run flight-finder` (o `--config otra_busqueda.yaml` para
   varias búsquedas guardadas).

### Interfaz web local (Fase 13, stdlib, sin dependencias)

```bash
uv run flight-finder-web            # sirve en http://127.0.0.1:8080 (local)
uv run flight-finder-web --port 8090
```

Formulario → **estimación con botón Confirmar** (nada se ejecuta sin tu
click) → página de progreso en vivo con botón Cancelar → resultados con
cards, `LINK:` a la búsqueda en Google Flights y descarga CSV. La
confirmación responde al instante (la búsqueda corre en background);
doble click o recargar no repite la búsqueda (token de un solo uso +
redirect); el servidor guarda como máximo 32 resultados por 15 minutos.
Preset óptimo precargado: 6 combos + drill top 3 = **9 requests** máx
por corrida.

### Cuota gratuita: revisar antes de buscar

Las búsquedas gratuitas son limitadas (SerpApi Free: 250/mes; SearchApi: 100
requests; fallidas no cobran, SerpApi además no cobra repetir una búsqueda
cacheada dentro de 1h). Por eso:

- El CLI siempre imprime la **estimación de requests ANTES** del primero
  (`Search combinations / Maximum API requests / Provider`).
- Toda prueba manual (nuevo proveedor, cambio de params) se valida primero
  **revisando el código/dry-run**, nunca gastando cuota en debugging.

### Solo consulta (SEARCH-ONLY)

El CLI nunca reserva: `flights_client.py` es **GET-only**, sin POST (el
`booking_request` de Google Flights no se implementa; test estructural lo
garantiza). Para reservar, buscá el vuelo manualmente por número de vuelo o
aerolínea.

### Honradez de precios

Los precios son los que **muestra Google Flights** (display): pueden variar al
momento de reservar; no son ofertas reservables con garantía. El listado
round trip muestra el precio total del ida+vuelta con la vuelta implícita más
barata; `drill_down: top_n` expande los segmentos reales de vuelta de los
mejores N resultados.

## Qué significa cada filtro

- **País evitado**: se descarta cualquier oferta con escala en un aeropuerto
  de ese país (según `data/country_airports.json`).
- **Aeropuerto evitado**: se descarta aunque su país no esté en la lista
  (además se envía server-side como `exclude_conns`/
  `excluded_connecting_airports` para ahorrar cuota; el filtro local sigue
  siendo la fuente de verdad fail-closed).
- **Escala no verificada**: si el aeropuerto no está en el dataset, la oferta
  se excluye por seguridad (fail-closed) y se muestra el motivo.
- **max_stops**: descarta tramos con más escalas, aunque no sean prohibidas
  (también se envía server-side como `stops`).

## Dataset de aeropuertos (Fase 2)

`data/country_airports.json` mapea IATA → país ISO 3166-1 alpha-2 (8802
aeropuertos). Generado desde **OurAirports** (dominio público,
`airports.csv`, filtrado a `large/medium/small_airport` con IATA) con:

```bash
uv run python scripts/build_country_airports.py
```

## Limitación honesta de cobertura

La fuente **es** Google Flights (vía SerpApi/SearchApi), así que el inventario
coincide con lo que muestra Google. Quedan dos salvedades documentadas:

1. **Precios display, no ofertas reservables** — disponibilidad y precio
   final pueden cambiar al reservar.
2. **Ambos proveedores scrapan Google Flights** — un cambio de UI de Google
   puede romper la normalización; por eso hay **dos proveedores**
   intercambiables (`provider`) y fixtures que fijan el schema (tests sin red).
