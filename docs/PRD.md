# PRD — Buscador de Vuelos con Filtro de Escalas Restringidas

**Proyecto:** flight-finder (nombre provisional)
**Autor:** (tú) + Claude
**Fecha:** 2026-09-21
**Estado:** Draft para implementación

---

## 1. Resumen ejecutivo

Un script en Python que busca vuelos ida y vuelta al menor precio posible, para 1
pasajero, permitiendo excluir itinerarios que hagan escala en países o aeropuertos
específicos (típicamente Estados Unidos, por restricción de visado del pasajero).

No es una app web, no es un producto para terceros. Es una herramienta personal de
línea de comandos que resuelve un problema muy concreto: los buscadores de vuelos
masivos (Google Flights incluido) no permiten excluir de forma nativa y confiable
"cualquier escala en un país donde necesito visa que no tengo".

---

## 2. Problema

### 2.1 Contexto
El usuario tiene pasaporte colombiano y no posee visa estadounidense. Buscando
vuelos entre Bogotá y destinos como Madrid, la ruta más barata casi siempre implica
una escala en un hub de EE. UU. (Atlanta, Miami, Houston...). Técnicamente, incluso
en tránsito sin salir del aeropuerto, muchas de esas escalas exigen una visa de
tránsito o una ESTA que el usuario no tiene, lo cual invalida el itinerario aunque
el precio sea el más bajo mostrado.

### 2.2 Por qué las herramientas existentes no alcanzan
- **Google Flights**: filtra por número de escalas, aerolínea y duración, pero no
  tiene un filtro nativo "evitar país X" ni "evitar aeropuerto Y en conexión".
- **ITA Matrix** (matrix.itasoftware.com): sí tiene esta funcionalidad exacta vía
  "Routing Codes" (ej. `-CITIES ATL` para excluir Atlanta como conexión), pero:
  - No tiene API pública ni oficial.
  - No existe una librería Python madura y mantenida que exponga esos routing
    codes programáticamente (solo proyectos personales pequeños y frágiles).
  - Habría que hacer ingeniería inversa del tráfico de red del sitio, que se puede
    romper sin aviso.
- **Buscar manualmente aerolínea por aerolínea**: es exactamente lo tedioso que
  el usuario quiere evitar automatizando.

### 2.3 Oportunidad
No hace falta que el motor de búsqueda tenga el filtro "evitar país" de forma
nativa. Si la fuente de datos devuelve el itinerario completo (todas las escalas,
con su código IATA), el filtrado se puede hacer nosotros mismos, en nuestro propio
código, sobre los resultados ya obtenidos. Esto es más simple, más estable, y no
depende de ingeniería inversa de nada.

---

## 3. Objetivo del proyecto

Construir un script en Python que, dado:
- Origen (IATA)
- Destino (IATA)
- Fecha de salida (o rango de fechas antes de una fecha límite)
- Rango de duración de estadía (mín. y máx. noches)
- 1 pasajero adulto
- Una lista configurable de países/aeropuertos prohibidos como escala

Devuelva la lista de itinerarios ida y vuelta ordenados por precio total (y
opcionalmente duración), **excluyendo cualquier itinerario cuya ruta —ida o
vuelta— toque un aeropuerto o país de la lista prohibida**, incluso como simple
tránsito.

---

## 4. Alcance

### 4.1 Dentro de alcance (v1)
- Búsqueda ida y vuelta, 1 pasajero adulto, clase económica.
- Fecha de salida fija o ventana de fechas ("antes de tal fecha").
- Rango de duración de estadía (min/max noches) para explorar varias combinaciones
  de fecha de regreso.
- Filtro configurable de países y aeropuertos prohibidos como escala (no aplica al
  origen/destino final, solo a conexiones intermedias).
- Límite configurable de número máximo de escalas.
- Orden de resultados por precio total, con desempate opcional por duración.
- Salida en terminal, clara y legible, con las mejores N opciones.
- Configuración de origen/destino/fechas/filtros en un archivo YAML editable a
  mano (según lo decidido con el usuario).
