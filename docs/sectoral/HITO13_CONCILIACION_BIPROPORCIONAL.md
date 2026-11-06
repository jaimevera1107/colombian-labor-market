# ICML 2.2.18.dev0 — Hito 13: cierre departamental × sector (1993–2026)

**Estado:** EXECUTED / EXPERIMENTAL / NONCANONICAL. La conciliación matemática **no** produce información sectorial departamental observada. La puerta de publicación permanece bloqueada.

## Base y límites

Se emplean **exclusivamente las salidas congeladas del H12**: (i) los 599.940 priors de 33 departamentos × 15 sectores × 404 meses × 3 escenarios; (ii) composición sectorial nacional del H11/H10; (iii) ocupados departamentales de ambos universos; y (iv) auditoría de universos H12. Todos se incluyen en `inputs/` con SHA-256 en `13_puerta_calidad.json`.

* Enero 1993 a junio 2001: composición nacional **estimada** a partir de tendencias DANE ENH de septiembre y homologación tentativa, **no dato sectorial mensual oficial**.
* Julio 2001 a diciembre 2014: composición nacional estimada por inversión de trimestres móviles H11, con incertidumbre por clasificación histórica.
* Enero 2015 a agosto 2026: composición apoyada en los 13 grupos oficiales mensuales DANE, **pero** el desdoblamiento de `B`/`D_E` se mantiene supuesto y `NO_INFO` es residual.
* Los 33 patrones geográficos del H12 son **priors hipotéticos** (neutral, rural débil, rural moderado); no hay ocupados sectoriales departamentales observados ni coeficientes territoriales ajustados a ellos.
* 1993–2000: los ocupados departamentales representados **NO** cierran al DANE nacional. H13 no intenta corregir esa diferencia, ni impone un margen sectorial nacional GEIH antes de 2001.

## Método

Cada celda tiene una participación `p[d,s,t]` que se aplica **sin cambio de proporción** a los ocupados departamentales completos y representados. Para cada mes y escenario se busca la solución de **mínima divergencia KL ponderada por ocupados completos** respecto al H12, con estos márgenes:

1. `sum_s p[d,s,t] = 1` en cada departamento: se mantienen exactamente los ocupados completos y los ocupados representados de cada territorio.
2. `sum_d ocupados_completos[d,t] × p[d,s,t] = ocupados_nacionales_ICML[t] × q[s,t]`.
3. **Solo desde enero 2001:** `sum_d ocupados_representados[d,t] × p[d,s,t] = ocupados_nacionales_representados[t] × q[s,t]`.
4. Participaciones no negativas; una rama con margen nacional cero permanece **cero**; nunca se reparte `NO_INFO` en ramas productivas por obligación contable.

Se resuelve mediante un sistema dual convexo con potenciales por sector y exposición representada estandarizada, método de Newton con búsqueda de paso y chequeo explícito de márgenes. Fallo de convergencia o inconsistencia de entradas **produce error**, no salidas aparentes. No se modifican ni los priors H12 ni las series nacionales, departamentales o DANE.

El tercer margen es una **restricción metodológica del escenario**, no un dato sectorial territorial oficial. Dado que el `q` nacional se transfiere a dos universos, imponerlo en ambos puede forzar grandes ajustes en los territorios menos representados.

## Resultados ejecutados

- 404 meses × 33 territorios × 15 sectores × 3 escenarios = **599.940 filas**.
- Error máximo de margen sectorial nacional del universo completo: **4,66 × 10⁻⁵ personas**.
- Error máximo de margen sectorial nacional representado desde 2001: **2,88 × 10⁻⁵ personas**.
- Error máximo de cierre departamental (ambos universos): **1,86 × 10⁻⁹ personas**.
- Corrección máxima de participación (H13 respecto al prior H12): escenario neutral ~0 pp; rural débil **3,817 pp**; rural moderado **8,937 pp**.
- El máximo se encuentra en **Vichada, sector A, agosto de 2020**. Otras correcciones altas ocurren en departamentos poco representados por GEIH.
- En 459 combinaciones mes-escenario y 2.929 celdas se excede el umbral **operativo y convencional** de 3 pp (es alerta de sensibilidad, no límite estadístico inferencial).
- Solución convergente con un máximo de cuatro iteraciones de Newton en todos los meses reales.

