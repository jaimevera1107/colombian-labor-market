# ICML 2.0 — Etapa A: estudio multicriterio de donantes (Pareto)

**Estado:** propuesta versionada, no activada. Exclusivamente datos existentes del proyecto. No se ejecutan etapas B o C.

## Pregunta y universo

Se comparan exhaustivamente **207 alternativas individuales**, 9 receptoras × 23 donantes, con las señales del proyecto. Las nueve receptoras conservan una alternativa y dos respaldos. La unidad sintética Cundinamarca (código 25) **no es una ciudad receptora** y no forma parte de este catálogo de nueve; su tratamiento pertenece a un flujo separado de la etapa A. Además se prueba, solo como sensibilidad, una mezcla de los tres mejores candidatos, sin optimizar todas las combinaciones posibles.

## Método y cautelas

1. **Cinco pérdidas simultáneas:** diferencia media absoluta de crecimientos logarítmicos de ocupados y de población; brecha de tasas de desempleo, participación y ocupación; distancia logarítmica de tamaños poblacionales; y dispersión logarítmica del factor relativo entre receptora y donante. Se minimizan las cinco. El tamaño mide comparabilidad, **nunca se copia la escala del donante**.
2. **Dominancia de Pareto:** se retira un donante únicamente si otro es no peor en los cinco criterios y estrictamente mejor al menos en uno. La frontera cambia si se modifican datos, criterios o ventana; por eso la asignación seleccionada se almacena por versión, no se elige automáticamente cada mes.
3. **Elección dentro de la frontera:** distancia ponderada al vector ideal (0,30, 0,20, 0,20, 0,10, 0,20, respectivamente). Escalas normalizadoras calculadas con las 506 parejas entre las 23 ciudades históricas. No se busca que el donante tenga la misma cantidad de personas.
4. **Guardias (criterio normativo, no prueba de verdad histórica):** diferencia media de error logarítmico sobre las cuatro magnitudes básicas en la referencia anual-proxy de 2025 y desajuste del puente 2021 no pueden empeorar más de **0,03 unidades logarítmicas** respecto al donante vigente. Si no existiera un candidato eficiente admisible, se conservaría el vigente como excepción registrada.
5. **Retropolación:** cuatro magnitudes básicas del receptor calibradas por suma de 2021–2024; para 2007–2020 se usa únicamente la evolución del donante. PEA y PET se derivan contablemente. No se imputan meses. No se reconstruye aquí la mensualidad ni se evalúan departamentos.
6. **Validación:** 23 ciudades con pasado 2007–2020 ocultado a la selección. 2025 participa en la guardia final, así que **no** es una prueba completamente independiente de la decisión. Las referencias anuales son promedios de ventanas móviles; no equivalen necesariamente a datos de año calendario. Los receptores pequeños quedan fuera de soporte para algunas dimensiones.

## Validación retrospectiva de reglas (23 ciudades)

| Regla | WAPE medio (%) | Peor ciudad (%) | Control 2025 promedio (log %) | Puente 2021 promedio (log %) |
|---|---:|---:|---:|---:|
| frontera_distancia | 10.63 | 17.44 | 5.96 | 4.78 |
| equilibrado | 10.82 | 18.86 | 6.18 | 5.02 |
| factor_estable | 10.82 | 18.86 | 6.18 | 5.02 |
| pareto_con_guardia | 10.96 | 17.44 | 5.72 | 4.40 |
| frontera_minimax | 11.67 | 24.08 | 6.26 | 4.77 |
| frontera_media | 12.10 | 28.67 | 5.72 | 4.23 |

La regla con guardias preserva el peor error por ciudad de la distancia Pareto sin guardias, pero el error medio es mayor. **No puede afirmarse dominancia universal sobre todas las reglas.**

## Propuesta de donantes