- Manejo explícito de errores de API (rate limits, sin resultados, fechas
  inválidas) con mensajes entendibles, no tracebacks crudos.

### 4.2 Fuera de alcance (v1)
- Reserva o compra del vuelto (el script solo busca y muestra precios).
- Multi-pasajero, clases premium/business, multi-tramo (multi-city).
- Interfaz web o app gráfica.
- Notificaciones automáticas o monitoreo de precio en el tiempo (cron / alertas).
  Se deja como posible v2, mencionado en el roadmap.
- Base de datos de historial de búsquedas.
- Soporte multi-idioma / multi-moneda dinámico (se fija USD o la moneda que
  entregue la API por defecto).

### 4.3 Posible v2 (no construir ahora, solo dejar constancia)
- Monitoreo periódico de una ruta con alerta cuando baje de un precio objetivo.
- Soporte multi-pasajero.
- Exportar resultados a HTML/CSV además de terminal.
- Integrar una segunda fuente de datos (p. ej. scraping ligero de Google Flights)
  como comparación cruzada de precios, no como filtro estructural.

---

## 5. Usuario objetivo

Una sola persona: el propio usuario, pasaporte colombiano, sin visa
estadounidense, buscando vuelos internacionales económicos evitando escalas en
países que requieren visado que no posee. Uso esporádico (cuando planea un viaje),
no un servicio corriendo 24/7.

---

## 6. Requerimientos funcionales

| ID | Requerimiento |
|----|----------------|
| RF-01 | El usuario puede definir origen y destino por código IATA en el archivo de configuración. |
| RF-02 | El usuario puede definir una fecha de salida fija o un límite ("antes de"). |
| RF-03 | El usuario puede definir un rango de días de estadía (mín/máx) para generar combinaciones de fecha de regreso. |
| RF-04 | El usuario puede definir una lista de países ISO (ej. `US`) a evitar como escala. |
| RF-05 | El usuario puede definir una lista de aeropuertos IATA específicos a evitar como escala (ej. `ATL`, `MIA`), independientemente del país. |
| RF-06 | El sistema descarta cualquier itinerario (ida o vuelta) que tenga una escala en un país o aeropuerto de la lista prohibida, sin importar que sea solo tránsito. |
| RF-07 | El usuario puede limitar el número máximo de escalas permitidas por tramo. |
| RF-08 | El sistema ordena los resultados válidos por precio total ascendente; permite orden secundario por duración total del viaje. |
| RF-09 | El sistema muestra, para cada resultado, al menos: aerolínea(s), precio total, fecha/hora de cada segmento, aeropuertos de escala, duración total, número de escalas. |
| RF-10 | El sistema informa claramente cuando una búsqueda no arroja resultados válidos tras aplicar los filtros (y sugiere relajar algún filtro). |
| RF-11 | El sistema no debe mostrar nunca un itinerario que viole los filtros de exclusión, aunque sea el más barato disponible. |

## 7. Requerimientos no funcionales

| ID | Requerimiento |
|----|----------------|
| RNF-01 | El script debe ejecutarse desde terminal sin requerir infraestructura adicional (sin servidor, sin base de datos). |
| RNF-02 | Las credenciales de API deben manejarse por variable de entorno / `.env`, nunca hardcodeadas ni versionadas en git. |
| RNF-03 | El script debe tolerar fallos de red o de API sin crashear de forma opaca; debe registrar el error y continuar o terminar limpiamente. |
| RNF-04 | El tiempo de respuesta para una búsqueda típica (1 fecha, rango de estadía de hasta 6 días) debe ser razonable para uso interactivo (idealmente bajo 1-2 minutos, dependiendo de cuántas combinaciones de fecha se consulten). |
| RNF-05 | El código debe ser fácil de modificar por el propio usuario (listas de exclusión, rutas, filtros) sin tocar la lógica central. |

---

## 8. Decisión: ¿necesita UI/UX?

**No.** Este proyecto no necesita una interfaz gráfica ni web, por las siguientes
razones:

1. **Un solo usuario, uso esporádico.** No hay audiencia externa ni necesidad de
   accesibilidad multiplataforma. Construir UI web agrega complejidad (frontend,
   hosting, estado, diseño) sin resolver mejor el problema.
