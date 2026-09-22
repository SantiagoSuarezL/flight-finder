<!-- scaffold:system:start -->
# AUDIT DE DRIFT

> Invocación explícita del usuario — nunca automático. Frecuencia sugerida: al
> cerrar una fase mayor, o ~mensual.

Compará la memoria documentada contra la realidad del código. Reportá solo
DESAJUSTES, no confirmaciones — lo que está bien no necesita mención.

## Verificaciones (en orden, reportá al final en un solo bloque)

1. `tech_stack.md` vs realidad: ¿las dependencias listadas siguen siendo las
   del manifest real (`pyproject.toml` / `package.json` / etc.)? ¿Apareció
   alguna lib nueva no registrada en "Protocolos Críticos" que merezca regla?
2. `roadmap.md` vs git log: ¿las fases marcadas ✅ corresponden a work
   realmente mergeado? ¿Hay commits que impliquen avance de fase no reflejado?
3. `lessons_learned.md` vs código: tomá las 3 reglas de oro más recientes y
   verificá con grep/graphify que el patrón que prohíben no aparece violado en
   el código actual.
4. graphify: leé `graphify-out/GRAPH_REPORT.md`. ¿Hay god nodes nuevos,
   comunidades que se fusionaron, o conexiones sorprendentes que contradigan
   supuestos de architecture asumidos en sesiones previas?
5. `observations.md`: ¿alguna observación "en curso" ya quedó resuelta por
   código existente y debería moverse a archive + regla de oro?
6. Cobertura de `.gitignore`: ¿`graphify-out/` y artefactos de build siguen
   ignorados? ¿Se acumulan archivos no versionados que deberían estarlo?

## Formato del reporte

Por cada desajuste:

> `[archivo de memoria]` dice X / realidad dice Y / acción sugerida (una línea).

Cerrá con: total de desajustes y si requieren actualización de memoria ya
(protocolo de salida) o pueden esperar al cierre de sesión.

El audit reporta, no corrige. Las correcciones van por `PROTOCOLO_SALIDA.md`
normal o por decisión del usuario.
<!-- scaffold:system:end -->
