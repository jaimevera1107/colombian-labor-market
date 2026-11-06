# Hito 10 — Inventario DANE GEIH 2007–2014 y contrato de retropolación sectorial

**Corte:** 1 de noviembre de 2026. **ICML:** 2.2.16.dev0.

## Decisión institucional del proyecto

Se descarta el uso de microdatos GEIH como dependencia del bloque sectorial.
La reconstrucción debe respetar la prioridad: fuentes DANE mensuales auténticas,
series con soporte de 3 meses, series anuales y estimaciones diferenciadas.
Ningún promedio móvil se convierte en observación mensual. Ningún desdoblamiento
CIIU se supone determinado sin una regla documentada y una fuente compatible.

## Qué se recuperó efectivamente

- El índice oficial GEIH documenta **70 publicaciones de anexos** para 2007–2014:
  2007 (abril), 2008 (febrero), 2009 (8 publicaciones), 2010–2014 (12 por año).
- Se verificaron individualmente los enlaces directos para diciembre de 2009–2014,
  febrero 2008 y abril 2007. Los demás están registrados por su índice oficial.
- Los **valores sectoriales de 2007–2014 no se pudieron extraer**: la herramienta
  de consulta no permite recuperar los XLS antiguos como datos tabulares en este entorno.
  Por ello `10_anclas_historicas_CON_TRAZABILIDAD.csv` está vacío y la puerta sigue bloqueada.
- Se recuperó del paquete original del usuario el anexo antiguo DANE **diciembre 2015**,
  `anexo_empleo_dic_15.xls`, sin alterar sus bytes: SHA-256 `5e532c30a9f96df88ded4f3b5ec0fab8e981c9cfcb284840814cf95bdd9d2ada`.
  Su estructura sectorial y cobertura **no se han inspeccionado todavía**.
- Se conservan intactas las **140 mensualidades** de 13 grupos DANE 2015–2026.
  El grupo combinado B+D_E y el residual `No informa` siguen diferenciados.
- El anexo antiguo de 14 ramas usado en ensayos previos es de *trimestre móvil*,
  no 14 estimaciones sectoriales mensuales directamente observadas.

## Identificabilidad y reconciliación entre dominios

1. Usar el archivo histórico original con su hash y documento DANE.
2. Determinar explícitamente `period_start`, `period_end`, `temporal_support`
   (`calendar_month`, `moving_3m`, `annual`), `domain`, `ciiu_revision`, `unit`.
3. Conservar ramas originales aunque no sea posible mapearlas a las 14 finales.
   `mapping_status=UNMAPPED`/`AGGREGATE_ONLY` impide atribuirles códigos falsos.
4. Reconciliar en la ventana/ámbito de la fuente; si corresponde CIIU Rev3,
   no hacer un 1:1 automático hacia CIIU Rev4.
5. En solapamientos homogéneos, contrastar observaciones y fijar regla de vintage:
   *no reemplazar los meses observados de 2015–2026*.
6. Estimar explícitamente lo no identificado en 2007–2014, y posteriormente 1993–2006.
   El objetivo sectorial total debe respetar los ocupados ICML censal completo;
   solo después se deriva el universo GEIH con el puente ocupacional del ICML.
7. Controlar filas y columnas del reconciliador RAS; no usar los ocupados de otro
   universo ni sobrescribir el resultado de la conciliación.

## Contrato CSV del importador

Archivo opcional `--annex-csv` con campos:
`source_id,source_file,source_sha256,source_url,source_review_status,domain,ciiu_revision,source_branch,mapped_sector_code,mapping_status,period_start,period_end,temporal_support,value,unit`.

Para promover a ancla, el archivo debe estar disponible en `--source-files`,
coincidir el SHA-256, tener revisión explícita `source_review_status=REVIEWED_OFFICIAL_ANNEX`
y un mapeo `mapping_status=DIRECT_VERIFIED` compatible con las 14 ramas.
Las observaciones históricas de trimestres móviles pueden ser anclas de su
**ventana original**, pero no pasan la puerta de ancla mensual directa.

## Ejecución

```bash
icml sectoral historical-annexes \
  --recent-monthly ../sectorial/hito10_mensual_v001/10_observaciones_oficiales_mensuales_13_grupos.csv \
  --output ../sectorial/hito10_historicos_v003
```

Con antiguos anexos inspeccionados y transcritos:

```bash
icml sectoral historical-annexes \
  --recent-monthly ../sectorial/hito10_mensual_v001/10_observaciones_oficiales_mensuales_13_grupos.csv \
  --annex-csv ../insumos/sectorial/anexos_historicos/observaciones_normalizadas.csv \
  --source-files ../insumos/sectorial/anexos_historicos \
  --output ../sectorial/hito10_historicos_v004
```

**Advertencia:** el módulo consolida observaciones normalizadas; aún requiere
lector/plantilla específica para el diseño de las hojas XLS históricas.
No debe confundirse esa parte pendiente con una serie 2007–2014 consolidada.

## Fuentes y procedencia

- Archivo oficial DANE: https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo/geih-historicos
- Anexo DANE diciembre 2014: https://www.dane.gov.co/files/investigaciones/boletines/ech/ech/anexo_empleo_dic_14.xls
- Anexo DANE diciembre 2013: https://www.dane.gov.co/files/investigaciones/boletines/ech/ech/anexo_ech_dic13.xls
- Anexo DANE diciembre 2012: https://www.dane.gov.co/files/investigaciones/boletines/ech/ech/anexo_ech_dic12.xls
- Anexo DANE diciembre 2011: https://www.dane.gov.co/files/investigaciones/boletines/ech/ech/anexo_ech_dic11.xls
- Anexo DANE diciembre 2010: https://www.dane.gov.co/files/investigaciones/boletines/ech/ech/anexo_ech_dic10.xls
- Anexo DANE diciembre 2009: https://www.dane.gov.co/files/investigaciones/boletines/ech/ech/anexo_ech_dic09.xls
- Anexo DANE febrero 2008: https://www.dane.gov.co/files/investigaciones/boletines/ech/ech/anexo_ech_feb08.xls
- Anexo DANE abril 2007: https://www.dane.gov.co/files/investigaciones/boletines/ech/ech/anexo_ech_abr07.xls
