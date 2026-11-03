> **Actualización H32 (2026-11-02):** la dependencia histórica `senales_historicas_23_y_donantes.csv` SÍ se regenera desde el anexo GEIH de agosto de 2026, hoja `Total 23 ciudades A.M. Trim`, mediante medianas anuales de ventanas trimestrales móviles. Ver `H32_SENALES_URBANAS_Y_LEGADO_COMPARATIVO.md`. Las afirmaciones anteriores de que faltaba fuente primaria para 2007–2020 quedan superadas.

# H31 — Generación Excel de fuentes urbanas y nacionales históricas

**ICML 2.2.31.dev0. Corte: 2026-08. Estado: reproducción retrospectiva de insumos, NO actualización de una vintage.**

## Qué se recuperó con evidencia numérica

La hoja `Año_móvil_32_ciudades` del anexo **GEIH Mercado Laboral agosto 2026** genera `proxies_anuales_ventanas_2026_08.csv`:

- 2021: únicamente la ventana enero–diciembre de 2021.
- 2022–2025: media aritmética de las **12 ventanas de doce meses terminadas dentro de cada año**, no una serie de 12 observaciones mensuales.
- 2026: media de las ocho ventanas terminadas hasta agosto; año **incompleto**.
- Las seis cantidades se convierten de miles a personas.
- Las 32 ciudades se emparejan por nombres y códigos oficiales, no por posición de fila; se rechazan ciudades/columnas o claves ausentes.

**Prueba de equivalencia:** 192 pares ciudad-año × seis valores, 0 faltantes, diferencia máxima `5.82e-11` personas. La tabla y los códigos no se han reinterpretado.

El anexo nacional de **agosto de 2026** genera `official_geih_annual.csv` mediante medias de los meses publicados; 2001–2025 son años completos y **2026 es promedio enero–agosto**, no un promedio anual definitivo. Se reproducen 26 años × seis variables, diferencia máxima `3.34e-5` personas frente a RC1, compatible con redondeo del CSV congelado.

La hoja `Datos` de **Indicadores Económicos Externos Mensuales.xlsx** aporta **siete** columnas de 1993-01 a 2003-12: `exchange_rate`, `producer_price_index`, `consumer_price_index`, `inflation_rate`, `industrial_production_index`, `real_value_unit_uvr`, y **`vacancies`** (columna H). Se reproducen 132 meses, error máximo `0.0` sobre las siete columnas. `vacancies` es un dato de ese Excel archivado; la autenticidad institucional de su descarga original aún no está acreditada.

## Qué NO se considera generado desde Excel original

1. `senales_historicas_23_y_donantes.csv` — 660 celdas ciudad-año de 2007–2026. El código actual reproduce la **selección Pareto** con estas señales, pero el anexo GEIH 2026 solo proporciona las ventanas móviles **2021–2026**. No dispone de las 23 trayectorias procesadas 2007–2020 ni recupera sus fuentes primarias. El CSV sigue **congelado** y verificado por SHA-256. No se sustituyó con proyecciones arbitrarias.
2. Los **seis campos `*_spliced`** en `indicadores_mensuales_1993_2003.csv`. Son niveles laborales empalmados de la vintage histórica: no pertenecen al Excel económico y **no coinciden** con el empalme reconstruido por el pipeline nacional actual. Se conserva su origen legado y su hash. En la especificación nacional actual, los indicadores Chow–Lin son `UVR`, `IPC` o `IPP`, no estos campos `*_spliced`.
3. La **selección de donantes** no se reestima: se mantiene H30 `donantes_pareto_congelados_h30.json`; se deben verificar hashes y guardas antes de cualquier nueva vintage.

## Operación desde Excel, no desde CSV proporcionados manualmente

```powershell
# Desde icml-colombia/ y con paquete instalado
python -m icml operations prepare-all-excel `
  --root .. `
  --output ..\preparacion_h31_agosto
```

Produce cinco derivados H29 y cuatro derivados H31/H32, en una **carpeta nueva fuera del proyecto**, con auditorías y hashes. La operación nunca sobrescribe ni activa una fuente, cambia el corte ni reentrena modelos. El control se bloquea si los XLSX no coinciden con la vintage aprobada o los resultados difieren de las bases internas congeladas. Para inspeccionar solo H31:

```powershell
python -m icml operations prepare-historical-excel `
  --root .. `
  --output ..\solo_h31
```

## Regla de operación futura

El titular administra originales Excel, pero **no** debe regenerar CSV a mano. La preparación desde Excel se integra como fase de *staging*; **no está aún conectada automáticamente con una actualización futura del pipeline de producción**. Para publicar otro mes se exigen GEIH Mercado Laboral y Empleo Informal/Seguridad Social con mismo mes de cierre, además de validadores, propuestas de revisión de históricos y comparación contra vintage previa.

La política de PIB, el historial urbano 2007–2020 y algunos insumos censales quedan como dependencias históricas identificadas o datos auxiliares que se revisan cuando la fuente correspondiente cambie. Ninguna actualización mensual debe recalcular la elección congelada de donantes.
