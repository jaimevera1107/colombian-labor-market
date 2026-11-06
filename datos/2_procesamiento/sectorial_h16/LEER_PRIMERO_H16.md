# ICML 2.5.0 — H16, predictor sectorial recuperado y matriz mensual conciliada

> Bundle regenerado en 2.5.0 a partir de la base laboral vigente (2.4.0 + factor GEIH recto por tramos), con la misma rutina que usa `icml rebuild`. Las cifras de desempeño cambian en la tercera cifra decimal respecto al bundle anterior (entrenado con la base laboral previa a 2.4.0).

**Estado: EXPERIMENTAL, NO CANÓNICO.** Implementación reproducible a partir del ICML 2.2.18/H11-H15 y del proyecto original del autor. No reemplaza datos históricos del ICML, no modifica los ZIP de origen ni constituye un anexo DANE oficial.

## Resultado

- **1993-01 a 2026-08:** 404 meses, 33 territorios y 15 categorías (`14 ramas + NO_INFO`). **199.980 filas** con empleo sectorial del universo completo y proxis del universo GEIH representado. Las 33 filas por rama de un mes se concilian a los márgenes nacionales de ocupación del universo completo H11 y cada departamento conserva su propio empleo. La misma composición territorial mensual se transfiere al universo representado, sin cerrar artificialmente los márgenes nacionales de ese otro universo.
- **Modelos 2015–2025:** recuperados los nombres exactos de las **38 variables** del notebook original; construidas sobre los estados laborales mensuales del ICML 2.2.18, más 16 variables del H15 (PIB rezagado y población). Se preserva la informalidad histórica del vintage del proyecto original como auxiliar, **no como actualización de la informalidad canónica**. Se evalúan Ridge con 38, Ridge con 37 sin código geográfico numérico y XGBoost de 14 salidas (un árbol por rama y ronda), contra Ridge del H15.
- **Ensamble:** ponderación seleccionada con las predicciones LOGO 2015–2024, nunca con las etiquetas de 2025. Después se ajustan estimadores con etiquetas 2015–2024 y se construyen candidatos anuales para 33 territorios 2015–2025.
- **Anclas sectoriales:** se preservan por separado las anuales GEIH de 23 departamentos 2015–2025 y de Bogotá 2015–2024. En la reconstrucción histórica se usan como **priors suaves**, no como cierres incompatibles contra el universo completo. Bogotá no entra en entrenamiento ni selección de modelos.
- **2001–2014 y 1993–2000:** no existen anclas sectoriales departamentales equivalentes; retropolación territorial condicional a la estructura de 2015 y las participaciones nacionales H11. Se utiliza atenuación de diferencias relativas al promedio nacional con semivida de 12 años, y se entrega sensibilidad de 6, 24 años y ausencia de atenuación. **Estas estructuras antiguas son supuestos**, no observaciones ni validaciones empíricas.
- **2026:** última referencia territorial anual disponible: 2025. Se combina su perfil con los márgenes nacionales mensuales H11 de enero–agosto de 2026. No hay PIB de 2025 como predictor temporal para 2026 en los insumos adjuntos.

## Evidencia de desempeño predictivo (fuera de muestra)

Todas las cifras son MAE de participación sectorial por celda, en puntos porcentuales, con **23 departamentos × 14 ramas × 10 años** en LOGO 2015–2024 y **23 × 14** en 2025. Se usa la misma muestra: LOGO no usa ninguna etiqueta del departamento excluido y 2025 no se utiliza en `fit` ni en selección de pesos.

| Modelo | LOGO 2015–2024 | 2025 reservado |
|---|---:|---:|
| Ridge del H15 con PIB rezagado | 1,2355 | 1,3702 |
| Ridge con 37 variables originales + PIB | 1,2421 | 1,3283 |
| Ridge con 38 variables originales + PIB | 1,2708 | 1,3613 |
| XGBoost 14 ramas y 38 variables + PIB | 1,2512 | 1,3081 |
| **Ensamble 50 % Ridge H15 / 50 % XGBoost 38** | **1,1598** | **1,2680** |

El ensamble usa ponderaciones de una malla preespecificada `{0, 0.25, 0.5, 0.75, 1}`, elegidas según el MAE LOGO 2015–2024. Esto **no es validación anidada de la selección de hiperparámetros** y el desempeño LOGO puede ser algo optimista por escoger la ponderación sobre esos mismos folds. El año 2025 sí queda separado de esa selección. Las variables macroeconómicas y de informalidad son vintages retrospectivos: esto tampoco es una simulación *as-of* de datos disponibles en tiempo real.

**Bogotá, importante:** antes de usar el Anuario como ancla histórica, el ensamble predice Bogotá 2015–2024 con MAE de aproximadamente **1,866 pp**; después de incorporar la referencia de Bogotá (2015–2024) y reconciliar H11, su error frente a esas mismas anclas cae a ~**0,092 pp**. La segunda cifra es **ajuste a datos históricos observados, no desempeño predictivo**. Para agricultura en Bogotá 2024 el valor conciliado es aproximadamente 0,395 % frente al 0,400 % de la referencia anual clasificada.

## Conciliación y evaluación

