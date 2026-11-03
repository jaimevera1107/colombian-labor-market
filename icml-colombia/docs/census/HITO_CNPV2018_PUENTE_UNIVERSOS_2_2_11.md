# Hito de escala censal y transferencia entre universos — ICML 2.2.11.dev0

**Estado:** etapa de pipeline y auditoría reproducible implementadas; **candidatos de sustitución de datos NO canónicos**. No reestimó empleo ni informalidad y las tres bases laborales 2.1.2 siguen congeladas.

## Decisión sobre el universo de modelado

**Elegir como universo rector el departamento completo del ICML.** Motivos:

1. La población departamental ya reproduce exactamente los 9 totales ajustados CNPV 2018, y el total país difiere apenas 3.427 personas (+0,007 %) en el promedio mensual de 2018. Cambiarla para «hacer que coincida» con GEIH sería confundir universos.
2. En 2001–2013, nueve capitales tenían factor cero en el agregado nacional GEIH del proyecto. Partiendo *solo* del universo GEIH es matemáticamente imposible recuperar el resto departamental con una división por el factor. Hay información faltante, no un problema de precisión numérica.
3. En 1993–2000, el agregado DANE_REFERENCIA previo era una **reconstrucción no oficial**, y sus factores igual a 1 eran una convención. Se creó un proxy geográfico de cabeceras capitales para que el dominio retrospectivo tenga sentido, manteniendo su carácter inferido.
4. Los departamentos completos permiten un único modelo territorial de mercado laboral. El modelo de informalidad puede consumir **los mismos niveles de ocupados y la misma geografía completa**, sin entrenar dos sistemas independientes. Para representar GEIH se proyectan **cantidades** por componente y después se calculan las tasas, no al revés.

**Advertencia:** esto es una **decisión arquitectónica**, no evidencia de superioridad predictiva de un modelo todavía no reentrenado. El benchmark presente es interno, porque ambas caras usan datos reconstruidos del mismo pipeline.

## Procedimiento

1. Leer `.xls` oficial y extraer por código DIVIPOLA las cabeceras *de municipio capital*, no municipios capitales enteros: `scripts/census/extract_capitals_2018.py`.
2. Comprobar para los nueve departamentos que la población ICML completa media de 2018 coincide con el total censal ajustado. **No escalar de nuevo el universo completo**: ya está anclado a las proyecciones censales.
3. Obtener para cada capital `k_geih = CNPV_cabecera_capital / GEIH_representado_2018_ICML`, y `k_urbano = CNPV_cabecera_capital / señal_urbana_2018`. Guardar los nueve coeficientes y el SHA del XLS.
4. Para 1993–2026 producir una señal geográfica capital-resto, con trayectoria heredada de la ciudad y nivel recalibrado en 2018. Se conserva todo el complemento departamental, incluso para las capitales no incluidas en GEIH en fechas tempranas.
5. Para 2014–2026, recalibrar las seis cantidades representadas a nivel 2018 multiplicando cada uno de los *componentes representados heredados* por **un mismo k_demográfico**, lo que conserva las tasas laborales ya reconstruidas en la capital. 2001–2013 mantienen cero participación en el nacional GEIH para esos territorios, por alcance del proyecto.
6. Para 1993–2000, usar señal capital retrospectiva como **proxy GEIH reconstruido, nunca observación**. En ambos lados retener `full = GEIH + complemento`, siempre exacto. Para convertir en sentido inverso, se requiere el **complemento**: dividir por un factor sin él es inválido.
7. Calcular y auditar agregados por universo y por mes, sin sobreescribir `insumos/laboral` ni `quality/products`.

No todas las tasas urbanas pueden asumirse iguales a las departamentales; el benchmark por simple fracción poblacional mide precisamente el efecto de imponer esa igualdad. La transferencia de informalidad necesitará su propio factor de cobertura del empleo informal o una hipótesis explícita de tasas condicionales, que NO equivale a un factor de población.

## Ancla de 2018

| Medición | Personas |
|---|---:|
| CNPV ajustado, nueve departamentos completos | 1.448.215 |
| CNPV ajustado, nueve cabeceras capitales | 412.527 |
| ICML anterior representado (2018) | 427.396 |
| ICML anclado representado (2018) | 412.527 |
| Diferencia del representado frente al anterior | −14.869 |
| CNPV ajustado, fuera de las nueve cabeceras | 1.035.688 |
| Nacional GEIH geográfico censal aproximado 2018 | 47.222.806 |
| Nacional ICML representado **después** del ancla (promedio 2018) | 47.226.233 |
| Diferencia del puente frente al geográfico censal aproximado | +3.427 |

**No confundir:** 47.226.233 es una estimación del **ICML**, no un total GEIH directamente publicado por el DANE. Su diferencia frente a 47.222.806 proviene de la diferencia de fecha/promedio del universo completo (3.427), no de una población creada/omitida por el puente.