2. **El dato es inherentemente tabular y secuencial** (lista de vuelos ordenada
   por precio): una terminal con formato claro (tablas, colores, agrupación por
   fecha) comunica esto igual de bien que una interfaz visual, con una fracción
   del esfuerzo de construcción y mantenimiento.
3. **Se va a construir con Claude Code / opencode**, herramientas pensadas para
   flujos de terminal — el entorho natural de este tipo de herramienta es CLI.
4. **No hay necesidad de persistencia de estado entre sesiones** ni de
   colaboración multiusuario, que son los casos donde una UI web empieza a pagar
   su complejidad.

**Recomendación concreta de interfaz:**
- CLI con salida enriquecida en terminal (tablas alineadas, resaltado de la mejor
  opción, resumen de filtros aplicados al inicio de cada corrida).
- Exportación opcional a un archivo (`.csv` o `.html` estático simple) como
  flag opcional (`--export resultados.csv`), para el caso en que el usuario quiera
  compartir o archivar resultados — esto sí vale la pena porque es barato de
  construir y no implica "UI" real, solo una vista alterna de los mismos datos.

Esta decisión y su razonamiento se detallan también en `ARCHITECTURE.md`.

---

## 9. Métricas de éxito (informales, proyecto personal)

- El script nunca muestra un itinerario con escala prohibida.
- El usuario puede correr una búsqueda nueva (otra ruta u otras fechas) editando
  solo el YAML, sin tocar código.
- El tiempo total desde "quiero ver vuelos BOG→MAD" hasta "tengo una lista
  ordenada y filtrada en pantalla" es menor que hacerlo a mano en Google Flights
  revisando escala por escala.

---

## 10. Riesgos conocidos

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| La fuente de datos (API) no cubre todas las aerolíneas de bajo costo / regionales que sí aparecen en Google Flights | Precios no siempre serán el "mínimo absoluto del mercado" | Documentar esta limitación explícitamente en el README; ver `ARCHITECTURE.md` sección de trade-offs |
| Cambios en la API externa rompen el script | Búsquedas fallan hasta actualizar el cliente | Aislar el cliente de API en un módulo separado (ver `TECHNICAL_SPEC.md`) para que un cambio de contrato solo toque un archivo |
| Falsos negativos/positivos en el filtro de escalas (ej. país mal mapeado a aeropuerto) | El script podría mostrar un vuelo con escala prohibida, o descartar uno válido | Mantener el mapeo aeropuerto→país en un archivo de datos versionado y testeable, no en lógica dispersa |

---

## 11. Fase LIVE — precios reales en modo búsqueda solamente (2026-09-21)

> Estado: requerimientos aprobados, **no implementados todavía**. Las Fases 0-7
> terminaron con 59/59 tests contra `duffel_test_*` (TEST/SANDBOX). Todo lo que
> sigue es el alcance de la próxima iteración. Detalle técnico en
> `ARCHITECTURE.md` §9-§12, `TECHNICAL_SPEC.md` §11-§15 e
> `IMPLEMENTATION_PLAN.md` Fase 8+.

### 11.1 Objetivo

Convertir `flight-finder` en un buscador capaz de consultar **precios reales**
(offers live) mediante Duffel cuando sea posible, manteniendo el flujo actual:

```text
SEARCH -> RECEIVE REAL LIVE OFFERS -> FILTER -> SORT -> DISPLAY
```

Nunca:

```text
SEARCH -> BOOK -> PAY
```

### 11.2 Principio no negociable: SEARCH-ONLY

El proyecto sirve únicamente para búsqueda/consulta. No se implementa ni se
ejecuta: creación/confirmación de Orders, pago, emisión de billetes, top-up
automático, ni ningún endpoint que genere obligación de pago. El cliente de esta
aplicación es READ/SEARCH ONLY por diseño (barrera arquitectónica, no solo
convención — ver `ARCHITECTURE.md` §10).

### 11.3 TEST MODE vs LIVE MODE

