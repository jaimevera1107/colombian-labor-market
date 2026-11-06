# ICML 2.2.12.dev0 — Evaluación de transferencia de MLP único tras el ancla censal

**Estado:** EXPERIMENTAL. Ninguna base laboral/informalidad publicada fue modificada.

## Pregunta y diseño

Se evaluó si el ancla censal municipal CNPV-2018, incorporada en 2.2.11, modifica el entrenamiento y la transferencia de informalidad sobre los universos **ICML completo** y **GEIH representado**. Se preserva una sola arquitectura `MLPInformality` residual con pérdida beta; los modelos histórico T5 y reciente GEIH siguen separados únicamente porque sus **definiciones no son idénticas**. No se entrenaron dos modelos por universo.

**Hallazgo de identificabilidad:** el ancla afecta nueve capitales especiales (códigos [81, 85, 86, 88, 91, 94, 95, 97, 99]), pero ninguna proporciona etiquetas individuales entre las 23 ciudades con ventanas DANE utilizadas en el MLP. Por tanto el conjunto de entrenamiento de **3.588 observaciones T5 y 1.380 recientes permanece EXACTAMENTE igual**. Reentrenar con el mismo archivo, configuración, época elegida y semilla recuperó las mismas predicciones que los modelos 2.2.6: diferencia máxima **0** en ambas definiciones. No se presume una mejora fuera de muestra por cambiar una entrada exclusivamente de inferencia.

## Cambios censales reales

En 2018, las nueve cabeceras capitales suman **412,527 habitantes ajustados**, sobre **1,448,215** habitantes completos. El nacional ICML completo mantiene su población anterior; la población representada de todo el país cambia desde **47,241,101** hasta **47,226,233**, y los ocupados representados (estimados, no censados) desde **21,271,706** hasta **21,266,303**. Los multiplicadores censales ajustan la señal urbana de cada uno de los nueve departamentos, sin modificar ninguna de las seis magnitudes laborales departamentales completas.

**Advertencia:** el CNPV avala población, NO valida los niveles de ocupados, desempleados, PET, ni informalidad transferidos. El reescalamiento común de los componentes laborales representados preserva tasas por hipótesis, no observación del censo.

## Validación de tasas y cierre

Se generaron **392 meses modelables** (de 404; **2020 no tiene puente homogéneo**), 33 departamentos, dos versiones de la señal y tres políticas de cierre. El comparador produjo **71.280 registros**. Los resultados previos a la calibración cambiaron, en los nueve territorios, en **0,075 pp de media y 0,314 pp como máximo**. En los otros 24 territorios los predictores y las predicciones anteriores al cierre no cambiaron.

Tras aplicar el **cierre KL a ICML completo** (modelo rector), el cambio medio de tasa en los nueve territorios es **0.0614 pp** (máximo **0.3049 pp**); en los restantes 24 el cambio medio indirecto es **0.000684 pp**. Las dos identidades locales `informal+formal=employed` se cumplen exactamente por construcción; el residuo nacional ICML no supera **5.59e-09 personas**.

### Ensayo de direcciones con UN solo modelo

| Regla de cierre | Margen exacto por construcción | Desviación absoluta media del otro margen *hipotético* |
| --- | --- | ---: |
| `FULL_FIRST` | ICML completo | GEIH **0.188 pp** |
| `GEIH_FIRST` | GEIH representado | ICML completo **0.205 pp** |
| `DUAL_IDENTICAL_RATE_ASSUMPTION` | Ambos | 0 pp por construcción; **no evidencia predictiva externa** |

Los dos márgenes usan una misma tasa nacional reconstruida; imponer simultáneamente ambos puede provocar cambios de distribución territorial **sin constituir una segunda validación estadística**. Los errores del otro margen usan denominadores distintos; no se comparan como si fueran un MAE de prueba con etiquetas oficiales.

**Regla de transferencia:** una vez estimados los informales en el completo, `informales_GEIH = informales_completos × factor_geih_employed` y `formales_GEIH = formales_completos × factor_geih_employed` es una descomposición contable bajo la **hipótesis explícita de tasa homogénea entre dominio representado y complemento**. No es una identificación del verdadero diferencial de informalidad capital–resto. Una futura estimación necesita medir/modelar ese diferencial con fuentes comparables; no se suple entrenando una segunda red sobre el mismo objetivo.

**Fechas:** 1993–2000 usa proxy geográfico retrospectivo; 2001–2013 mantiene cero de GEIH para nueve capitales y NO puede invertirse por división; 2014–2026 utiliza las capitales representadas con ancla 2018. En todos los períodos el **complemento debe conservarse** para trasladar GEIH → completo. Los modelos de informalidad no tienen cierre validado en 2020.

## Selección y puerta

**Arquitectura recomendada para siguientes hitos:** un modelo de tasas sobre el universo geográfico completo, con ajuste censal para los predictores y transformaciones contables versionadas hacia GEIH. Esta elección se sustenta en la completitud del dominio y la identificabilidad del complemento, **no en una mejor precisión departamental demostrada**. El entrenamiento sigue usando 23 etiquetas urbanas latentes y su capacidad para generalizar a departamentos sigue sin evidencia independiente.

No se modifican los tres CSV congelados ni las publicaciones existentes. Se verificaron **13 archivos reproducibles por SHA-256** en dos corridas del experimento; las pruebas unitarias existentes y nuevas deben ejecutarse antes de promover el paquete.

### CLI de reproducción

```bash
icml informality census-transfer-mlp \
  --features-dir ../informalidad/consolidacion_v004 \
  --census-bridge ../censo/puente_v001/02_puente_dos_universos_33_territorios.csv \
  --census-anchors ../censo/puente_v001/01_ancla_cnpv_2018_nueve.csv \
  --model-dir ../informalidad/mlp_v005/models \
  --previous-predictions ../informalidad/mlp_v005/05_department_predictions_EXPERIMENTAL.csv \
  --national ../informalidad/secuencia_v003/02_nacionales.csv \
  --output ../informalidad/census_transfer_nueva_corrida
```

No sobrescribir una carpeta ya generada. Usar `--skip-refit` para comparar únicamente la transferencia con los mismos pesos (al no haber cambiado el entrenamiento produce iguales predicciones). No se generan etiquetas departamentales falsamente observadas.
