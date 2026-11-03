# Arquitectura operativa ICML H20

## Separación de responsabilidades

- `icml-colombia/src/icml/`: código fuente instalable y CLI. Única fuente de verdad para la lógica de actualización.
- `icml-colombia/configs/` y `requirements/`: parámetros y referencias de dependencias; usar Python 3.12 con el lock.
- `insumos/`, `censo/` y `sectorial/`: fuentes e insumos auxiliares heredados; NO modificar in situ.
- `_test_quality_run/products/`: las tres bases laborales congeladas, con rutas conservadas para preflight H19.
- `informalidad/cierre_integral_v013/`: último cierre de informalidad, experimental no oficial.
- `research/sectoral/h16/`: modelo H16 reproducible y sus auditorías, congelado.
- `CIERRE_MODELO/PRODUCTOS/`: exportaciones sectoriales seleccionadas H18.
- `CIERRE_OPERATIVO_H19/`: evidencia de integridad y ensayos de actualización.
- `ENTREGA_H20/`: manifiestos de integridad, catálogos, guías y evidencia de puertas.

Los prototipos H12/H13, resultados de investigaciones anteriores y ejecuciones temporales no son dependencias del producto actual: permanecen en el checkpoint histórico H19 externo, no en esta distribución activa.

## Flujo mensual

1. Descargar anexo oficial y documentar URL, fecha, hash, cobertura y cambios de esquema.
2. Correr el pipeline en un directorio nuevo inmutable, sin editar fuentes ni vintages publicados.
3. Ejecutar controles laborables, conciliación, informalidad y sectorial (cuando corresponda).
4. Ejecutar `stage-update` sobre el candidato calculado, con `revision_state` válido en el anterior.
5. Generar informe diferencial: celdas nuevas, revisadas y protegidas.
6. Revisar y autorizar humanamente la publicación; `freeze-products` no es un sistema de publicación oficial.

## Reglas de versión

- Corrección de errores: incrementar versión del software y añadir regresión; no cambiar datos congelados en silencio.
- Actualización ordinaria: crear vintage nueva, añadir mes y respetar ventana revisable.
- Revisión DANE: nuevo vintage trazado con causa documental y diferencia de históricos.
- Cambio metodológico: nueva versión del método; no mezclar con actualización ordinaria.
- H16 50/50 Ridge+XGBoost queda congelado. Sólo cambiar con nueva evidencia o defecto reproducible autorizado.
