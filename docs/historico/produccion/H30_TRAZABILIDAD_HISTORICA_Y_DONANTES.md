> **Actualización H32 (2026-11-02):** la dependencia histórica `senales_historicas_23_y_donantes.csv` SÍ se regenera desde el anexo GEIH de agosto de 2026, hoja `Total 23 ciudades A.M. Trim`, mediante medianas anuales de ventanas trimestrales móviles. Ver `H32_SENALES_URBANAS_Y_LEGADO_COMPARATIVO.md`. Las afirmaciones anteriores de que faltaba fuente primaria para 2007–2020 quedan superadas.

# H30 — Trazabilidad histórica y decisiones congeladas de donantes

**Base:** ICML 2.2.29.dev0 → 2.2.30.dev0. **Corte:** agosto de 2026.
**Alcance:** auditoría de fuentes, congelamiento de decisiones del estudio original y contraste de libros Excel. **No reestima modelos ni sustituye series congeladas.**

## 1. Evidencia del estudio RC2

Conservamos en `docs/research/rc2_urban_decisions/` cinco documentos/CSV originales de RC2 con hashes y rutas en `MANIFEST_RC2.json`. Ningún módulo de código RC2 se trasplantó.

El análisis evaluó 9 receptoras × 23 donantes = 207 alternativas. Cinco dimensiones minimizadas: crecimiento logarítmico de ocupados, crecimiento logarítmico de población, tasas laborales, distancia de tamaños y dispersión del factor de escala. Se usó frontera no dominada, distancia ponderada al ideal (0,30;0,20;0,20;0,10;0,20), ventana de elección 2021–2024, guardas sobre 2025 y puente 2021 (tolerancia 0,03 log), y backtest de 23 ciudades.

La regla `pareto_con_guardia` obtuvo WAPE retrospectivo medio **10,96 %**, frente a **10,63 %** de `frontera_distancia` sin guardas. La elección priorizó control de riesgos, **no** menor error promedio. El año 2025 interviene en la guarda y no representa test totalmente independiente. Las 2021–2024 son proxies de promedios de ventanas móviles y **no** mensualidades observadas.

**El selector original ya estaba migrado a** `icml.urban.donors.ParetoDonorSelector` y parametrizado en `configs/rc1/urban.toml`. El H30 comprobó 207 alternativas, 23 ciudades de backtest y nueve asignaciones idénticas a `INFORME_PARETO_DONANTES.md` de RC2:

| Receptora | Donante Pareto congelado |
|---|---|
| Arauca | Armenia |
| Yopal | Villavicencio |
| Mocoa | Armenia |
| San Andrés | Quibdó |
| Leticia | Manizales A.M. |
| Inírida | Medellín A.M. |
| San José del Guaviare | Riohacha |
| Mitú | Armenia |
| Puerto Carreño | Bucaramanga A.M. |

Cundinamarca (25) conserva tratamiento **separado**, con donante sintético Bogotá (11). El estudio de cuatro donantes agregados es un *experimento de respaldo*, no parte del algoritmo activo.

### H30: bloqueo explícito de nuevas selecciones

Archivo inmutable: `insumos/fuentes/historicas/urbano/donantes_pareto_congelados_h30.json`. En ejecución se comprueba:
- SHA-256 de señales históricas y referencias de donantes;
- huella de los proxies fijos 2021–2025 (se permite agregar o modificar años posteriores sin retocar esa referencia);
- huella del conjunto de parámetros del selector;
- coincidencia de las nueve asignaciones.

Cualquier divergencia **bloquea** la etapa urbana y exige revisión metodológica y una nueva vintage aprobada. No recalcula el catálogo ante una actualización ordinaria mensual.

## 2. Excel del usuario y evidencia numérica

Los cuatro libros recibidos se guardan en `insumos/fuentes/historicas/auditoria_h30/`, junto con sus hashes. Son evidencia de auditoría y **no reemplazan entradas activas**.