1. En cada mes: márgenes de filas = empleo ICML completo de cada departamento; márgenes de columnas = empleo completo nacional × participación H11 de cada rama. Convergencia por IPF/ajuste biproporcional, no negatividad y ceros nacionales estructurales. El empleo representado se calcula multiplicando las mismas participaciones por los ocupados representados **propios** de cada departamento.
2. Restricciones NO impuestas: la suma nacional GEIH representada contra DANE en 1993–2000, o la exactitud de los 24 conjuntos de anclas GEIH anuales frente a márgenes completos; son dominios de referencia parcialmente distintos y la igualdad puede ser imposible.
3. Auditoría de anclas: cotejo de participaciones anuales ponderadas con empleo representado de la matriz, antes de excluir `NO_INFO`. El denominador del contraste se restringe correctamente a las 14 actividades clasificadas.
4. H11: 1993–2014 reconstrucción nacional con supuestos; 2015–2026 conserva las 13 agrupaciones publicadas del DANE, con desdoblamiento `B/D_E` previamente identificado como supuesto. Las anomalías originales de `NO_INFO` y los supuestos de enlace no quedan resueltos por este paquete.
5. El algoritmo reporta correcciones mensuales de hasta ~5,72 pp respecto al prior, sobre todo en 2020. Estas modificaciones no son automáticamente errores: indican que la reconciliación es sustantiva y requiere revisión.
6. La sensibilidad de retropolación desde 2015 alcanza ~23,03 pp en una celda de enero 1993 al comparar la ausencia de atenuación con la semivida de 12 años; **no es un intervalo de confianza**.

## Relación con el notebook original

Se recupera la especificación **nominal** de 38 variables y la familia de 14 XGBoost, con correcciones verificables: los códigos territoriales no se usan como ordenaciones económicas sin comparar una ablación; se conserva la semántica real del último mapeo para Meta/Cesar que en el diccionario original estaba sobrescrito; el escalado e imputación se aprenden dentro de cada fold; las tasas de informalidad del vintage original se reescalan al empleo ICML vigente antes de usarlas como features, y **nunca se adoptan sus niveles**.

**No se afirma reproducir exactamente los 1000 árboles del artefacto `sector_model.joblib` ni el entrenamiento mensual antiguo.** El nuevo XGBoost usa 100 rondas de boosting con 14 salidas independientes, datos anuales agregados y un objetivo de comparación fuera de muestra. No se deserializa ningún joblib antiguo; se entrena desde fuentes CSV para evitar efectos de versión y problemas de seguridad. Las señales de ciudades de períodos móviles no se hacen pasar por observaciones mensuales ni se imputan hacia atrás como si fueran oficiales. Se conservan para análisis de evidencia separado del H4 y del original.

## Archivos importantes

`src/h16_integracion.py` contiene construcción de 38 características, LOGO, ensamble, anclas y reconciliación. `src/h15_predictor.py` y `src/hito4_reference.py` son dependencias de referencia del checkpoint H15.

- `outputs/16_metricas_predictor.csv`: resultados de validación 2015–2024 y 2025.
- `outputs/16_validacion_pareada_celdas.csv`: todas las comparaciones por celda para los cinco modelos.
- `outputs/16_original38_vs_37_logo.csv`: predicciones fuera de muestra de modelos nuevos.
- `outputs/16_candidatos_anuales_2015_2025.csv`: cuotas predichas, cuota observada diferenciada y prioridad suave para 2015–2025.
- `outputs/16_matriz_mensual_1993_2026_EXPERIMENTAL.csv`: 199.980 filas de sector×territorio×mes, dos universos como columnas, `NO_INFO` distinto, estatus de ancla por año.
- `outputs/16_auditoria_margenes_mensuales.csv`: cierres de filas, columnas, ajuste máximo mensual e iteraciones.
- `outputs/16_auditoria_anclas_GEIH_anuales.csv`: desviaciones frente a referencias por departamento, año y rama, **no fuera de muestra**.
- `outputs/16_bogota_evaluacion_independiente_PRE_ANCLA.csv`: predicciones externas de Bogotá antes de anclar.
- `outputs/16_sensibilidad_retropolacion.csv`: sensibilidades de semividas de 6, 12, 24 años y sin atenuación para años seleccionados.
- `outputs/16_puerta_calidad.json`: decisiones de método y fallos que impiden publicación.
- `outputs/16_manifest_hashes.json`: hashes SHA-256 de insumos y salidas.

## Reproducción

Python 3.11+ (recomendado 3.11/3.12) y dependencias disponibles:

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
python .\src\h16_integracion.py --root .
python -m pytest -q tests
```

El comando regenera los resultados de manera determinista con una misma versión de entorno y no escribe fuera de esta carpeta. Las etiquetas DANE originales, los checkpoints 2.2.18 y las series canónicas se mantienen intactos.

## Puerta de publicación: BLOQUEADA

El **componente funcional H16 sí está implementado** (predicción, validación anual, ensamble, mensualización con supuestos, reconciliación y auditoría). No sería científicamente correcto llamar "terminada y oficial" la reconstrucción sectorial territorial histórica. Las principales limitaciones son:

1. Cotejo documental directo de las extracciones sectoriales anuales con cada anexo DANE original y compatibilidad del universo/geografía.
2. Validación territorial independiente de los nueve departamentos sin ancla sectorial 2015–2024 y análisis de soporte de predictores.
3. Reconstrucción territorial 1993–2014 fuertemente dependiente de la semivida supuesta (solo el margen nacional está respaldado por H11 y sus propias limitaciones).
4. Asegurar corrección de vintages y disponibilidad de PIB, informalidad y demás covariables en cada fecha de actualización, especialmente para 2026 y posteriores.
5. Establecer protocolo de publicación frente a incompatibilidad de cuotas GEIH departamentales y márgenes del universo completo. La matriz entrega un candidato **reconciliado solo para el completo**, no un valor observado GEIH a escala departamental.
6. Evaluación temporal de innovaciones económicas, con tratamiento reforzado de 2020 y de cambios CIIU, y comparación con otros modelos posibles antes de producción.

El resultado actual es reproducible, tiene pruebas y permite trabajo posterior sin volver a construir la arquitectura. No se debe promover al conjunto canónico con solo ejecutar el código.
