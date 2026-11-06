# ICML — Catálogo único de insumos, H26

**Corte congelado:** agosto de 2026. **Modelo:** H16, sin modificación.  
**Código:** H24/H25, reorganizado para portabilidad. **No usar código antiguo RC2.**

## Directorios

- `datos/1_ingesta/dane/geih_mercado_laboral/AAAA-MM/`: anexo oficial GEIH mensual, una copia activa por corte.
- `datos/1_ingesta/dane/geih_departamentos/AAAA/`: anexo departamental anual; el lector acepta XLSX y XLS (este último requiere xlrd).
- `datos/2_procesamiento/fuentes_preparadas/nacional/`: insumos históricos nacionales.
- `datos/2_procesamiento/fuentes_preparadas/urbano/`: señales urbanas, donantes y configuración congelada.
- `datos/2_procesamiento/fuentes_preparadas/departamental/`: proyecciones históricas por territorio.
- `legacy/archivo_original_duplicado/`: XLS binario departamental original, únicamente para trazabilidad y comparación, NO se utiliza en el pipeline activo.
- `datos/2_procesamiento/fuentes_preparadas/anclas_dane/`, `datos/1_ingesta/censo_original/`, `datos/2_procesamiento/fuentes_preparadas/demografia/`, `datos/2_procesamiento/fuentes_preparadas/informalidad/`, `datos/2_procesamiento/fuentes_preparadas/sectorial/`: insumos auxiliares especializados existentes; no son los productos finales.
- `datos/2_procesamiento/productos_congelados/laboral/`: **bases laborales congeladas** usadas como entradas de otros componentes; son *outputs históricos*, no anexos que se sustituyen al actualizar.

**Fuente única de rutas y hashes activos:** `datos/2_procesamiento/catalogos/catalogo_fuentes.json`. Cada entrada indica `role`, `path`, `sha256`, categoría y procedencia. Las configuraciones `configs/rc1/{national,urban,departmental,integration}.toml` apuntan a estas mismas rutas; el auditor impide discrepancias. El anexo mensual aparece en dos roles pero corresponde a **un solo archivo físico**.

## Comandos

Desde `root/` con el paquete instalado en editable:

```powershell
python -m icml operations source-audit --root ..
python -m icml operations integral-preflight --root .. --mode recompute
python -m icml operations run-integral --root .. --mode verify --output ..\..\auditoria_h26
```

Para recibir un nuevo archivo (sin activarlo ni modificar series):

```powershell
python -m icml operations source-stage --root .. --role departmental.annex --file "D:\Fuentes\Anexo GEIH Departamentos 2026.xlsx" --period 2026 --output "D:\Staging\icml_departamentos_2026"
```

Una actualización autorizada requiere **nueva vintage inmutable**, revisión de estructura y cambios de cobertura, ajustes controlados de TOML, y **regeneración del catálogo/hash**. No reemplazar a mano el fichero de agosto ni editar solo una ruta: ambas romperían `source-audit`.

Para avanzar de mes, los dos anexos **GEIH Mercado Laboral** y **Empleo Informal y Seguridad Social** son obligatorios y deben tener **el mismo mes final**. El período trimestral móvil de Seguridad Social no es un dato mensual directamente observado. `source-stage` no autoriza actualización ni publicación.

## Advertencias

La comparación del `.xlsx` convertido contra las celdas del `.xls` binario requiere un lector binario funcional para equivalencia completa. La compatibilidad estructural y el parser anual sí se han comprobado. El catálogo Golden RC1 contiene **rutas históricas de un proyecto anterior**, no rutas de ejecución activa; no convertirlas en rutas actuales.

Las carpetas `informalidad/`, `research/sectoral/`, `CIERRE_MODELO/` son evidencias de modelos y resultados congelados. No moverlas sin migrar sus manifiestos hash y verificaciones de reproducibilidad.

### Sincronizar apuntadores desde un único lugar

En una **copia nueva** del proyecto para una revisión futura, actualiza solo la ruta, hash y metadatos del insumo en `datos/2_procesamiento/catalogos/catalogo_fuentes.json`. A continuación:

```powershell
python -m icml operations source-sync --root ..
python -m icml operations source-sync --root .. --apply
python -m icml operations source-audit --root ..
```

La primera invocación muestra qué apuntadores cambiarían. `--apply` cambia **únicamente** los campos `*.sources` en los TOML de una copia: ni modelos, ni coeficientes, ni archivos de datos. No activa un nuevo anexo GEIH mensual sin la regla obligatoria de **dos anexos del mismo período**; esa operación sigue bloqueada y requiere el flujo de vintage completo.
