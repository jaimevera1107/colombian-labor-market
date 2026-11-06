# ICML H32 — Origen exacto de las señales urbanas y política del ejercicio anterior

**Versión:** 2.2.32.dev0. **Corte:** agosto de 2026. **Regla:** el código actual es el único ejecutable; los proyectos anteriores son evidencia comparativa y nunca fuentes del modelo.

## Corrección de procedencia frente a H31

La hoja **`Total 23 ciudades A.M. Trim`** del Excel **`Anexo_GEIH_Agosto_2026.xlsx`** contiene las series móviles trimestrales de las 23 ciudades, con cierres desde marzo de 2007. Se comprobó que las seis columnas `*_geih` del archivo `senales_historicas_23_y_donantes.csv` corresponden a la **mediana de las ventanas de tres meses que terminan dentro de cada año**, en miles de personas:

- **2007:** diez ventanas con cierre marzo–diciembre.
- **2008–2025:** doce ventanas por año.
- **2026:** ocho ventanas, con cierre enero–agosto.
- No son observaciones mensuales puntuales ni promedios de doce niveles mensuales independientes.

El extractor `icml.operations.h32_urban_annex.extract_urban_historical_annex` lee el XLSX vigente, comprueba etiquetas de conceptos y ciudades, calcula las medianas y produce las señales históricas para los **33 territorios × 20 años = 660 registros**. Las diez transferencias a territorios sin ciudad observada usan el archivo **ya congelado** `donantes_congelados_referencia.csv`, que representa la asignación de las **señales históricas**. No es el catálogo de **nueve donantes Pareto seleccionados en H30**, que se mantiene independiente e intacto.

Para las columnas `employed`, `unemployed`, `inactive`, `pea`, `pet` y `population` (sin sufijo `_geih`), desde 2021 se utiliza la hoja **`Año_móvil_32_ciudades`**, mediante el extractor H31 de ventanas de doce meses. Antes de 2021 son nulas. **Excepción explícita:** Cundinamarca tiene 24 valores sintéticos para 2021–2024, archivados como referencia de calibración interna en `cundinamarca_25_senales_sinteticas_2021_2024.json`; no son mediciones oficiales y no se reconstruyen desde la hoja de 32 ciudades. Para 2025–2026 permanecen vacíos.

## Validación contra el checkpoint congelado

- **660 registros**, sin claves faltantes, sobrantes o alteración de donantes históricos.
- Para las 23 ciudades originales hay **2.760 celdas** únicas (23 × 20 × 6 variables); las correspondientes señales de los 33 territorios son transferencias de esos valores conforme al mapa congelado.
- Diferencia máxima para `*_geih`: `4.8247534721213015e-05` **miles de personas** (aprox. **0,0483 personas**), por el redondeo del CSV histórico.
- Diferencia máxima en proxies de 32 ciudades: `0.05000000004656613` personas, también atribuible al redondeo histórico.
- Ningún valor fuera de tolerancia; se conservan los 24 valores sintéticos y las ausencias identificadas.
- Las referencias congeladas no se sobrescriben: el generador escribe en una nueva carpeta de *staging* y compara cada campo.

## Qué hacer con el ZIP `ICML_Original_Produccion_Integral(1)(3).zip`

Es **exclusivamente material de investigación y contraste** (SHA-256 `6322b406045ea36a28ca4043db86335e39313bdff1b4cac8e1f746e846e6f04e`). Sus notebooks, módulos, modelos y niveles empalmados antiguos no se incorporan al ejecutable actual.

Los seis campos `*_spliced` archivados en `indicadores_mensuales_1993_2003.csv` pertenecen al **ejercicio anterior**; no son entradas de estimación. La etapa nacional vigente selecciona expresamente los indicadores declarados en `configs/rc1/national.toml` (`UVR`, `IPC`, `IPP`) mediante `prepare_monthly_indicators`, que descarta columnas no solicitadas. Los campos anteriores se conservan solo para comparación con vintages históricos y pruebas retrospectivas; no deben regenerarse ni reinterpretarse como fuentes oficiales.

## Ejecución

```powershell
python -m icml operations prepare-all-excel --root .. --output ..\staging_h32
```

Genera nueve derivados verificados: cinco de H29 y cuatro de H31/H32, incluyendo las señales urbanas completas. No recalcula modelos, no cambia las ocho bases congeladas y no abre una nueva vintage.

**Límite restante:** la validación anterior demuestra reproducibilidad del **anexo congelado de agosto 2026**, no autoriza automáticamente cualquier futura revisión de ese anexo ni certifica resultados de modelos con series revisadas. Para una actualización ordinaria siguen siendo obligatorios los dos anexos oficiales sincronizados del mismo mes de cierre.

**SHA-256 de referencia sintética interna H32:** `936bddf0dd81f15daa8b9f07580cb411376b6362c26b5a647b4b155ab6e71455`.
