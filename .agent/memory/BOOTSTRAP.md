<!-- scaffold:system:start -->
# PROTOCOLO DE BOOTSTRAP

> Correr UNA sola vez, al arrancar el proyecto. Invocación explícita del usuario.

La estructura de `.agent/memory/` ya existe (la creó el script de scaffold). Tu
trabajo acá es solo POBLAR. No crees archivos.

## Paso 1 — Leer los docs UNA vez completos

Leé `README.md` y todo `docs/` completo, en una única lectura sin criterio de
selección. Es el único momento en todo el proyecto en que los specs se leen
enteras: en sesiones siguientes aplica el criterio de `PROTOCOLO_INICIO.md`
(punto 4), no esta regla.

## Paso 2 — Poblar tech_stack.md

Leé `docs/ARCHITECTURE.md` / `TECHNICAL_SPEC.md` (o el doc equivalente) y
completá `.agent/memory/tech_stack.md`:
- `## Stack Actual`: lenguaje, dependencias principales, arquitectura (árbol
  de carpetas real), tooling, suite de tests.
- `## Protocolos Críticos`: solo invariantes que costó aprender, con referencia
  `(Ref: X.Y)`. No transcribas el spec.

## Paso 3 — Poblar roadmap.md

Copiá las fases desde `docs/IMPLEMENTATION_PLAN.md` (o el doc que defina fases)
a `.agent/memory/roadmap.md` (`## Fases`), con sus nombres y orden. Si no hay
fases explícitas, proponé una división en fases y esperá confirmación antes de
escribir.

## Paso 4 — Actualizar INDEX.md

En `.agent/memory/INDEX.md`, actualizá `## Estado del proyecto`:
- `Fase actual`: 0 (setup inicial).
- `Próxima fase`: 1 — con el nombre de la primera fase real.

## Paso 5 — Confirmar

Avisame con un resumen de 2-3 líneas: stack detectado, fases del roadmap y
cualquier pregunta antes de asumir algo. No asumas: confirmá.

## Nota sobre archivos ya existentes

Los 9 archivos de memoria existen con su estructura vacía. Verificá que los
headers estén intactos al escribir; no los regeneres.
<!-- scaffold:system:end -->
