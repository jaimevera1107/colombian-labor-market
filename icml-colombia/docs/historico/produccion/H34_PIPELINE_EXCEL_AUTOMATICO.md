# ICML 2.2.34.dev0 — H34: Excel → insumos → ejecución integral

**Corte congelado verificado:** agosto de 2026. **No es actualización a septiembre ni publicación de una nueva vintage.**

## Punto de entrada

Desde `icml-colombia`, con Python y las dependencias de producción instaladas:

```powershell
python -m icml operations run-integral --root .. --output ..\..\ejecucion_agosto_H34 --mode recompute
```

La nueva carpeta de salida debe estar fuera del checkpoint y no existir previamente. `run-integral --mode recompute` y `--mode recompute-components` llaman **obligatoriamente** al preparador `prepare-all-excel` antes de empezar a calcular. Si un original Excel, su hash, su estructura o su comparación con la referencia congelada no es válido, la corrida queda bloqueada. El modo `verify` continúa siendo auditoría de productos existentes, sin recálculo.

## Flujo implementado

1. Validar Excel contra el catálogo (`REGISTRO_EXCEL_ORIGINALES_H29.json`, el catálogo general y los manifiestos históricos).
2. Regenerar nueve derivados en `excel_preparation/h29` y `excel_preparation/h31` y comparar sus claves y valores con la referencia de agosto.
3. Construir `prepared_labor_sources/`: incluye once archivos declarados por el motor laboral. Seis son derivados verificados y el resto son fuentes auxiliares ya congeladas. La tabla de indicadores conserva las **seis columnas `*_spliced` solo por compatibilidad del esquema**, pero sustituye sus siete indicadores exógenos por los extraídos del Excel. Dichas seis columnas no son regresores ni nuevos insumos del ICML.
4. Las señales históricas y proxies urbanos se **regeneran y cotejan numéricamente**. Por requerir un hash congelado en los controles de donantes, el motor recibe para esas dos tablas la *serialización canónica original*, después de superar la comparación. Esto evita cambiar la elección Pareto por diferencias de redondeo o formato del CSV. El reporte expone ambas huellas.
5. Recalcular siete etapas laborales utilizando exclusivamente esta vista de fuentes.
6. Recalcular H9 desde los insumos censales e históricos seleccionados y las nuevas tres bases laborales. El CSV extraído de observaciones de informalidad se valida automáticamente desde Excel, **pero el ejecutor final de H9 no lo consume directamente**. No confundir validación de esa fuente con recálculo íntegro de sus etapas originales.
7. Construir la entrada de H16 a partir del conjunto de características congeladas y sustituir sus archivos de PIB y empleo sectorial por los dos CSV derivados verificados desde Excel. Se sustituye también `departamentos.csv` con la base laboral recién calculada.
8. Verificar las ocho bases con cierres cruzados, identidad de claves/categorías y tolerancias de comparación contra agosto de 2026. Ninguna base canónica se modifica ni se promueve automáticamente.

La ejecución registra `excel_preparation`, `prepared_labor_sources` y `prepared_sectoral_sources` en `integral_execution_report.json`, además de los manifiestos y hashes de cada insumo de la vista de trabajo.

## Limitaciones explícitas

- **Corte fijo:** la preparación conserva los formatos, hojas y rangos contrastados para agosto de 2026. No garantiza extracción automática de versiones futuras con estructura distinta.
- **Nuevo mes:** para pasar a un mes posterior, debe existir GEIH Mercado Laboral y Empleo Informal y Seguridad Social con **el mismo mes de cierre**. Este mecanismo de actualización se mantiene separado.
- **PIB:** es una covariable externa independiente; no puede derivarse de los anexos GEIH. El modelo H16 conserva el conjunto de variables y parámetros elegidos.
- **Donantes:** no se recalibra la decisión Pareto mensualmente.
- **RC1 Golden:** la certificación en el entorno numérico bloqueado de Python 3.12 no se reemplaza con una simple comparación de productos de agosto.

## Control de fallos

El checkpoint es solo lectura en el flujo. Se rechaza una carpeta de salida existente. Una etapa que falle deja evidencia y un informe `RECOMPUTATION_FAILED_NOT_PUBLISHED`, nunca una vintage parcialmente promovida.
