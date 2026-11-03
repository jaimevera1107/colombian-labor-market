# ICML 2.2.28.dev0 — Ejecución reproducible agosto 2026

## Política

El modelo **termina en agosto de 2026**. Esta operación no descarga nuevos meses y no cambia los ocho productos congelados ni los modelos. Para nuevas mensualidades se requieren **ambos anexos DANE correspondientes al mismo mes de cierre**. La salida experimental sectorial no es estadística oficial.

## Estructura

- `insumos/`: fuentes activas centralizadas con catálogo de rutas y hashes.
- `icml-colombia/`: **única versión de código** y comandos de ejecución.
- `_test_quality_run/products/`: tres productos laborales congelados.
- `informalidad/cierre_integral_v013/`: informalidad congelada.
- `research/sectoral/h16/`: modelo sectorial seleccionado y auditorías.
- `validacion/rc1_original/`: **solo datos Golden recuperados del RC2**, nunca scripts.
- `ENTREGA_H27/`: actas y controles de la versión.

## Comandos Windows (PowerShell)

Situarse dentro de `icml-colombia` y crear un entorno compatible:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements/lock-py312.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m icml operations source-audit --root ..
.\.venv\Scripts\python.exe -m icml operations integral-preflight --root .. --mode recompute
```

La reejecución integral usa una carpeta de destino nueva **fuera** del checkpoint:

```powershell
.\.venv\Scripts\python.exe -m icml operations run-integral --root .. --mode recompute --output D:\ICML_corridas\agosto_2026_r01
```

Verificar `integral_execution_report.json`: `status=RECOMPUTED_ALL_EIGHT_AUDITED`, `candidate_cross_audit.status=PASS`, `eight_product_equivalence_passed=true`. Se registran discrepancias numéricas por columna, diferencias de orden y de formato CSV, sin sobrescribir los resultados de referencia. Si falla, ningún resultado se promociona.

La comparación de integridad de las 102 referencias RC1 no equivale a una prueba de regresión numérica; para esta ejecutar `scripts/production/certificar_rc1_h27.ps1` desde `icml-colombia` con Python 3.12 y dependencias bloqueadas. No etiquetar el software como RC1-certificado antes de obtener esa evidencia.

## Productos

Son ocho: tres laborales, tres informalidad y dos sectorial. Se conservan separados los universos `ICML_COMPLETO` y `DANE_REFERENCIA`/GEIH representado; nunca se impone equivalencia de los representados de informalidad y laboral sin justificación. Las ciudades no constituyen una partición aditiva nacional. `NO_INFO` no se redistribuye.

## Lo que no se da por demostrado

- Revisión científica adicional sobre las ramas sectoriales históricas o departamentos extrapolados.
- Identidad byte por byte cuando el nuevo formato CSV redondea valores o reordena columnas; manda la auditoría estructural/numerical con tolerancias.
- Certificación RC1 en Python 3.12 sin ejecutar la suite completa.
- Incorporación automática de un nuevo mes del DANE.
