# ICML H36 — Cierre reproducido con anexos de julio y agosto de 2026

**Corte del cálculo:** 2026-08. **Fecha de verificación:** 2026-11-02. **Base:** canónico H35 / `icml-colombia` 2.2.35.dev0.

## Resultados comprobados

1. GEIH Mercado Laboral de julio y agosto: ambos anexos validados a nivel de celda para dominios Nacional y 13 ciudades (niveles, tasas e identidades).
2. Empleo informal y seguridad social mayo–julio y junio–agosto: ambos anexos originales validados (cuatro hojas, período, mensual vs. trimestre móvil, seguridad social, identidades).
3. En GEIH, los datos del mes julio publicados dentro del XLSX de agosto coinciden en las nueve variables comprobadas y los dos dominios con el XLSX de julio: **cero revisiones encontradas**. No es prueba de ausencia de revisiones en otras hojas.
4. Los XLSX de agosto aportados son idénticos en SHA-256 a los XLSX ya presentes en H35; se preservaron sus bytes originales. Los XLSX de julio se archivaron en `insumos/fuentes/excel_originales/Mercado Laboral/Anteriores/`.
5. Ejecución completa `run-integral --mode recompute`: `RECOMPUTED_ALL_EIGHT_AUDITED`. Recalcula las 9 preparaciones Excel, ICML laboral, H5 nacional, H6 urbano, H9 departamental y H16 sectorial, y compara contra los 8 productos congelados. Los 8 productos son equivalentes dentro de tolerancias; ninguno fue promovido automáticamente ni reemplazó el congelado.
6. Auditoría cruzada de los ocho productos: `PASS`. Las series urbanas son señales no aditivas. Los dominios GEIH/representado difieren por definición; no se equiparan a la fuerza.
7. Pytest completo con 2 pruebas H36 nuevas: **406 passed, 131 skipped**. Las 131 Golden RC1 requieren entorno y referencias adicionales, NO se consideran pruebas aprobadas.
8. `tempdisagg` 0.6.3 se instaló desde el artefacto original de publicación de GitHub Actions (`release-dists`, ejecución 41164448787, ID 13028451969). SHA-256 de la rueda: `ae7593b90db9e32d9860d07b7be439490fb66fee61a0e0a7d53910ab12d68a29`.

## Importante: límites y estado científico

- **No son estadísticas oficiales.** No existe autorización de publicación. La auditoría numérica H9 es positiva, pero la **validación científica independiente H9 no está aprobada**. Persisten sensibilidad del período 2020, saltos urbanos y supuestos sobre dominios y definiciones.
- El cierre H36 corresponde a un **recálculo integral de la vintage agosto 2026**, no al entrenamiento de un modelo nuevo con parámetros libres. El puente CNPV y los *priors* MLP departamentales permanecen congelados para preservar comparabilidad; esto se registra en `informality_h5_h6`.
- No se ha demostrado que el motor actualice meses posteriores a agosto en forma arbitraria: hay ventanas de código/configuración fijadas en el corte. Un mes nuevo requiere adaptación y revisión expresa.
- Julio está documentado como fuente separada y es contrastado contra agosto; no se creó una *vintage* de modelos independiente terminada en julio. El modelo de agosto toma su secuencia histórica de las fuentes archivadas.
- El código de base continúa etiquetado `2.2.35.dev0`: el nombre H36 identifica la **entrega auditada**, no una versión nueva de software ni un cambio semántico del motor.

## Archivos entregados en cinco ZIP complementarios

Descomprimir los cinco ZIP **en la misma carpeta raíz**, conservando rutas relativas:

- `01_CODIGO_Y_FUENTES_H36.zip`: `ICML_H36/canonico/` con código, 4 fuentes julio/agosto, históricos y documentos de trabajo.
- `02_MODELOS_Y_REFERENCIAS_H36.zip`: resto de `ICML_H36/canonico/`, con validaciones previas, investigación, modelos y bases congeladas.
- `03_RECALCULO_LABORAL_H36.zip`: `ICML_H36/recalculo/` con ejecución laboral, preparación Excel y fuentes preparadas.
- `04_RECALCULO_INFORMALIDAD_SECTORIAL_H36.zip`: `ICML_H36/recalculo/` con reconstrucción H5/H6/H9, predictor y producto sectorial.
- `05_AUDITORIAS_Y_OCHO_PRODUCTOS_H36.zip`: `ICML_H36/evidencias/`, registros de prueba, resumen, manifest de integridad y copia de los ocho CSV para consulta directa.

La separación es solo **logística**: no deben confundirse las bases congeladas con las regeneradas. En todos los CSV, preservar los códigos de territorio como texto (ceros iniciales), la clave `national_type` y las definiciones de las tasas y los universos.

## Reproducir

Desde `ICML_H36/canonico/icml-colombia`, con un ambiente apropiado (versiones de dependencias fijadas en `pyproject.toml` y documentación del proyecto):

```bash
python -m pip install --no-deps ../../dependencias/tempdisagg-0.6.3-py3-none-any.whl
python -m pip install -e . --no-deps
python tools/release/audit_july_august_h36.py --root .. --output /ruta/auditoria_nueva
python -m icml operations run-integral --root .. --output /ruta/nueva_fuera_del_canonico --mode recompute
python -m pytest -q
```

La ejecución integral no escribe sobre el canónico y requiere un destino que no exista. El informe decisivo es `integral_execution_report.json`, con `status=RECOMPUTED_ALL_EIGHT_AUDITED`, `eight_product_equivalence_passed=true` y `candidate_cross_audit.status=PASS`.

## Manifiestos y trazabilidad

- `ICML_H36/evidencias/RESUMEN_H36.json` resume el resultado oficial de la ejecución.
- `ICML_H36/evidencias/H36_AUDITORIA_FUENTES_JULIO_AGOSTO.json` conserva las observaciones y hashes de las cuatro fuentes.
- `ICML_H36/evidencias/H36_ARCHIVOS_SHA256.csv` permite comprobar el contenido; `H36_PAQUETES_SHA256.json` se entrega como archivo adicional externo (evita un manifiesto autorreferencial en ZIP).
- La documentación previa H35 y el historial interno de ejecución se preservan sin eliminación ni sobreescritura.
