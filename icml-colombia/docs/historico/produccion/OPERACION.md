# Manual de operación — ICML 2.2.25.dev0 (H23; origen H20)

> CANDIDATO DE PRODUCCIÓN TÉCNICA; estadística reconstruida/no oficial.

En PowerShell desde la carpeta que contiene `icml-colombia/` y `ENTREGA_H20/`:

```powershell
cd .\icml-colombia
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements/lock-py312.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m icml operations preflight --root .. --output ..\auditorias\preflight_001
.\.venv\Scripts\python.exe -m icml operations verify-products --root .. --report ..\auditorias\products_001.json
.\.venv\Scripts\python.exe -m pytest -q tests/unit tests/regression
```

Para generar una entrega INMUTABLE que explícitamente diga NO OFICIAL:

```powershell
.\.venv\Scripts\python.exe -m icml operations freeze-products --root .. --destination ..\vintages\1993-2026-08_H20_EXPERIMENTAL
```

No reutilices `--destination`: siempre usa una ruta nueva. Esto no incorpora un mes nuevo.

Para nuevas mensualidades NO ejecutar directamente `icml run` como si fuese una actualización integral. Primero seguir el procedimiento H23 en `docs/production/H23_PIPELINE_MENSUAL.md`, con dos fuentes DANE del mismo mes de cierre. La computación integral y cualquier nueva vintage siguen bloqueadas hasta contar con validación de contenido de Seguridad Social y adaptación completa de ambos anexos. `icml run` es la cadena laboral histórica, no el flujo de ocho productos.

## Qué no está habilitado

- Distribución como cifras oficiales del DANE.
- Publicación automática sin revisión humana de un nuevo anexo.
- Afirmar certificación golden (faltan artefactos externos).
- Afirmar que una actualización real posterior a agosto de 2026 se ha probado.

Si `preflight` y `verify-products` pasan, sólo se establece integridad del checkpoint, no validación científica adicional.
