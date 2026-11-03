# ICML Core H36 — Complemento RC1 / H11 / CNPV 2018

Esta entrega complementa `ICML_CORE_H36.zip`. Es un paquete de **referencias e insumos**, NO una nueva versión del código.

## Contenido

- `validacion/rc1_original/`: **101 archivos físicos** de la referencia Golden RC1, que cubren **102 IDs del catálogo** `icml-colombia/configs/golden/rc1_catalog.toml` (2 IDs apuntan a la misma ruta).
- `research/sectoral/h11/inputs/`: **5 archivos**, conservando las rutas de origen.
- `insumos/censo_original/`: **1 archivo** original `CNPV-2018-Poblacion-Ajustada-por-Cobertura.xls`.
- `MANIFIESTO_COMPLEMENTO_RC1_H11_CENSO.json`: listado de todos los archivos, tamaños y SHA-256.

**Verificación de integridad:** 102/102 entradas catalogadas coinciden con sus SHA-256 de referencia, sin archivos ausentes o adicionales en Golden RC1. No implica que la suite de regresión se haya ejecutado.

## Instalación de carpetas

Descomprima `ICML_CORE_H36.zip` en una carpeta (por ejemplo `D:\ICML`). Después descomprima este complemento **en la misma carpeta**. Ambos ZIP contienen un directorio superior `ICML_CORE_H36/` y se fusionan sin reemplazar los archivos de código existentes.

Estructura resultante:

```
D:\ICML\ICML_CORE_H36\
  icml-colombia\
    configs\golden\rc1_catalog.toml
    requirements\lock-py312.txt
    tests\regression\
  validacion\rc1_original\fases\...
  research\sectoral\h11\inputs\...
  insumos\censo_original\CNPV-2018-Poblacion-Ajustada-por-Cobertura.xls
```

## Ejecutar regresión RC1 (PowerShell)

Desde `D:\ICML\ICML_CORE_H36` con Python 3.12 y el entorno numérico fijado en `requirements/lock-py312.txt`:

```powershell
$env:ICML_GOLDEN_DIR = (Resolve-Path '.\validacion\rc1_original').Path
cd .\icml-colombia
..\.venv\Scripts\python.exe -m pip install -c requirements/lock-py312.txt -e '.[dev]'
..\.venv\Scripts\python.exe -m pytest -q tests/regression
```

Para el comando adicional de certificación (NO sustituye pytest):

```powershell
..\.venv\Scripts\python.exe -m icml operations certify --root .. --golden-dir ..\validacion\rc1_original --report ..\auditorias\rc1_certificate.json
```

Si aún no se instaló el core, seguir primero `ICML_CORE_H36/LEER_PRIMERO.md` e `INSTALAR_WINDOWS.bat`.

**Nota:** este ZIP proporciona los archivos faltantes, pero **no certifica todavía las 131 pruebas**: deben ejecutarse en el ambiente fijado y revisarse sus resultados. No sustituye validación científica independiente H9.