| Libro Excel | Contraste | Decisión |
|---|---|---|
| `Departamental and National Population Projections Colombia 1993-2030 (2).xlsx` | **4.752 / 4.752** claves y valores iguales a `proyecciones_poblacion_original.csv`; el libro llega en realidad hasta **2050** | Puede vincularse como otra copia archivada del insumo demográfico, previa deduplicación |
| `Indicadores Económicos Externos Mensuales.xlsx` | Seis columnas (TRM, IPP, IPC, inflación, producción industrial, UVR): coincidencia numérica completa para **132 meses (1993-01 a 2003-12)** | Fuente histórica de esas seis columnas, congelada; NO explica vacantes ni variables laborales empalmadas |
| `Reconstruction National Labor Market Colombia 1993-2001.xlsx` | Los niveles de población, PET, PEA y ocupados **difieren** del CSV empalmado vigente en cada mes de solapamiento | Otra vintage/reconstrucción; nunca reemplazar `*_spliced` automáticamente |
| `Ind_empleo_1958_2018(1).xlsx` | Documento histórico sectorial con hojas 1958–2011 y 2002–2018 | Ancla de tendencia histórica; sus series no son mensualidades sectoriales oficiales |

**Punto no resuelto:** las series `vacancies` y `*_spliced` en `indicadores_mensuales_1993_2003.csv` requieren una genealogía histórica adicional; no se pueden regenerar con solo `Indicadores Económicos Externos Mensuales.xlsx`. Tampoco se ha demostrado la producción *desde Excel primario* de `senales_historicas_23_y_donantes.csv` ni `proxies_anuales_ventanas_2026_08.csv`. Recuperar la selección Pareto no equivale a recuperar esas dos tablas fuente.

## 3. Contraste con instituciones publicadoras

Páginas externas verificadas (referencias institucionales, **no cotejo numérico mes a mes** con los libros locales):

- Banco de la República, [Series estadísticas históricas de Colombia](https://www.banrep.gov.co/es/estadisticas-economicas/series-estadisticas-historicas-colombia); ver [TRM y sector externo](https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas/tasas-cambio-sector-externo) y [IPC, IPP y UVR](https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas/precios-inflacion).
- DANE, [Proyecciones y retroproyecciones de población](https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion); revisar **vintage censal y cobertura** antes de usar cifras actualizadas.
- DANE, [ficha de series históricas GEIH](https://www.dane.gov.co/files/operaciones/GEIH/fmet-GEIH.pdf): cambios ENH→ECH→GEIH requieren empalme documentado. Una coincidencia de nombres de variables no valida equivalencia de fuentes.
- DANE, [históricos del Índice de Producción Industrial](https://www.dane.gov.co/index.php/estadisticas-por-tema/industria/indice-de-produccion-industrial-ipi/indice-de-produccion-industrial-ipi-historicos): indicador moderno sujeto a bases y cobertura, no intercambiable sin prueba con índice histórico 1993–2003.

La presencia de las mismas variables en un sitio oficial **no demuestra** que los libros del proyecto provengan de esa exacta versión, ni que sus valores sean idénticos a los datos revisados actualmente. Para eso se necesitan URLs/descargas y comparaciones directas con la vintage de origen.

## 4. Auditoría ejecutable

```powershell
python -m icml operations audit-historical-lineage `
  --root .. `
  --report ..\auditorias\H30_lineage.json
```

Es una operación read-only salvo el reporte JSON en un **archivo nuevo fuera del checkpoint**; compara las fuentes Excel, verifica Pareto y notifica fuentes alternativas. Ni esta auditoría ni la selección de donantes actualizan por sí mismas el ICML.

## 5. Reglas para operación posterior

La persona usuaria administra Excel originales y nuevas vintages autorizadas. Las cinco transformaciones certificadas en H29 siguen vigentes. Los CSV heredados sin productor Excel demostrado permanecen en una capa `historical_derived_frozen`, con hash, hasta que su cadena primaria se pueda reproducir. **Nunca** se rellenan con un Excel alternativo por tener encabezados similares.
