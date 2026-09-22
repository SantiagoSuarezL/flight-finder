<!-- scaffold:system:start -->
# PROTOCOLO DE SALIDA (Mantenimiento de Memoria) — v2

Antes de pasar a la siguiente fase, verificá qué hiciste y actualizá los
archivos siguientes en `.agent/memory/` según las reglas de abajo.
Son 5 archivos activos — `observations.md` es parte del protocolo
explícitamente, no un archivo suelto.

## 1. `tech_stack.md`

Solo si la tarea introdujo un cambio CRÍTICO en el stack (nueva librería,
cambio de arquitectura). Agregá a "Protocolos Críticos":
- Una línea corta y prescriptiva (qué regla, qué invariante).
- Referencia `(Ref: X.Y)` al número de Regla de Oro en `lessons_learned.md`.
- **NO repitas ahí la historia completa (bug/root cause/solución)** — esa
  narrativa vive UNA sola vez, en `lessons_learned.md`. Si te encontrás
  copiando 3+ líneas de contexto en `tech_stack.md`, pará: es una señal de
  que estás duplicando en vez de referenciar.

## 2. `lessons_learned.md`

Solo si hubo un error técnico NUEVO no documentado o comportamiento
inesperado de la IA que se corrigió. Formato:
```
X.Y [Categoría]: [Título breve]
- Error: ...
- Root Cause: ...
- Solución: ...
- Regla de Oro: [máximo 2-3 líneas, imperativo]
```
**Regla de rotación (obligatoria):** este archivo debe contener solo las
reglas de las últimas 2 fases. Si al agregar la regla nueva quedan reglas
de 3+ fases atrás en detalle completo, movélas a `lessons_learned_archive.md`
tal cual (verbatim) y dejá en su lugar una línea en el "Índice de reglas
archivadas" al principio del archivo activo.

## 3. `roadmap.md`

Si se completó un hito mayor o se detectó una tarea de arquitectura crítica.
No repitas acá el detalle de decisiones ya explicado en `lessons_learned.md`
o `session_log.md` — solo el estado (✅/[ ]) y una referencia si hace falta.

## 4. `observations.md`

Si durante la tarea surgió una observación de comportamiento en curso (no
resuelta todavía, requiere más monitoreo). Cuando una observación se
resuelve y queda blindada en código: mové la entrada completa a
`observations_archive.md` y dejá solo una línea de cierre en `observations.md`
apuntando a la Regla de Oro correspondiente en `lessons_learned.md`.

## 5. `session_log.md` (MANDATORIO — máx 5 bullets para la sesión nueva)

La sesión nueva arranca siempre con esta primera línea (obligatoria):

`Sesión N — 2026-09-21 — [modelo + harness que ejecutó: ej. "GLM 4.6 vía OpenCode"]`

Resumí lo hecho hoy: qué se hizo, archivos modificados, líneas/notas clave.

**Regla de rotación (obligatoria, no opcional):**
- Este archivo debe tener SIEMPRE como máximo 1 sesión en detalle completo
  (la de "ÚLTIMA SESIÓN") + el resto en "HISTORIAL RELEVANTE" (1-3 líneas
  cada una, ~150-200 caracteres).
- Antes de escribir la sesión nueva: tomá lo que hoy está en "ÚLTIMA SESIÓN",
  comprimilo a 1-3 líneas, agregalo arriba de todo en "HISTORIAL RELEVANTE",
  y movés el detalle completo de esa sesión (verbatim) a
  `session_log_archive.md`.
- Si en algún momento `session_log.md` supera ~150-200 líneas totales,
  es señal de que la compresión no se está aplicando — parar y corregir
  antes de seguir agregando.

## Chequeo final antes de cerrar

- [ ] `session_log.md` tiene 1 sola sesión en detalle completo, no más.
- [ ] Ninguna Regla de Oro ni decisión aparece duplicada palabra-por-palabra
      en dos archivos activos distintos.
- [ ] Si moviste algo a un `*_archive.md`, dejaste la línea de índice/referencia
      correspondiente en el archivo activo.
<!-- scaffold:system:end -->
