# ICML H21 — Cierre de auditoría de certificación técnica

**Paquete**: `2.2.22.dev0` (derivado de H20 `2.2.21.dev0`). **Corte**: agosto de 2026. **Estado**: candidato de investigación **no certificado**.  
**No se recalcularon modelos, estimaciones, ni se incorporaron datos nuevos.**

## Ejecución observada en este entorno

- 323 pruebas aprobadas, 137 omitidas en `tests/unit` y `tests/regression`.
- De las omitidas, **131** dependen de la referencia RC1 y **6** usan bases congeladas ausentes del checkout de código (aunque incluidas en la distribución). No equivalen a pruebas aprobadas.
- El catálogo RC1 contiene **102 entradas y 101 rutas físicas únicas**: dos ID apuntan al mismo CSV y mismo SHA-256. No es inconsistencia.
- Los **ocho productos** activos H20 fueron verificados en lectura contra sus hashes congelados.
- `pip wheel --no-deps --no-build-isolation` produjo la wheel `icml_colombia-2.2.22.dev0-py3-none-any.whl`; se instaló aisladamente en un directorio temporal y su CLI respondió al `--help`.
- Entorno utilizado en esta ejecución: Python 3.13.5; el lock RC1 exige Python 3.12 y versiones numéricas distintas, por tanto **no se pudo certificar equivalencia RC1**.
- Los artefactos externos Golden no están disponibles en H20 ni en los checkpoints H19/H11/Original inspeccionados con las rutas históricas del catálogo. Ningún Golden nuevo fue fabricado.

## Procedimiento de certificación para Windows (PowerShell)

Desde la carpeta que contiene `icml-colombia`:

```powershell
cd .\icml-colombia
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements/lock-py312.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m icml operations certify --root .. --report ..\auditorias\H21_01.json
.\.venv\Scripts\python.exe -m pytest -q tests/unit tests/regression -rs
```

Si se dispone **de la carpeta ORIGINAL e íntegra** con las 102 referencias RC1 externas:

```powershell
.\.venv\Scripts\python.exe -m icml operations certify --root .. --golden-dir "D:\REFERENCIA_RC1" --report ..\auditorias\H21_02.json
$env:ICML_GOLDEN_DIR = 'D:\REFERENCIA_RC1'
.\.venv\Scripts\python.exe -m pytest -q tests/unit tests/regression -rs
```

Sustituir rutas de ejemplo por las reales. `--report` exige una ruta nueva; no sobrescribe auditorías. **El comando `certify` comprueba los hashes, pero no ejecuta por sí mismo las 131 pruebas Golden**, que deben aprobarse después con `pytest` en el entorno fijado.

Si no se recupera RC1, puede conservarse el **baseline de integridad H20** de ocho productos y generar nuevos Golden para versiones futuras con procedencia *nueva*, pero **no denominarlos RC1 ni presentarlos como validación retrospectiva independiente**.

## Puertas pendientes para una versión estable

1. Recuperar el conjunto RC1 auténtico, comprobar sus 102 hashes y ejecutar la equivalencia del pipeline en Python 3.12 con las bibliotecas fijadas; o aprobar y documentar formalmente una nueva línea base de regresión diferenciada de RC1.
2. Comprobar instalación y regresión en el sistema de destino (Windows), pues esta ejecución ocurrió en Linux.
3. Actualización real con un anexo DANE posterior a agosto 2026, comparando vintages y sin alterar las series definitivas sin revisión autorizada (H22).

**Conclusión**: `H21_CHECKPOINT_INTEGRITY_PASS; STABLE_RELEASE_BLOCKED`. La estadística sigue siendo una reconstrucción de investigación, no una cifra oficial.