- Conservar TEST MODE (`duffel_test_*`): precios sandbox, **no reales**, no
  utilizables para decisiones reales. Los tests automatizados siguen corriendo
  sin credenciales reales y sin consumir inventario live.
- Soportar LIVE MODE con el mismo pipeline
  (`API response -> normalization -> filter -> sort -> presentation`); la única
  diferencia es la fuente de datos/modo (`mode: test | live` en config, sin
  duplicar lógica).
- El modo real se detecta por la **respuesta de Duffel (`live_mode`)**, no por
  el nombre del token. Separación de tokens:
  `TEST = duffel_test_*` / `LIVE = live_*`, ambos solo en `.env`.
- Lenguaje obligatorio en presentación: TEST muestra `MODE: TEST / SANDBOX` +
  aviso de precios no reales; LIVE muestra `MODE: LIVE` + `SEARCHED AT`. Nunca
  presentar un precio como "real" si `live_mode == false`.

### 11.4 Requisito económico (pregunta a responder con docs oficiales vigentes)

Antes de tocar credenciales o ejecutar acciones facturables, verificar en la
documentación actual de Duffel (Test Mode, Offer Requests, Offers, Airlines,
Getting Started / Go Live, Pricing, rate limits):

1. Qué necesita Duffel hoy para activar LIVE MODE.
2. Si una búsqueda live puede hacerse sin comprar ningún vuelo.
3. Si hace falta tarjeta registrada, saldo/top-up, información empresarial,
   mínimo de cuenta u otro requisito.
4. Distinguir: coste de buscar vs coste de reservar vs fees de Duffel vs
   necesidad de tarjeta/saldo.

Reglas: no asumir que "activar live implica pagar" ni que "live search es
gratis" sin verificarlo. Si LIVE requiere una condición con coste real,
detenerse antes de modificar credenciales o ejecutar requests potencialmente
facturables y explicar el requisito. Si Duffel permite búsquedas LIVE sin
saldo suficiente para reservar, usar esa posibilidad.

### 11.5 Restricción principal de viaje (aclaración normativa del filtro)

La regla no es "evitar ATL". La configuración canónica es:

```yaml
avoid:
  countries:
    - US
  airports:
    - ATL
```

- Si `US` está en `avoid.countries`, cualquier itinerario con stopover en un
  aeropuerto estadounidense se rechaza, en outbound **y** en inbound.
- Ejemplos: `BOG -> ATL -> MAD / MAD -> BOG` = INVALID;
  `BOG -> MAD / MAD -> MIA -> BOG` = INVALID;
  `BOG -> MEX -> MAD / MAD -> BOG` = potencialmente válido respecto a `US`.
- El programa solo filtra lo configurado por el usuario; **ninguna afirmación
  migratoria automática** del tipo "este aeropuerto no necesita visa".
- Política fail-closed (§10, fila 3): escala sin mapeo país → REJECT, nunca
  ASSUME SAFE (crítico por tratarse de tránsito internacional).

### 11.6 Caso real de referencia (viene de `config.yaml`, no hardcodeado)

```text
origin: BOG, destination: MAD, passengers: 1, cabin: economy
departure.before: 2026-09-28, stay: 10-15 días, ida y vuelta
avoid.countries: [US], avoid.airports: [ATL]
```

### 11.7 Posicionamiento frente a Google Flights

- NO hacer scraping de Google Flights en esta fase.
- Documentar: `Google Flights ≠ Duffel inventory`. Google agrega decenas de
  fuentes; Duffel expone su propio inventario/contenido.
- `Duffel LIVE result` = precio/oferta real disponible vía las fuentes que
  Duffel expone, NO "todos los vuelos que existen".
- No afirmar "los vuelos más baratos del mercado"; decir
  `Cheapest valid offer returned by Duffel`.
- Comparación cruzada con Google Flights: solo manual, para detectar
  diferencias de cobertura/precio, sin automatizar.

### 11.8 Requerimientos funcionales nuevos

