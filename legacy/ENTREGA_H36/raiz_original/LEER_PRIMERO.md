# ICML CORE H36 — Código + insumos operativos autocontenidos

**Corte:** agosto de 2026. **Motor:** `icml-colombia==2.2.35.dev0` (checkpoint de entrega H36).
**Alcance:** reproducción del corte, NO actualización automática de meses posteriores, NO publicación oficial.

## Qué contiene

- `icml-colombia/`: código Python (`src/icml`), CLI, configuraciones RC1, pruebas, utilidades y documentación.
- `insumos/`: fuentes de ejecución (incluidos anexos originales de julio y agosto), catálogo, datos históricos usados por el motor.
- `censo/`, `informalidad/`: puente censal, priors congelados de H9, secuencia H5/H6 y referencia H9.
- `research/sectoral/h16/`: entradas, modelo y referencias de la etapa sectorial H16.
- `CIERRE_MODELO/PRODUCTOS`, `_test_quality_run/products`: productos congelados necesarios para pruebas y comparaciones.
- `dependencias/`: rueda original `tempdisagg==0.6.3`.

No contiene salidas de ejecución H36 ni los checkpoints históricos completos H19–H35, porque no son necesarios para reproducir la corrida actual.
Se debe instalar Python y las dependencias externas de `pyproject.toml` (NumPy, SciPy, pandas, scikit-learn, XGBoost, etc.).
La rueda `tempdisagg` viene incluida, pero este ZIP NO es un entorno Python offline que contenga todas las dependencias binarias del sistema.

## Instalación en Windows / PowerShell

Situarse **en esta carpeta raíz**, no en `icml-colombia`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install --no-deps .\dependencias\tempdisagg-0.6.3-py3-none-any.whl
.\.venv\Scripts\python.exe -m pip install -e .\icml-colombia
.\.venv\Scripts\python.exe -m pip install pytest
```

## Verificación sin recálculo

**Desde la carpeta raíz**:

```powershell
.\.venv\Scripts\python.exe -m icml operations run-integral --root . --output ..\ICML_H36_verificacion --mode verify
```

El destino de salida debe ser una carpeta **nueva y externa** a la raíz del core.
No se permite sobrescribir una salida existente.
Revise `ICML_H36_verificacion/integral_execution_report.json`.

## Reproducción integral desde Excel (puede requerir tiempo y memoria)

```powershell
.\.venv\Scripts\python.exe -m icml operations run-integral --root . --output ..\ICML_H36_recalculado --mode recompute
```

Verifique en `integral_execution_report.json` el estado `RECOMPUTED_ALL_EIGHT_AUDITED`,
`eight_product_equivalence_passed=true` y la auditoría cruzada `PASS`.
**El código tiene corte fijo 2026-08**: un anexo de un mes posterior NO convierte automáticamente esta entrega en una nueva vintage.

## Pruebas

```powershell
cd icml-colombia
..\.venv\Scripts\python.exe -m pytest -q
```

Las **131 pruebas RC1 Golden** no están certificadas en H36; su ejecución requiere referencias y condiciones de certificación separadas.
No interpretar `skipped` como `passed`.

## Integridad y seguridad

`MANIFIESTO_CORE_H36.json` enumera cada archivo con SHA-256.
No cambie archivos de `insumos/`, los productos congelados o los parámetros H9/H16 sin establecer una vintage nueva.
No son estadísticas oficiales. H9 es una estimación departamental sin observaciones oficiales departamentales directas de referencia.
La validación científica se basa en pruebas indirectas, predictivas y de robustez.
