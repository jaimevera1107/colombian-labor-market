# ICML 2.2.6.dev0 — Hito 8: MLP de informalidad (experimental)

**Estado: NO CERTIFICADO; NO PUBLICAR.** Esta fase no modifica ninguna de las tres bases laborales, no modifica las 33 señales de informalidad del Hito 6, no recalcula los dos nacionales y **no habilita** el cierre de informalidad departamental. La evidencia se encuentra en `informalidad/mlp_v005/`.

## 1. Lectura fiel de la arquitectura original

Referencia: notebook `2 - Estimación Departamental.ipynb`, celdas 157, 159, 161 y archivo `models/mlp_config.json` de `Indicadores Mercado Laboral(1).zip`. Se preservan las fuentes de código neuronal y configuración originales en `docs/informality/reference/` solo para auditoría, **no ejecutadas**.

- MLP `Linear -> ReLU -> Dropout -> ResidualBlock(s) -> Linear(1) -> sigmoid`.
- Cada `ResidualBlock`: `LayerNorm -> Linear -> Dropout -> ReLU -> sumatoria con la entrada`.
- Tres pérdidas candidatas en el notebook: `logit_huber`, `logit_mse`, `beta_nll`. La tasa se representa en [0,1].
- StandardScaler, MinMaxScaler y RobustScaler como alternativas; archivo original selecciona StandardScaler.
- Búsqueda externa de hiperparámetros orientada al **percentil 90 de MAPE medio por ciudad**, no solo al RMSE global. La búsqueda original estratifica aleatoriamente dentro de cada año y no garantiza exclusión geográfica.
- Configuración guardada: `hidden_dim=128`, `num_blocks=1`, `dropout=0.1`, `use_residual=true`, `loss_type=beta_nll`, `beta_phi=20`, `epochs=500`, `batch_size=512`, `lr=0.001`, `weight_decay=0.001`, `patience=20`, `early_metric=mape_p90`, `monotonic_type=none`.

### Dos errores operativos del notebook original

**Beta:** calculaba `log_beta_ab = lgamma(a)+lgamma(b)-lgamma(a+b)` pero **no lo incluía en la función objetivo**. La pérdida antigua no era la log-verosimilitud beta completa. La implementación nueva incluye la normalización y comprueba su valor contra `scipy.stats.beta`. Esta corrección cambia las estimaciones respecto al entrenamiento original.

**Parada anticipada:** `fit()` no utilizaba la validación temporal ni `patience`/`early_metric`; recorría todas las épocas. Ahora se usa un subconjunto **interno** de entrenamiento para seleccionar la época por P90 MAPE, sin consultar la partición geográfica-temporal externa. Posteriormente se reentrena el modelo con la partición exterior completa durante el número de épocas elegido.

Las variantes originales de monotonicidad no garantizan matemáticamente monotonía de la función final: incluyen normalización/una cabeza lineal no restringida. No se ofrecen como garantía en la ruta nueva, y la configuración efectiva original no las utilizaba.

## 2. Diferencia frente a entrenamiento original

El modelo actual conserva la **arquitectura efectiva**, pero no pretende equivalencia byte-a-byte con los pesos originales: utiliza las 92 características del Hito 7 (no las aproximadamente 52 de la configuración original), corrige la pérdida beta, aplica parada real, usa restricciones geográfico-temporales y no mezcla definiciones T5 y GEIH. El entorno de esta ejecución (PyTorch CPU 2.10.0, numpy 2.3.5, pandas 2.2.3, scikit-learn 1.8.0) tampoco coincide enteramente con el entorno congelado de producción; es un experimento reproducible **dentro del entorno usado**, no una nueva certificación golden.

Se conservan la semilla, el orden exacto de características, el StandardScaler ajustado **solo con entrenamiento**, los pesos `state_dict`, los parámetros, la selección de épocas y los hashes de entradas.

## 3. Definiciones y validación

- **OLD_T5_LATENT**: entrenamiento de 2007–2019, excluyendo 2020; cinco pliegues `G1..G5_T2016_2019`. Entrena con ciudades disponibles hasta 2015 y evalúa ciudades reservadas en 2017–2019, con cuarentena temporal.
- **NEW_GEIH_LATENT**: cinco pliegues `G1..G5_T2022_2025`. La condición temporal del Hito 7 solo expone **2021** como entrenamiento con definición reciente y evalúa ciudades excluidas en 2023–2025. Esto es más estricto que un ajuste aleatorio retrospectivo, pero permite poco entrenamiento de la definición nueva.
- Se descartan cinco pliegues `T2019_2022` para aprendizaje supervisado dentro de definición, pues entrenar la tasa antigua como si fuera la tasa nueva incumpliría el puente metodológico.
- Las etiquetas siguen siendo **mensualidades latentes reconstruidas** de ventanas DANE, no observaciones mensuales oficiales. Las cantidades de datos no son equivalentes a observaciones independientes.
- Es validación retrospectiva: algunas covariables ya estaban reconstruidas con vintages posteriores, por lo que no demuestra capacidad predictiva histórica en tiempo real.

