# ICML 2.2.4.dev0 — Informalidad secuencial DANE (candidato)

**Estado: experimental / publicación bloqueada.** Fecha 2026-11-01. Referencia: Bloque II de la hoja de ruta v3.0 y cadena de informalidad del notebook original `2 - Estimación Departamental.ipynb`. Se continúa sobre la puerta metodológica 2.2.3, SIN modificar las tres bases laborales canónicas 2.1.2 ni los candidatos previos.

## Por qué se rehace la cadena

2.2.2 producía las 33 señales en un solo proceso y derivaba el nacional a continuación. El notebook original distinguía un primer empalme urbano, la reconstrucción nacional y **una segunda extensión de ciudades con el nacional** (`SplicingInformalityCities`). Esta versión materializa explícitamente las dependencias, sin declarar que las fórmulas alternativas reproducen numéricamente el notebook original.

| Etapa | Salida | Cobertura / prueba |
|---|---|---|
| 1. Trece áreas | `01_ciudades_13.csv` | 13×404 = 5.252; tasas T5 históricas y GEIH nueva; sin datos mensuales oficiales inventados |
| 1. Evidencia | `01_anclas_agregado_13.csv`, `01_validacion_13_anio_excluido.csv`, `01_ventanas_13.csv` | Seis anclas *agregadas* T5 2001–2006; su validación LOYO MAE **0,458 pp**. Las cifras individuales T10 2005–2006 no son anclas T5 |
| 2. Nacional | `02_nacionales.csv`, `02_senal_agregada_13.csv` | 2×404 = 808; DANE_REFERENCIA e ICML_COMPLETO, ocupados fijos. Candidato de puente entre definiciones; ambos usan **la misma tasa por hipótesis**, no por evidencia de igualdad |
| 3. Veintitrés | `03_ciudades_23.csv` | 23×404 = 9.292. Conserva las primeras 13; diez adicionales se extienden antes de 2007 con cambios de la tasa nacional reconstruida (logit) y una señal laboral auxiliar |
| 3. Otras diez señales | `03_ciudades_33.csv`, `03_catalogo_retro_y_donantes.csv` | 33×404 = 13.332; donantes identificados, incluida señal sintética de Cundinamarca. No convertir en observación territorial |
| 4. Matriz | `04_entrenamiento_23_ciudades_etiquetas_latentes.csv`, `04_inferencia_33_departamentos_sin_etiquetas.csv` | **5.244** filas de entrenamiento de ciudad 2007–2025 (no observaciones mensuales independientes) y **13.332** filas de inferencia departamental sin etiquetas de informalidad observada |
| 4. Línea base | `04_baseline_transferencia_urbana_no_calibrada.csv` | Tasas urbanas transferidas como referencia **NO** resultado departamental certificado |
| 5. Contrafactual de cierre | `05_calibracion_dual_contrafactual_no_canonica.csv` | Logits calibrados a las dos tasas nacionales supuestas; ocupados departamentales invariables. **NO** es una predicción validada ni evidencia de igualdad de universos |

## Decisiones científicas

1. Tres objetos distintos: (a) tasa publicada en un trimestre móvil de un dominio DANE, (b) mensualidad latente inferida, (c) cifra departamental predicha. No etiquetar (b) o (c) como observaciones mensuales.
2. Para 2001–2006 existen referencias T5 de las **trece áreas agregadas**, no 13 etiquetas T5 individuales. Se calibra el promedio ponderado de las ciudades con su empleo urbano ICML y se etiqueta esa aproximación de dominio como tal; las cifras individuales T10 son contrastes de **otra definición**.
3. Antes de 2001 se retropola con señales laborales. La ausencia de anclas ENH individuales recuperadas no autoriza declarar precisión histórica conocida.
4. El nacional posterior a la reconstrucción de 13 áreas usa la serie agregada de DANE y el indicador nacional histórico de no afiliación a pensión solo como *señal diferencial*, sin equivalencia de definiciones.
5. Las 10 ciudades adicionales de las 23 se retropolan **después** de disponer del nacional y no vuelven a modificar las 13 anteriores.
6. Las otras 10 señales urbanas son donadas y no se consideran una segunda observación de informalidad municipal.
7. En el panel de entrenamiento solo hay **objetivos latentes de ciudades**. `target_latent_informal_rate` en departamentos queda vacío por diseño (no se fabrican etiquetas observadas); las seis variables del mercado laboral congelado siguen completas.
8. `cluster_descriptive_2007_2019` utiliza solamente información laboral urbana de 2007–2019 y no informalidad; **no es válido como predictor en validación LOGO sin volver a ajustar clústeres y escaladores en cada fold**.
9. El nacional `DANE_REFERENCIA` anterior a 2001 sigue siendo *referencia histórica reconstruida*, no ancla mensual oficial. Los factores iguales a uno en ese tramo mantienen la totalidad de la historia ICML, sin imponer falsa igualdad de agregados.

