# INDEX — Mapa de Memoria

> Leé esto SIEMPRE primero, completo (es corto a propósito).

## Estado del proyecto

**Proyecto:** flight-finder
**Fase actual:** 13 — Interfaz web local + links ✅ CERRADA (stdlib, 127.0.0.1, async+progreso+cancelar, preset 6+3; suite 140/140; 1 request e2e)
**Próxima fase:** sin fase nueva definida — uso normal (CLI o `flight-finder-web`, siempre con estimación+confirmación)

## Tabla de archivos

| Archivo | Cuándo leerlo |
|---|---|
| `INDEX.md` | Siempre, primero |
| `session_log.md` | Siempre |
| `lessons_learned.md` | Siempre |
| `tech_stack.md` | Siempre |
| `roadmap.md` | Siempre |
| `observations.md` | Siempre |
| `*_archive.md` | Nunca automático — grep puntual si la tarea toca fase vieja |
| `BOOTSTRAP.md` | Solo la primera vez (invocación explícita del usuario) |
| `AUDIT_DRIFT.md` | Solo bajo invocación explícita del usuario (~mensual) |

## Convenciones

- `session_log.md`: 1 sesión en detalle ("ÚLTIMA SESIÓN") + resto comprimido;
  la rotación mueve el detalle a `session_log_archive.md`.
- `lessons_learned.md`: solo reglas de las últimas 2 fases; lo viejo se archiva
  verbatim y queda una línea en el índice de archivadas.
- Referencias cruzadas por número de Regla de Oro (`X.Y`); `tech_stack.md`
  referencia con `(Ref: X.Y)`.
- `observations.md`: resuelta → `observations_archive.md` + línea de cierre
  apuntando a la Regla de Oro.