| Receptora | Vigente | Propuesto | Respaldo 1 | Respaldo 2 | N.° Pareto | Domina al vigente en cinco dimensiones |
|---|---|---|---|---|---:|---|
| Arauca | Armenia | Armenia | Tunja | Bucaramanga A.M. | 9 | No |
| Yopal | Neiva | Villavicencio | Popayán | Sincelejo | 16 | No |
| Mocoa | Florencia | Armenia | Riohacha | Florencia | 9 | No |
| San Andrés | Quibdó | Quibdó | Florencia | Manizales A.M. | 15 | No |
| Leticia | Cúcuta A.M. | Manizales A.M. | Armenia | Riohacha | 15 | Sí |
| Inírida | Cali A.M. | Medellín A.M. | Armenia | Florencia | 9 | No |
| San José del Guaviare | Pereira A.M. | Riohacha | Manizales A.M. | Pereira A.M. | 16 | No |
| Mitú | Barranquilla A.M. | Armenia | Florencia | Tunja | 11 | Sí |
| Puerto Carreño | Pasto | Bucaramanga A.M. | Popayán | Florencia | 18 | No |

Los **nueve seleccionados pertenecen a sus respectivas fronteras no dominadas**. Solo dos propuestas dominan estrictamente al vigente en las cinco dimensiones. Los restantes casos son compromisos entre criterios, no mejoras de Pareto respecto del donante anterior. No hay un "óptimo universal" único.

## Balance de controles (nueve ciudades)

- Error medio logarítmico de 2025: **9.85 % vigente** vs **8.68 % propuesto**. Este porcentaje es solo una representación de una magnitud logarítmica, no WAPE.
- Puente medio logarítmico 2021: **5.81 % vigente** vs **6.36 % propuesto**. Aumenta levemente; **no esconder este costo**.
- No hay cantidades negativas, vacíos ni PET superior a población en las propuestas.

## Sensibilidad a la tolerancia de guardias

| Tolerancia (log) | Asignaciones idénticas a la versión 0,03 |
|---:|---:|
| 0.00 | 3/9 |
| 0.02 | 7/9 |
| 0.03 | 9/9 |
| 0.04 | 8/9 |
| 0.06 | 5/9 |

El resultado NO es inmune a la elección de tolerancia, por lo que el catálogo debe congelarse con esa regla documentada. Las pruebas de anexos junio/agosto de 2026 muestran que **2021–2025 permanece idéntico**, mientras el 2026 provisional sí evoluciona. No corresponde recalcular los donantes con esa actualización.

## Mezclas: comparación, no activación

| Opción | WAPE medio retrospectivo (%) | Peor ciudad (%) |
|---|---:|---:|
| 1 donante(s) | 10.63 | 17.44 |
| 2 donante(s) | 9.94 | 20.59 |
| 3 donante(s) | 9.76 | 22.30 |

Las mezclas de dos y tres señales escaladas reducen el error medio, pero **empeoran la peor ciudad**, por lo que no son una mejora global no dominada evidente frente al donante individual. No se han evaluado exhaustivamente las 253 parejas ni las 1771 ternas posibles por receptor: esta comprobación usa los mejores donantes de la frontera.

## Alcance de Pareto y bienestar

Si no se impone capacidad ni exclusividad de uso del donante, las nueve selecciones son matemáticamente **separables**. Una cartera con un donante no dominado por ciudad es eficiente respecto de las 45 pérdidas (5×9) consideradas, pero existen muchas carteras eficientes. La regla normativa de distancia al ideal y sus guardias escoge una versión reproducible, **no prueba precisión histórica no observable ni satisfacción de todas las preferencias posibles**.

## Archivos y ejecución

- `results/evaluacion_207_alternativas.csv`: todas las parejas y controles; `pareto_eficiente` indica pertenencia a la frontera.
- `results/validacion_23_ciudades_6_reglas.csv`: métodos y WAPE observados contra 2007–2020.
- `results/catalogo_pareto_nueve_propuesto.csv` y `catalogo_congelable_NO_ACTIVO.json`: catálogo con hash SHA-256 y respaldo, no activado.
- `results/sensibilidad_tolerancia.csv` y `results/estabilidad_anexos_junio_agosto.csv`: estabilidad metodológica y temporal.
- `results/validacion_mezclas_pareto_23.csv`: comparación opcional de 1, 2, 3 donantes.
- `exports/visualizacion/00_indice_visual.html`: diez imágenes y explicación visual.
- `src/catalogo_congelado.py`: lector con validación de integridad y bloqueo para uso productivo si no aprobado.
- Ejecutar: `python src/estudio_pareto.py`; luego `pytest -q`.

**Siguiente acción dentro de A:** revisar el catálogo versionado, decidir su activación explícita y ejecutar la reconstrucción histórica definitiva con esos donantes. Las fases B y C siguen fuera de alcance.