## Auditoría ejecutada

- **21 CSV** reproducidos byte por byte en dos corridas completas con los mismos insumos, configuraciones y dependencias locales.
- **191 pruebas unitarias superadas y 6 omitidas**; no se afirma equivalencia de toda la batería de regresiones históricas.
- Tres bases laborales de entrada conservadas por SHA-256.
- Ausencia de nulos en cantidades informales/formales reconstruidas; tasas dentro del intervalo [0, 1]. Identidades formales + informales = ocupados fijos.
- **328 alertas temporales** de tasas, **32 candidatos de quiebre**, **0 alertas de variación extrema de informales superior a 200%** según el criterio de puerta anterior. Son indicadores de revisión, no fallas estadísticas causales demostradas.
- Comparación con 2.2.2: las 13 ciudades y las dos series nacionales son numéricamente equivalentes dentro del redondeo; la nueva retropolación de las ciudades restantes introduce una diferencia máxima de **3,287 pp**.
- La transferencia urbana sin calibrar deja un agregado nacional entre **8,84 y 13,50 pp por debajo** del nacional reconstruido. Una calibración doble contrafactual puede cerrar exactamente las tasas asumidas para ambos universos sin alterar ocupados, pero requiere cambios de hasta **15,025 pp** en una celda, con intervención absoluta media mensual de **9,708 pp** entre territorios. Este volumen **bloquea** su publicación como estimación departamental.

## Alcance del método original que NO se ha ejecutado en esta versión

- El entrenamiento nuevo de `MLPInformality` y evaluación frente a la señal urbana en LOGO territorial con transformaciones *fold-safe*.
- Evaluación fuera de muestra **después** del cierre, con criterio de mejora frente a transferencia directa.
- Un puente empíricamente verificado entre la informalidad nacional del universo urbano y la del universo departamental completo.
- Un producto departamental informal definitivo de 33×404. La tabla contrafactual no sustituye esa fase.

## Próxima puerta

1. Resolver las mensualidades latentes excesivamente oscilantes mediante regularización validada contra ventanas retenidas, sin cambiar las publicaciones DANE.
2. Entrenar MLP original y alternativas sencillas usando `04_entrenamiento_23_ciudades_etiquetas_latentes.csv`, **reajustando clústeres y estandarizadores dentro de cada fold**. Tratar las mensualidades latentes como etiquetas débiles, no independientes.
3. Predecir en `04_inferencia_33_departamentos_sin_etiquetas.csv` y medir la intervención de la conciliación final frente a ambos agregados con el mismo protocolo para todos los modelos.
4. Promover únicamente si disminuye el error fuera de muestra y el cierre no exige correcciones desproporcionadas. Nunca modificar las seis cantidades laborales.

## Reproducción (desde raíz de paquete)

```bash
icml informality sequential \
  --config configs/rc1/informality_sequential.toml \
  --sources RUTA/insumos/informalidad/informality_source_observations.csv \
  --cities RUTA/insumos/laboral/ciudades.csv \
  --departments RUTA/insumos/laboral/departamentos.csv \
  --nationals RUTA/insumos/laboral/nacionales.csv \
  --recent RUTA/insumos/informalidad/national_informality_monthly_2021_2026.csv \
  --anchors13 RUTA/insumos/anclas_dane/anclas_dane_agregado_13_areas_2001_2009.csv \
  --output RUTA/nuevo_vintage
```

`--output` debe estar vacío. La política de parámetros y su hash están registrados en el manifiesto; cambiar un parámetro implica otro vintage. `icml run` continúa siendo la cadena laboral previa y no ejecuta esta prueba de informalidad por defecto.