### Comparación obligatoria: cierre solo completo vs. cierre conjunto

| Escenario | Máximo ajuste con cierre del completo (pp) | Máximo ajuste con cierre conjunto (pp) | Máxima brecha GEIH si solo se cierra completo (pp) |
|:--|--:|--:|--:|
| Neutral | ~0 | ~0 | ~0 |
| Rural débil | 0,155 | 3,817 | 0,068 |
| Rural moderado | 0,696 | 8,937 | 0,139 |

El costo sustantivo de imponer el segundo margen supera considerablemente las brechas representadas iniciales. Por ello **ninguno de los priors heterogéneos conciliados debe promoverse a serie canónica**, aunque cumpla identidades. El cierre **solo completo** es una sensibilidad reproducible; su matriz alternativa para los dos escenarios rurales de 2001 en adelante se incluye expresamente (el neutral no cambia y antes de 2001 ambos enfoques coinciden).

## Archivos de salida

- `13_matriz_depto_sector_1993_2026_RECONCILIADA_EXPERIMENTAL.csv`: las 599.940 filas, composición, empleos en ambos universos y cambio respecto al prior.
- `13_matriz_alternativa_solo_cierre_completo_2001_2026.csv`: alternativa que NO obliga al cierre sectorial nacional GEIH, solo escenarios rurales de 2001 en adelante (los demás tramos coinciden).
- `13_auditoria_ajustes_y_convergencia.csv`: correcciones, convergencia, función objetivo, cierre por mes y escenario.
- `13_auditoria_margenes_nacionales.csv`: para cada sector/mes/escenario, restricciones, niveles y residuales.
- `13_auditoria_cierre_departamental.csv`: filas y universos por departamento.
- `13_sensibilidad_escenarios.csv`: totales del impacto por escenario.
- `13_comparacion_cierre_completo_vs_conjunto.csv`: compara el esfuerzo de cada estrategia y la discrepancia GEIH residual.
- `13_ajustes_mayores_puntuales.csv`: las 100 celdas con mayores cambios, unidas a nombre y ruralidad.
- `13_concentracion_ajustes_depto_sector.csv`: perfil de modificaciones en cada departamento y rama.
- `13_puerta_calidad.json`: estado, métricas y hashes SHA-256 de insumos.

## Cómo reproducir

Solo requiere Python + `numpy` + `pandas`:

```powershell
python h13_bundle_runner.py --inputs inputs --output outputs_reproducidos
```

Si se incorpora el parche a un checkout de ICML 2.2.18 ya actualizado a H12, también se añade el comando:

```powershell
icml sectoral reconcile-department-sectors --priors-csv inputs/12_candidatos_depto_sector_1993_2026_NO_CANONICOS.csv --national-csv inputs/12_composicion_nacional_unificada_1993_2026.csv --covariates-csv inputs/12_covalidadores_departamentales.csv --universe-csv inputs/12_auditoria_universos.csv --output outputs_reproducidos
```

El CLI ICML completo requiere las dependencias del proyecto, incluyendo `tempdisagg`; **no** se ejecutó ese CLI completo en este entorno. El runner aislado sí se ejecutó sobre las entradas reales. Las pruebas unitarias del solver también pasaron. El parche incremental actualiza `cli.py` y añade `sectoral_reconciliation.py` y sus pruebas; no restaura ni altera módulos del H11/H12.

## Puerta de publicación

**BLOQUEADA:** no existe validación empírica subnacional por sector ni identificación de sus distribuciones internas, y la sensibilidad al segundo margen representado es alta. Este Hito **cierra la conciliación contable** y documenta el impacto de los supuestos. No constituye certificación, serie oficial, ni autorización para reemplazar el ICML canónico.
