# H27 — Evidencia Golden RC1 y ejecución bloqueada

Se localizaron 102 entradas del catálogo `configs/golden/rc1_catalog.toml` dentro del archivo histórico RC2 facilitado por el autor. Hay 101 **rutas físicas únicas** porque dos IDs comparten una. Se extrajeron únicamente las rutas catalogadas; **ningún script antiguo**.

Los hashes SHA-256 de **102/102** entradas coinciden con los valores preexistentes del catálogo. La referencia recuperada reside fuera del árbol de código, en `../validacion/rc1_original/`, con rutas `fases/...` originales. La extracción **NO** convierte sus métodos originales en el código operativo.

## Reproducción RC1 exigida para certificación completa

1. Instalar Python **3.12** y crear un entorno virtual nuevo.
2. Instalar dependencias exactas con `python -m pip install -c requirements/lock-py312.txt -e ".[dev]"`.
3. Asignar `ICML_GOLDEN_DIR` a la ruta absoluta de `validacion/rc1_original` (la carpeta que contiene `fases/`).
4. Ejecutar `python -m pytest -q tests/regression` desde `icml-colombia/`, sin saltar pruebas, y conservar `pytest` y las versiones de paquetes en el acta.
5. Ejecutar `python -m icml operations certify --root .. --golden-dir ../validacion/rc1_original --report ../auditorias/rc1_certificate.json` y comprobar **por separado** los resultados de regresión. El comando `certify` por sí solo **no ejecuta** la suite de regresión.

En el entorno que generó H27 solo estaba disponible Python 3.13, con versiones numéricas distintas. No es defendible forzar esa suite RC1, ni etiquetar las 131 pruebas de equivalencia como aprobadas. La comprobación de **hashes** sí se efectuó; su estado es `PASS_REFERENCE_INTEGRITY_ONLY`.

## Comparación H27 con agosto congelado

La cadena de agosto se ejecuta de extremo a extremo por `run-integral --mode recompute`, sin acceder a septiembre. En el informe H27 se registran claves, cobertura, residuos y discrepancias columna por columna; la salida de cálculo no reemplaza el checkpoint congelado sin revisión.
