# ICML 2.2.18 — Hito 12: estimador previo de composición sectorial departamental

**Estado: EXPERIMENTAL, NO CANÓNICO. No hay estimaciones departamentales sectoriales observadas ni modelo entrenado con etiquetas en este paquete.**

## Qué se puede sustentar

- Panel laboral mensual 1993-01–2026-08, **33 territorios**, `insumos/laboral/departamentos.csv`.
- Participaciones nacionales: H11 homologación ENH (1993-01–2001-06, metodología `ENH_SEP_PRINCIPAL`); H11 inversión de ventanas móviles CIIU 3–4 (`FULL_2015_BRIDGE`, 2001-07–2014-12); DANE 13 grupos mensuales **2015-01–2026-08**.
- Demografía histórica del checkpoint: población por `Cabecera` y `Centros Poblados y Rural Disperso` para cada departamento-año. Es **población**, no empleo sectorial; se usa únicamente como covariable de composición condicional.
- **NO** existen etiquetas departamentales de empleo sectorial para entrenar ni validar contra la verdad del sector, por lo que las diferencias regionales son escenarios explícitos.

## Composición nacional temporal

Para 2015 en adelante, las 13 ramas publicadas del DANE se conservan como fuente de niveles por grupo; la rama combinada `B_D_E_COMBINED` se desagrega en `B` y `D_E` mediante la proporción inferida en H11, marzo 2015, **fija** para todos los meses recientes (proxy, no observación). La categoría `NO_INFO` se calcula a partir del total DANE y los 13 grupos; si las sumas redondeadas exceden el total por 1–2 personas, se normalizan participaciones con discrepancia auditada como redondeo, sin valores negativos.

**Los tres tramos se ensamblan sin superposiciones**: 1993–2001/06 (estimación ENH), 2001/07–2014/12 (estimación H11) y 2015/01–2026/08 (DANE 13 grupos publicados + supuesto B/D_E).

## Modelo territorial

Sea `q[s,t]` la participación nacional sectorial, `u[d,t]` la fracción rural de población departamental proveniente de la proyección y `ubar[t]` su media ponderada por **ocupados totales ICML de los departamentos**. Sea `alpha[s]` un vector de supuestos *declarados en el código*. El prior es:

`p[d,s,t | k] = q[s,t] * exp(k * alpha[s] * (u[d,t] - ubar[t])) / sum_j(q[j,t] * exp(k * alpha[j] * (u[d,t] - ubar[t])))`.

- `NEUTRAL_NATIONAL` (`k=0`): mismas participaciones nacionales en todos los departamentos (única base neutral sin supuestos espaciales externos).
- `RURAL_PROXY_WEAK` (`k=0.75`): perturbación espacial moderada hipotética.
- `RURAL_PROXY_MODERATE` (`k=1.5`): perturbación espacial más fuerte hipotética.

Los coeficientes y potencias son **supuestos**, no parámetros ajustados a información sectorial departamental. No se presentan como predicciones validadas. La composición se cierra por construcción en cada departamento-mes: `sum_s p[d,s,t] = 1`.

`ocupados_sector_completo[d,s,t] = p[d,s,t] * ocupados_completos[d,t]`.

`ocupados_sector_representado_proxy[d,s,t] = p[d,s,t] * ocupados_representados[d,t]`.

**Nunca** se usa la razón de poblaciones para expandir o contraer ocupados. Antes de 2001, los datos representados del panel departamental son **proxy no conciliado con el total nacional DANE**: no se afirma cierre GEIH de ese tramo. Para 2001+ el panel representado suma el DANE nacional del checkpoint.

## Límites y puerta

Este es **Hito 12** (generación y auditoría de prior territorial). La reconciliación simultánea a los márgenes *nacionales* de empleo por sector es **Hito 13**, NO se hace ni se oculta aquí. El archivo `12_brechas_margenes_nacionales_PRE_H13.csv` cuantifica esas desviaciones. Para Hito 13 se requerirá ajuste biproporcional / optimización bajo márgenes compatibles y preservación de los dos universos, sin forzar restricciones nacionales sobre un universo departamental no comparable en 1993–2000.

La precisión contable no es precisión sectorial. La puerta de publicación queda **bloqueada** por falta de etiquetas territoriales y validación fuera de muestra, además de la incertidumbre sectorial pre-2001.

## Archivos y reproducibilidad

Paquete **incremental**; no duplica el checkpoint integral 2.2.18. Incluye un parche sobre `root/` que conserva la CLI H11, módulo `sectoral_departmental_prior.py`, pruebas unitarias y los 7 insumos congelados, más los resultados calculados. Instalación en el entorno habitual ICML: copiar `patch/root/...` sobre el repositorio correspondiente; sin ello, también se puede ejecutar aislado:

`python h12_bundle_runner.py --inputs inputs --output outputs_reproducidos`

Con numpy y pandas instalados es suficiente para la ejecución aislada. Para usar la CLI completa `icml sectoral predict-departments`, se necesitan todas las dependencias de ICML, incluidas `tempdisagg==0.6.3`. El checkpoint no está modificado en origen.

## Archivos de auditoría

- `12_composicion_nacional_unificada_1993_2026.csv`: fuente nacional y estado de cada división.
- `12_covalidadores_departamentales.csv`: ocupados, fracción rural demográfica, referencia de universo.
- `12_candidatos_depto_sector_1993_2026_NO_CANONICOS.csv`: 3 escenarios × 404 meses × 33 departamentos × 15 sectores, con dos niveles laborales por fila.
- `12_auditoria_cierre_filas.csv`: márgenes departamento-mes en ambos universos.
- `12_auditoria_universos.csv`: sumas departamentales completas y representadas contra nacionales, con bandera antes de 2001.
- `12_brechas_margenes_nacionales_PRE_H13.csv`: brechas pendientes por sector-mes para Hito 13.
- `12_sensibilidad_escenarios_resumen.csv`: sensibilidad de brechas por intensidad asumida.
- `12_puerta_calidad.json`: métricas, parámetros fijados, estado bloqueado y SHA-256 de siete insumos.

## Números de la ejecución real

- 404 meses, 33 departamentos, 15 ramas, 3 escenarios, **599.940 filas**.
- Error máximo de cierre por departamento y universo **1,86 × 10⁻⁹ personas**.
- Desviación máxima de ocupados totales departamentales frente al total nacional ICML **6,71 × 10⁻⁸ personas**.
- **96 meses (1993–2000)** sin conciliación GEIH departamental-nacional (en el archivo de ocupados representados, los factores previos a 2001 son supuestos).
- Diferencia máxima sectorial nacional (como porcentaje de ocupados ICML): neutral ~0 pp; proxy débil **0,128 pp**; proxy moderado **0,504 pp**. Hito 13 deberá cerrarlas.
- 9 pruebas unitarias específicas aprobadas con fixtures sintéticos; ejecución del procedimiento real satisfactoria. La prueba de la CLI completa no pudo ejecutarse en este entorno por ausencia de `tempdisagg`; la ejecución directa del módulo sí se completó.
