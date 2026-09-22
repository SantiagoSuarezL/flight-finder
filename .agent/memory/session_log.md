# Session Log — flight-finder

> MEMORIA ACTIVA. Se lee completa al inicio de sesión.
> REGLA DE ROTACIÓN (obligatoria, no opcional): al cerrar CADA sesión nueva,
> la sesión que hoy está en "ÚLTIMA SESIÓN" se comprime a 1-3 líneas y pasa a
> "HISTORIAL RELEVANTE"; el detalle completo se mueve a `session_log_archive.md`.
> Nunca debe haber más de 1 sesión en detalle completo en este archivo.
> Si este archivo supera ~150-200 líneas, la compresión no se está
> aplicando — parar y corregir antes de seguir agregando.

---

## ÚLTIMA SESIÓN (detalle completo)

`Sesión 15 — 2026-09-22 — Muse Spark via OpenCode (Fase 13.5 async + preset)`

- **Preset óptimo ✅:** `config.example.yaml` top_n 10→3 (6 combos + drill 3 = 9 req) + assert en `test_config.py`; fallback web igual; README con números nuevos.
- **Async ✅:** `/run` lanza thread y redirige en ~30ms; `run_search` con `on_progress`/`should_cancel` (CLI intacto); página pending con progreso X/Y + Cancelar → resultado parcial etiquetado; error interno genérico sin detalle.
- **Verificación ✅:** suite **140/140**; e2e real con 1 request (searchapi 1 combo): pending visto, SOURCE/LINK/1119/CSV OK; `graphify update`.
- **Cuota sesión:** 1 request (autorizado). Pendiente usuario: probar web en navegador + PASO 4 Fase 12.

---

## HISTORIAL RELEVANTE (comprimido, detalle completo en session_log_archive.md)

- Sesión 14 (22-09): Fase 13 web UI + links ✅ — search.py compartido, web.py stdlib con idempotencia, 137/137, smoke 0 requests.
- Sesión 13 (22-09): Fase 12 validación real ✅ — dry-run + separate_tickets, 1 combo/proveedor (IB152 1119 ambos), vuelos.csv corroborado; 121/121.
- Sesión 12 (21-09): Fase 11.7 cierre ✅ — test_no_booking, borrado Duffel total, check_provider.py; 121/121; Fase 11 CERRADA.
- Sesión 11 (21-09): Fase 11.6 cli ✅ — FlightsClient, estimación antes de requests, drill-down top N; 118/118.
- Sesión 10 (21-09): Fase 11.5 presenter ✅ — banner SOURCE/SEARCHED AT/NOTE, cards PRICE/AIRLINE/CARBON, vuelta `not expanded`, CSV/HTML sin Duffel; 112/112.
- Sesión 9 (21-09): Fase 11.4 filters/sorter ✅ — `inbound=None` tolerado, sorter `price`; test_filters con fixtures Google Flights; 100/100.
- Sesión 8 (21-09): Fase 11.3 config ✅ — `provider`/`currency`/`drill_down`, fuera `mode`; 81/81.
- Sesión 7 (21-09): Fase 11 código por sub-fases — 11.1 models ✅ (30/30), 11.2 flights_client ✅ (26/26).
- Sesión 6 (21-09): Fase 11 PASO 1 docs — `INFORME_FASE_11.md` GO; specs migrados; regla de cuota dry-run.
- Sesión 1 (21-09): scaffolding uv + Fase 1 (models, 10/10); regla uv (1.1).
- Sesión 5 (21-09): Fase 10 TEST (3049 ofertas, 99/99); LIVE bloqueado por billing.
