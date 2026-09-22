# Observaciones — flight-finder

> 5to archivo del protocolo, explícito (no un archivo suelto). Solo
> observaciones EN CURSO (no resueltas todavía, requieren más monitoreo).
> Una vez que una observación se convierte en regla de código confirmada,
> se archiva en `observations_archive.md` y queda solo una línea de cierre
> acá apuntando a la Regla de Oro correspondiente en `lessons_learned.md`.

Formato de cada entrada: fecha, target/módulo, observación, hipótesis, estado, acción.

## En curso

- **2026-09-21 / `opencode.json` (raíz, NO versionado — está en `.gitignore`,
  verificado con `git ls-files`):** contiene API keys en texto plano
  (OpenRouter `sk-or-v1-...`, NVIDIA `nvapi-...`), solo riesgo local.
  Hipótesis: config local necesaria para el harness.
  Estado: riesgo acotado; si alguna vez se comparte el repo sin `.gitignore`,
  rotar las keys. Acción: re-evaluar si cambia el versionado.
- **2026-09-21 / Cuota gratuita SerpApi/SearchApi:** usuarios free no tienen
  tarjeta; excedente requiere upgrade. Falladas no cobran; SerpApi cache 1h
  gratis. Hipótesis: ~6-16 requests por ejecución (6 combos + drill-down)
   → limitan cuántas ejecuciones/semana. Estado: en curso — Fase 12 consumió
   ~10 requests (8 búsqueda serpapi 21-09 + 2 validación 22-09), dentro del
   free tier. Acción: usuario revisa dashboards (PASO 4); dry-run antes de
   cada request futuro; `config.validate.yaml` queda como helper 1-combo.
   Desde Fase 13 la web exige confirmación explícita de la estimación
   (topes UI: top_n 50, max_combinations 31).

(2026-09-21 / Duffel LIVE / billing on file: archivada — el motivo del
bloqueo live quedó sin importancia al cancelarse la Fase 10b y migrar a
SerpApi/SearchApi en Fase 11.)