Comparación de diez pliegues (MAE en puntos porcentuales, promedio sin ponderar entre pliegues):

| Modelo | T5 2007–2019 | GEIH 2023–2025 |
|:---|---:|---:|
| MLP residual `beta_nll` corregida | **5.51** | 11.41 |
| MLP residual `logit_huber` | 5.78 | 12.42 |
| Regresión Ridge | 9.47 | 10.72 |
| Media de ciudades de entrenamiento | 8.70 | **9.64** |

En el tramo antiguo la arquitectura neuronal reduce el error frente a Ridge y la media. En el reciente no mejora la referencia ingenua de la muestra de entrenamiento. No debe adoptarse el segundo modelo solo porque minimiza la pérdida interna.

Ablación **solo de un pliegue histórico** `G1_T2016_2019`: residual MAE 8.39 pp y P90 MAPE 25.73%; sin residual MAE 9.35 pp y P90 MAPE 23.90%. No constituye prueba universal de superioridad de la conexión residual.

## 4. Puerta de transferencia ciudad → departamento

El ajuste urbano NO valida por sí solo la predicción departamental. La comparación directa de las predicciones experimentales de 33 departamentos con el nacional **ICML_COMPLETO** revela una brecha media, definida como nacional modelado menos nacional ICML reconstruido:

| Tramo | Brecha media |
|---|---:|
| 1993–2000 | −15.33 pp |
| 2001–2006 | −19.69 pp |
| 2007–2019 | −16.13 pp |
| 2021–2026 | −13.20 pp |

Máximo absoluto: **21.37 pp** en mayo de 2002. Por ello **no se ejecutó una calibración nacional para borrar esta divergencia**.

La distancia entre covariables urbanas de entrenamiento y departamentales de inferencia es grande. El 7.79% (antigua) y el 10.01% (nueva) de las celdas estandarizadas del panel departamental se sitúan por encima de |z|=4 usando únicamente el escalador de las ciudades del entrenamiento. La proporción de filas con al menos un extremo es casi 100% en 92 variables; esa medida a nivel de fila debe interpretarse con cautela por dimensionalidad elevada.

Las diferencias de universo ciudad/departamento son estructurales, especialmente para ruralidad. **Ni el cierre contable ni la suma nacional demuestran validez de la tasa de un departamento**. Actualmente no hay objetivo oficial departamental compatible para validar los diez territorios faltantes, por lo que no se inventa.

## 5. Qué se guarda y qué NO se publica

Se guardan dos entrenamientos completos diferenciados por definición, pesos, escaladores, configuración, predicciones departamentales duales y archivos de evaluación. Para 2020 se retienen las tasas independientes de ambas redes **solo para diagnóstico**, pero las columnas de serie provisional final se dejan deliberadamente sin selección: falta validar el puente de definiciones. Los seis niveles de mercado laboral siguen completos y fijos; la base formal/informal publicada **no** se genera aquí.

- `05_urban_cross_validation.csv`, `05_cv_summary.csv`, `05_heldout_urban_predictions.csv`: evidencia supervisada urbana.
- `05_ablation_residual_one_fold.csv`: un solo experimento controlado de arquitectura.
- `05_department_predictions_EXPERIMENTAL.csv`: **no canónico**, 33×404 pares departamento-mes.
- `05_national_gap_diagnostic.csv`, `05_transfer_feature_drift.csv`, `05_monthly_change_flags.csv`, `05_mlp_quality_gate.csv`: auditorías.
- `models/OLD_T5_LATENT/`, `models/NEW_GEIH_LATENT/`: pesos `state_dict` y escaladores guardados sin pickle de objetos arbitrarios.

### Puerta final

**NO CERTIFICADO**. Requisitos pendientes: verificar/decidir puente de definiciones (especialmente 2020), justificar transferencia urbana–departamental, superar una línea base aplicable después del cierre, limitar el desplazamiento necesario frente al nacional y probar evaluación después del cierre (G6). No se proponen datos departamentales inexistentes como condición de avance.

Comando independiente (no modifica `icml run`):

```bash
icml informality fit-mlp \
  --features-folder informalidad/consolidacion_v004 \
  --output informalidad/mlp_NUEVO_VINTAGE \
  --epochs 110 --folds-per-definition 5
```

El comando aplica los datos de entrada y es computacionalmente exigente. La ruta atómica conserva un directorio `._in_progress` en caso de interrupción para evitar anunciar un vintage incompleto. Un segundo comando, `icml informality audit-mlp`, genera la puerta postentrenamiento contra un nacional externo. Un `exit status=2` en esa auditoría señala intencionalmente **que no está certificado**.