| ID | Requerimiento |
|----|----------------|
| RF-12 | El usuario puede seleccionar `mode: test \| live` en config sin duplicar pipeline; el mismo flujo normaliza/filtra/ordena/presenta en ambos modos. |
| RF-13 | El sistema detecta el modo efectivo desde `live_mode` de la respuesta Duffel (`offer_request.live_mode`, `offer.live_mode`) y lo expone en modelos y presentación. |
| RF-14 | El sistema conserva y muestra datos enriquecidos del Offer cuando Duffel los provee: offer ID, total amount/currency, `live_mode`, `created_at`, `expires_at`, `owner` (+name, IATA), baggage, y por segmento: aeropuertos, horarios, duración, flight number, marketing carrier (+name/IATA) y operating carrier (+name/IATA). |
| RF-15 | La presentación distingue `Marketing carrier` vs `Operating carrier` (no solo código IATA) y etiqueta carriers de prueba (`ZZ` o equivalentes) como TEST/SANDBOX, nunca como aerolínea real. |
| RF-16 | En TEST se muestra `SOURCE: Duffel / MODE: TEST / SANDBOX / WARNING: prices and availability are not real market fares`; en LIVE, `SOURCE: Duffel / MODE: LIVE / SEARCHED AT: <timestamp>`. |
| RF-17 | Cada Offer de ida y vuelta se presenta como unidad con `OUTBOUND` + `RETURN` + `TOTAL` explícitos; nunca presentar una ida como precio total del viaje. |
| RF-18 | Antes de una búsqueda LIVE grande, el CLI muestra estimación (`Search combinations`, `Maximum API requests`, `Mode: LIVE`) y respeta rate limits vigentes con requests secuenciales/controlados, backoff, manejo 429, logging de requests y límite configurable de combinaciones. |
| RF-19 | La validación live expone por búsqueda `offer_request.live_mode`, `offer.live_mode`, owner, carrier, precio, moneda, y exige `live_mode == true` antes de llamar a un resultado "LIVE". Primera prueba: 1 sola combinación; luego ampliar. |

### 11.9 Requerimientos no funcionales nuevos

| ID | Requerimiento |
|----|----------------|
| RNF-06 | El cliente HTTP de la aplicación no contiene métodos de booking (`Orders`/`Payments`/`Bookings`); la imposibilidad de compra es estructural y verificable por test. |
| RNF-07 | Tokens solo en `.env`; prohibido hardcodear, imprimir, loggear, incluir en HTML/CSV/tests o versionar. No relajar `.gitignore` para secretos. |
| RNF-08 | Búsqueda LIVE conservadora por defecto: pocas combinaciones útiles, secuenciales, con backoff y 429; cientos de requests paralelos están prohibidos. |
| RNF-09 | No presentar datos TEST como reales; no inventar nombres de aerolíneas (usar `owner`/`marketing_carrier`/`operating_carrier` oficiales); no prometer equipaje incluido si la API no lo garantiza. |

### 11.10 Criterio de éxito de la fase LIVE

`flight-finder --config config.yaml` produce ofertas donde: datos vienen de
Duffel LIVE con `live_mode=true` (no sandbox), son ida+vuelta completas, US
excluido cuando `avoid.countries: [US]` (+ ATL excluible), ordenadas por
precio, sin ninguna compra, sin booking implementado, secretos fuera del repo,
tests en verde y documentación con las limitaciones (§11.7). Presentación por
oferta: PRICE, CURRENCY, AIRLINE, MARKETING/OPERATING CARRIER, OUTBOUND,
RETURN, STOPS, DURATION, BAGGAGE, EXPIRATION, LIVE/TEST; y al final conteos
`VALID OFFERS / FILTERED BY US / FILTERED BY AIRPORT / FILTERED BY MAX STOPS`.

### 11.11 Explícitamente NO hacer en esta fase

No migrar de arquitectura sin necesidad; no cambiar Python/uv; no añadir
frontend web, base de datos, scraping de Google Flights, reservas, pagos,
multi-passenger, multi-city; no eliminar tests; no hardcodear fechas, países ni
nombres de aerolíneas; no poner secretos en código; no lanzar cientos de
requests LIVE; no presentar datos TEST como reales.
