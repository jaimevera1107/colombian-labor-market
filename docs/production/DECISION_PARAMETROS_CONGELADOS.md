# Decisión: parámetros congelados al incorporar un mes nuevo

**Estado:** adoptada por el responsable del proyecto el 2 de noviembre de
2026. **Alcance:** actualizaciones ordinarias mensuales posteriores a la
vintage de agosto de 2026.

## Regla

Una actualización ordinaria **reutiliza sin reentrenar**:

* el puente censal CNPV 2018 (`censo/puente_v001`);
* los *priors* departamentales del MLP de H9
  (`informalidad/census_transfer_v012`);
* las características sectoriales congeladas de H16.

Solo se agregan observaciones del mes nuevo y se actualizan los resultados
que legítimamente dependen de ellas, según la política de estados
`definitivo` / `sujeto_a_ancla` / `provisional`
(`docs/evaluation/04_UPDATE_POLICY.md`).

## Razones

1. **Comparabilidad**: reentrenar con cada mes cambiaría el histórico por
   motivos ajenos a los datos nuevos.
2. **Coherencia con H36**, que ya conserva estos parámetros congelados.
3. **Costo y trazabilidad**: una actualización ordinaria no debe requerir
   entrenar modelos ni depender de la versión de `torch`.

## Cuándo no aplica la regla

Un cambio de fuente o de método (rediseño de la GEIH, nuevas proyecciones
de población, nuevo censo, cambio de definición) **no** es una actualización
ordinaria: exige reprocesamiento completo y una versión nueva, conservando
las vintages anteriores.

## Riesgos conocidos y condiciones de revisión

* Los parámetros congelados pueden volverse inadecuados si los datos nuevos
  se alejan de lo que ellos supusieron. La regla no incluye aún un criterio
  numérico de deriva; **debe definirse** (por ejemplo, error de la
  predicción del mes nuevo frente a su referencia observada).
* La versión de `torch` con la que se entrenaron los *priors* originales no
  está registrada; la regla evita depender de ella, pero no la recupera.
* Si la validación científica independiente de H9 (Fase 4 del roadmap)
  encuentra problemas sustantivos en los *priors*, esta decisión se revisa.