Los nueve multiplicadores de nivel representado para 2018 van aproximadamente de **0,9161 (Arauca)** a **1,1013 (Guaviare)**. No se debe aplicar un multiplicador nacional único.

## Benchmark de dirección y límites de identificación

El ensayo de 2014–2026 compara dos transportes ingenuos de tasas laborales:

- **Completo → GEIH:** nivel departamental completo multiplicado por fracción de población cubierta.
- **GEIH → completo:** nivel de la parte cubierta dividido por la fracción de población cubierta, suponiendo mismas tasas del resto.

Se evalúan ambos contra los dos **componentes previamente reconstruidos**, por lo que los porcentajes son **consistencia interna**, no errores predictivos externos. Los denominadores de error difieren: **no** comparar el WAPE de direcciones distintas como si fueran una validación causal o un ranking científico. El resultado relevante es la asimetría de identificación: hacia abajo hay un subconjunto conocido y hacia arriba hace falta modelar el complemento.

La tabla `04_comparacion_direccion_transferencia.csv` incluye las 33 entidades y, por separado, los nueve departamentos especiales. Para estos últimos, suponer uniformidad de tasas entre capital y resto produce discrepancias considerables, en especial en desempleo; **por eso la transferencia final no puede usar únicamente el coeficiente poblacional para todas las cantidades**.

## Restricciones, referencias y puerta de calidad

- Las seis cantidades de `ICML_COMPLETO` quedan intactas, en las 33 entidades y los 404 meses.
- En la salida alternativa `geih_*`, `labor_force=employed+unemployed`, `working_age=labor_force+inactive`, `0≤geih_q≤full_q`; todo `full_q=geih_q+outside_geih_q`.
- El agregado nacional `DANE_REFERENCIA` antiguo **se conserva separado**: bajo el nuevo ancla, el agregado representado para 2018 disminuye unas 14.869 personas. Si se exigiese mantener simultáneamente el agregado antiguo exacto, con las nueve cabeceras exactamente censales y los 24 territorios restantes con factor 1, el sistema de restricciones sería incompatible sin una reasignación identificable. No se impuso un cierre artificial.
- Para publicar un nuevo nacional GEIH es necesario revisar referencias oficiales comparables, su fecha y sus dominios, y decidir explícitamente si se ajustan las anclas o si se usa una reconciliación con holguras documentadas.
- **La concordancia censal solo certifica escala de población**. No certifica PET, empleo, desempleo, informalidad, ni escenarios anteriores/posteriores a 2018.
- **2014 como inicio del dominio GEIH en el proyecto:** el DANE describe recolección para las ocho capitales a partir de finales de 2012 e inclusión en los empalmes GEIH desde 2014. Se preserva el corte elegido en el modelo, no se declara que antes de 2014 no existan microdatos.
- CNPV es un nivel 2018: el coeficiente de 2018 se mantiene como **hipótesis de nivel** para 1993–2026. La calidad de la evolución temporal se comprobará con futuras anclas y vintages; no hay observación censal mensual fuera de 2018.

## Entradas, salida y reproducción

Fuente primaria: `insumos/censo_original/CNPV-2018-Poblacion-Ajustada-por-Cobertura.xls`, y sus 9 anclas extraídas con script. Los insumos laborales se toman sin modificaciones de `insumos/laboral` (2.1.2). El nuevo comando tiene manifest compatible con `StageResult` y existe también la opción `icml run --census-source ...` para ejecutar la etapa opcional inmediatamente después de `quality`.

```sh
python scripts/census/extract_capitals_2018.py \
    ../insumos/censo_original/CNPV-2018-Poblacion-Ajustada-por-Cobertura.xls \
    ../insumos/cnpv_2018_capitales_ajustado.csv

icml census-bridge run \
    --departments ../insumos/laboral/departamentos.csv \
    --cities ../insumos/laboral/ciudades.csv \
    --nationals ../insumos/laboral/nacionales.csv \
    --census ../insumos/cnpv_2018_capitales_ajustado.csv \
    --output ../censo/puente_v001
```

Etapa registrada en `STAGES`, posterior a `quality`:

```sh
icml census_bridge run \
    --config configs/rc1/census_bridge.toml \
    --sources ../insumos_censo \
    --quality-run <ruta-de-quality-completo-con-manifest> \
    --runs-dir runs --run-id cnpv2018-v001
```

**No se han reentrenado los modelos laborales ni el MLP informal**. Este checkpoint valida la escala demográfica y el traspaso contable, sin autorizar sustituir series publicadas. Antes de entrenar de nuevo, las características y la conciliación deben consumir esta versión única del puente, con sus referencias y puertas de calidad.

## Referencias oficiales

- DANE CNPV 2018, ajuste por cobertura: https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/censo-nacional-de-poblacion-y-vivenda-2018/informacion-tecnica
- GEIH 2014, empalme e inclusión de nuevas capitales: https://microdatos.dane.gov.co/index.php/catalog/756/data-dictionary
- GEIH 2010, empalme y alcance: https://microdatos.dane.gov.co/catalog/765
