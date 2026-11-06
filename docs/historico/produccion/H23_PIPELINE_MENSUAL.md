# ICML — Hito 23: orquestación mensual controlada

**Versión de software:** `2.2.25.dev0`. **Último corte congelado:** `2026-08`.
**Estado:** recepción y preflight implementados y probados; ejecución mensual integral nueva **BLOQUEADA** hasta completar validadores/adaptadores y disponer de ambos anexos del DANE.

## Contrato de actualización innegociable

Para cada mes objetivo `M` se requieren simultáneamente:

1. GEIH Mercado Laboral, período **M**.
2. Empleo Informal y Seguridad Social, trimestre móvil **M-2, M-1, M** (cierre **M**).

No basta con fechas declaradas o nombres de archivos. Ambos originales deben superar verificación de contenido, integridad de archivo, procedencia y revisiones. El proceso no trasladará tasas de otro trimestre, no permitirá mezclar meses ni declarará una nueva vintage cuando falte evidencia.

## Procedimiento de recepción (sin recalcular)

Desde la carpeta que contiene `icml-colombia`, con el proyecto instalado:

```powershell
# Mientras falte cualquiera de los dos originales, se crea un plan BLOQUEADO.
python -m icml operations monthly-cycle `
  --root . `
  --period 2026-09 `
  --output ..\staging\septiembre_2026_auditoria_001
```

Cuando los dos originales estén disponibles localmente (los meses mostrados deben verificarse frente al contenido):

```powershell
python -m icml operations monthly-cycle `
  --root . `
  --period 2026-09 `
  --geih-annex "C:\FuentesDANE\anex-GEIH-sep2026.xlsx" `
  --geih-month 2026-09 `
  --social-annex "C:\FuentesDANE\anex-informalidad-jul-sep2026.xlsx" `
  --social-start 2026-07 `
  --social-end 2026-09 `
  --output ..\staging\septiembre_2026_auditoria_002
```

**Las rutas son ilustrativas y no afirman que estos archivos ya estén disponibles.**
El comando devuelve código de salida `2` deliberadamente: completar la recepción no equivale a autorizar la ejecución estadística. Se debe examinar el JSON creado en la nueva carpeta.

Para comprobar el paquete de evidencia sin tocar los productos:

```powershell
python -m icml operations verify-monthly-cycle `
  --root . `
  --cycle ..\staging\septiembre_2026_auditoria_002
```

El verificador devuelve `0` si los archivos de staging y los ocho productos congelados mantienen su integridad; **esto tampoco autoriza el cálculo**. La carpeta de staging es única: se rechaza cualquier ruta ya existente o situada dentro del checkpoint.

## Puertas del flujo

| Puerta | Implementación | ¿Permite publicar? |
|---|---|---|
| P0. Último corte + continuidad calendario | Comprueba `2026-08 → 2026-09` | No |
| P1. Dos archivos y períodos declarados | `source_pair.py` | No |
| P2a. Celdas GEIH, tasas e identidades | `h22.inspect_annex` cuando está el original | No |
| P2b. XLSX Seguridad Social, origen y trimestre reales | **Pendiente de validador de contenido específico** | No |
| P3. Materialización de fuentes canónicas del motor desde ambos anexos | **Pendiente del adaptador integrado** | No |
| P4. Cadena laboral, informalidad, sectorial y cierres | Motor existente, pero **no ejecutado para un nuevo mes** | No |
| P5. Comparación de vintages, anclas, calidad y Golden | Parcial; RC1 externos faltantes | No |
| P6. Publicación/control de versión | Bloqueada; requiere P0–P5 completas y aprobación | No |

La ejecución ordinaria `icml run` que ya existía corresponde a la cadena histórica de investigación; **no constituye por sí sola un pipeline de actualización de los ocho productos**. No debe usarse como atajo para publicar ni generar una mensualidad integral.

## Evidencias de H23

- `23_monthly_cycle.json`: fuentes, meses, hashes, resultados de puerta y plan de etapas.
- `23_geih_observations.csv`: solo valores nacionales y 13 ciudades validados en el XLSX GEIH; encabezados sin valores si falta el original.
- `sources/`: copias byte a byte de las fuentes recibidas, con hashes SHA-256 registrados. No se reescriben los originales.
- `verify-monthly-cycle`: confirma que las copias recibidas y los ocho productos históricos son idénticos a los que constan en la auditoría.

Los hashes permiten detectar cambios accidentales, pero no constituyen firma digital del DANE ni prueban oficialidad. Las cifras generadas no son oficiales y se mantienen las incertidumbres científicas previas.

## Criterios para habilitar la fase ejecutora

Se debe implementar y probar el lector verificable del original de Seguridad Social y validar sus ventanas y variables; incorporar ambos originales a los *inputs* de las etapas activas, no solo guardar sus rutas; ejecutar completamente los componentes laboral, informalidad y sectorial bajo el mismo mes objetivo; cerrar las ocho salidas y auditar todas las diferencias con la última vintage. Solo después se podrá habilitar una etapa de promoción con control de autorizaciones y reversión.

No se reentrenan los modelos ni se revisan las series históricas sin un cambio metodológico o revisión oficial aprobados y documentados.
