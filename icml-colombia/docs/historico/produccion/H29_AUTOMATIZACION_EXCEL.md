> **Actualización H32 (2026-11-02):** la dependencia histórica `senales_historicas_23_y_donantes.csv` SÍ se regenera desde el anexo GEIH de agosto de 2026, hoja `Total 23 ciudades A.M. Trim`, mediante medianas anuales de ventanas trimestrales móviles. Ver `H32_SENALES_URBANAS_Y_LEGADO_COMPARATIVO.md`. Las afirmaciones anteriores de que faltaba fuente primaria para 2007–2020 quedan superadas.

# ICML 2.2.29.dev0 — H29: fuentes Excel y reconstrucción de insumos

**Corte:** agosto de 2026. **Estado:** reconstrucción y verificación retrospectiva de insumos, NO actualización de la vintage.

## Principio operativo

Las fuentes externas administradas por la persona usuaria deben ser libros Excel. Los archivos CSV generados son **productos internos del preparador**, no archivos que la persona usuaria tenga que construir. Se preservan los originales por SHA-256, las transformaciones quedan versionadas y los resultados se preparan fuera del checkpoint.

Para abrir una nueva mensualidad ICML se requieren **dos anexos DANE del mismo mes de cierre**: GEIH mercado laboral del mes y el anexo Empleo Informal y Seguridad Social cuyo trimestre móvil acaba en ese mes. Ningún `prepare-excel` autoriza publicación, actualización ni reestimación.

## Cadena comprobada de Excel original a base interna

| Origen Excel | Hoja | Producto interno | Filas | Validación contra H27 |
|---|---|---|---:|---|
| Reconstrucción ENH Anual 1993-2001.xlsx | `ENH_Final` | `source_enh_annual.csv` | 12 | 12 claves, 6 variables exactas |
| Proyecciones de Población 1993–2004, 2005–2019, 2020–2050.xlsx (3 archivos) | `Departamental_*` | `proyecciones_poblacion_original.csv` | 4.752 | Identidad de claves y valores, 1993–2050 |
| PIB Departamentos 2024.xlsx | `Cuadro 1` (corrientes; **NO** `Cuadro 2`) | `gdp_groups_2005_2024.csv` | 7.920 | Identidad de 33 territorios, 12 agregados, 20 años y valores |
| Anexo GEIH Departamentos 2025.xlsx | `Ocu ramas anual  Dptos CIIU 4` | `official_sectors_2015_2025.csv` | 3.542 | 23 departamentos, 14 ramas, 11 años y celdas origen |
| Anexo GEIH Informalidad Marzo 2021.xls (**archivo histórico inmutable**) + Anexo GEIH Informalidad Agosto 2026.xlsx | `Ciudades`, `Seguridad social T. nal` y `Total nacional` | `informality_source_observations.csv` | 6.580 | **Identidad byte a byte**; definiciones antigua y nueva permanecen separadas |

Se recuperaron **34 Excel originales** y se añadió el XLSX departamental de 2025 suministrado posteriormente (35 archivos registrados). Solo ocho roles del catálogo alimentan las cinco rutas verificadas. El archivo `.xls` de marzo de 2021 se mantiene como evidencia histórica interna congelada; **no es una entrada periódica que deba administrarse**. Los seis tipos de entrada futura mencionados por el usuario se gestionarán en XLSX.

## Uso

Desde `icml-colombia/`, con el paquete instalado:

```powershell
python -m icml operations prepare-excel `
  --root .. `
  --output ..\preparacion_excel_agosto
```

`--output` ha de ser una carpeta **nueva, fuera del checkpoint**. El programa devuelve estado `BLOCKED` sin entregar CSV si una comparación falla. La salida incluye `preparation_audit.json` y los cinco CSV regenerados. Las rutas aprobadas se almacenan en `insumos/fuentes/REGISTRO_EXCEL_ORIGINALES_H29.json`. Cambiar rutas o ficheros obliga a abrir un proceso nuevo de verificación y versionado; no se acepta activar el sustituto por sobrescritura.

**La comparación de los tres CSV numéricos y ENH es semántica por claves con tolerancia de `1e-9` en la unidad original, no por identidad de bytes:** una serialización decimal diferente puede cambiar el SHA del CSV sin alterar los datos. Informalidad sí coincide byte por byte.

## Qué sigue sin automatización demostrada desde fuentes primarias

Estos insumos siguen **congelados y verificados por H27**, pero no se han reemplazado:

1. `official_geih_annual.csv`: serie anual GEIH de una vintage de referencia; falta cotejo completo contra el anexo oficial de origen y documentación de agregación.
2. `indicadores_mensuales_1993_2003.csv`: combina indicadores macro con señales laborales ya empalmadas; un Excel de indicadores económicos no identifica por sí mismo todo el proceso.
3. `senales_historicas_23_y_donantes.csv`: requiere replicar el empalme urbano y la selección de donantes del proyecto actual, además de las observaciones originales.
4. `proxies_anuales_ventanas_2026_08.csv`: derivados urbanos históricos con ventanas; aún sin comparación de extractor contra la referencia.
5. Tablas derivadas CNPV, anclas sectoriales antiguas y otras referencias auxiliares: se conservan como instantáneas documentadas hasta probar su cadena completa.

**PIB departamental por actividad es una dependencia externa independiente:** su Excel 2024 está recuperado y verificado, pero para actualizar el PIB en el futuro se necesita una nueva publicación, no bastan GEIH y las tres proyecciones. Una actualización ordinaria sin PIB nuevo debe usar explícitamente la vintage congelada y no interpretarla como una observación de PIB reciente.

## Limitaciones del H29

- Los extractores de PIB, ENH y empleo sectorial se limitan a los períodos y estructura de las fuentes **congeladas**. Nuevas columnas, nuevos años o cambios de metodología se bloquean hasta actualizar contrato, pruebas y vintage. Esto es deliberado: evita aceptar cambios de significado sin revisión.
- El nuevo preparador de cinco entradas no sustituye todavía el pipeline de fuentes completo de `icml run`. Las demás instantáneas internas permanecen disponibles para reproducir agosto.
- El archivo de informalidad anterior a 2021 es un `.xls` histórico interno: no se ha convertido ni alterado para evitar pérdida de evidencia.
- Este hito **no ejecutó nuevamente los ocho estimadores**, porque no cambia las entradas congeladas ni los modelos; la reejecución integral de agosto fue documentada en H27.
- La equivalencia de regresión RC1 en Python 3.12 con el entorno numérico bloqueado continúa pendiente.

## Integridad

H27 no se modifica. Los ocho productos estadísticos y el código de estimación se conservaron inalterados. Únicamente se añaden extractores, configuración de fuentes, pruebas, documentación y versión del paquete.
