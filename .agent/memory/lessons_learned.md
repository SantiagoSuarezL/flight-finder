# Lessons Learned — flight-finder

> MEMORIA ACTIVA. Se lee completa al inicio de sesión.
> Reglas de fases viejas: ver `lessons_learned_archive.md` (NO se lee
> automático, solo por grep/keyword si la tarea actual toca esa fase).
> Regla de rotación: este archivo debe contener solo las reglas de las
> últimas 2 fases. Al cerrar una fase nueva, la más vieja de las que
> quedan acá pasa al archivo y se reemplaza por una línea de índice abajo.

## Índice de reglas archivadas

(vacío todavía)

---

## Reglas activas

### Regla de Oro 1.1 [Tooling]: Tras `uv sync`, el `.venv` queda sin `pip`

**Error:** `.venv/Scripts/python -m pip` falla con `No module named pip`
después de migrar el entorno a uv.

**Root Cause:** `uv sync` gestiona el entorno él mismo y desinstala
`pip`/`setuptools` del `.venv` (innecesarios para uv).

**Solución:** entorno reparado con `ensurepip` para el bootstrap inicial,
luego migrado con `uv sync --extra dev` (reutiliza el `.venv` existente,
genera `uv.lock`).

**Regla de Oro:** *Gestioná el entorno solo con `uv` (`uv sync`, `uv add`, `uv run`); nunca invoques `pip` dentro de `.venv`.*

### Regla de Oro 5.1 [Output]: Mensajes visibles al usuario en ASCII seguro

**Error:** `print(exc)` de `DuffelAuthError` crasheaba con
`UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'`
en consola Windows (cp1252).

**Root Cause:** la flecha `→` (y cualquier glyph fuera de cp1252) en
mensajes de excepción, `print` o logs que llegan a consola real. Los tests
no lo detectan (capturan en UTF-8).

**Solución:** `duffel_client.py`, `config.py`, `scripts/check_duffel.py`:
`→` → `->` en todo string visible al usuario (verificación manual con
token falso).

**Regla de Oro:** *Todo string que pueda imprimirse en consola (errores, prints, logs) usa solo ASCII seguro (`->` en vez de `→`); tildes sí, símbolos no. Verificar en consola real, no solo con pytest.*

### Regla de Oro 9.1 [Models/Live]: `live_mode` es obligatorio y los carriers son opcionales [OBSOLETA desde Fase 11]

> **OBSOLETA** (Fase 11, migración a SerpApi/SearchApi): `live_mode` ya no
> existe en el contrato de modelos (`TECHNICAL_SPEC.md` §13 / `INFORME_FASE_11.md`).
> Fail-closed ahora aplica sobre `price`/`currency`/`segments` ausentes, no sobre
> `live_mode`. Carrier/baggage tolerante y etiquetado honesto: sigue vigente
> en esencia. Se conserva abajo verbatim como referencia histórica.

**Error:** `normalize_offer` fallaba con `live_mode` ausente vs. tolerar
carriers malformados llevó a diseñar `CarrierInfo`/`OwnerInfo`/`BaggageInfo`
opcionales con `?`/`None`.

**Root Cause:** `offer.live_mode` es la única fuente de verdad TEST/LIVE
(`TECHNICAL_SPEC.md` §13); un offer sin `live_mode` no se puede clasificar y
presentarlo como "real" sería engañoso. En cambio, `operating_carrier`/`name`
pueden faltar o venir malformados sin comprometer el filtrado de escalas.

**Solución:** `models.py:94` — `_carrier_info` devuelve vacío ante no-dict,
`_parse_segment` usa `?` para `marketing_carrier`/`flight_number` faltantes,
`_aggregate_baggage` exige pasajeros en todos los segmentos o `None`
(`not confirmed by API`). Fixture `live_offers.json` con `AA`/`AM` reales para
tests live.

**Regla de Oro:** *`live_mode` faltante → `ValueError` (fail-closed); carriers/baggage faltantes → `None`/`?` (tolerante pero etiquetado TEST/SANDBOX si `ZZ`).*
