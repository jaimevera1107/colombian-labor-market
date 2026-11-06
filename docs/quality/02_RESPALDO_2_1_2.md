# Respaldo integral del ICML 2.1.2.dev0

El respaldo portátil separa **código** (`icml-colombia/`) de **productos
publicados y diagnósticos** (`productos/`) y de **insumos congelados de
referencia** (`insumos/`), sin introducir artefactos pesados dentro del
repositorio Python (ver `.gitignore`). Se mantienen sin cambios las
subcarpetas `src/`, `tests/`, `configs/`, `docs/` y `requirements/`.

Los tres CSV canónicos son:

- `productos/bases/ciudades.csv`
- `productos/bases/departamentos.csv`
- `productos/bases/nacionales.csv`

El listado de los archivos y sus SHA-256 vive en la raíz del respaldo:
`MANIFIESTO_RESPALDO_SHA256.json`. Ejecutar desde la carpeta extraída:

```bash
python icml-colombia/tools/release/verify_backup.py --bundle .
```

La verificación valida integridad de archivos, cardinalidad, fechas,
variables laborales, identidades, y factores de 1993–2000.

**No se alteraron estimaciones de empleo ni denominadores.** Esta entrega
es un paquete de conservación de la implementación 2.1.2.dev0 y sus
productos. Las alertas de linealidad y cambios estructurales siguen
vigentes: el estado de certificación continúa siendo
`REQUIERE_REVISION_METODOLOGICA`.

La biblioteca `tempdisagg==0.6.3` sigue siendo una dependencia fijada,
no se incorpora como código fuente de ICML. Los anexos DANE originales
y demás recursos históricos se conservan en el ZIP de recursos separado
que se entregó previamente.
