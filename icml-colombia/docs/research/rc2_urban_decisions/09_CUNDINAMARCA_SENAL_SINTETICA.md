# 09 · Señal urbana sintética de Cundinamarca (25): rectificación y auditoría

## Problema corregido

La extensión histórica anterior omitió el código 25 por no ser una ciudad observada. Fue un error de migración: **la metodología original sí había creado la unidad sintética** para que Cundinamarca tuviera un predictor urbano propio en la reconstrucción departamental. En el histórico de entrada, `dep_code=25` contiene las columnas `*_geih` clonadas de **Bogotá, código 11**, y en las columnas originales (`employed`, `unemployed`, etc.) contiene las anclas departamentales de **Cundinamarca 2021–2024**. El campo `Region` conserva la etiqueta Bogotá por su procedencia; NO significa que el nivel territorial de la unidad 25 sea Bogotá.

## Decisión metodológica

1. **Donante fijo 11 (Bogotá).** Sus seis trayectorias anuales 2007–2024 se usan únicamente como señales de *tendencia*. El catálogo y el factor por variable están congelados en [`config/cundinamarca_25_donante_congelado.json`](../config/cundinamarca_25_donante_congelado.json) con hash SHA-256 del histórico de referencia.
2. **Receptora 25 (Cundinamarca).** Sus magnitudes anuales 2021–2024 proceden de anclas departamentales incluidas en el proyecto. La escala de cada variable se calibra con `SeriesSplicer(method="ratio")` de `tempdisagg==0.6.3`, en el mismo solapamiento fijo 2021–2024. En 2007–2020 se obtiene la trayectoria anual sintética del receptor. Cambiar el anexo mensual no cambia el donante ni la calibración.
3. **Retropolación 1993–2006.** Los seis indicadores nacionales homólogos, cada uno por separado, extienden la serie a enero de 1993, anclados a la referencia sintética de 2007.
4. **Coherencia estadística.** Proyección mínima de seis señales a cuatro componentes no negativos. Los originales quedan intactos y se conservan sus columnas sin conciliar. Los valores oficiales 2021–2024 se guardan adicionalmente sin modificación.
5. **Resolución mensual.** Entre 2007 y 2024 se transfieren las variaciones intraanuales del Nacional y se normalizan a la cantidad anual sintética o ancla oficial. Es un **perfil mensual inferido**, no mensualidad GEIH urbana observada de Cundinamarca.

## Auditoría y evidencia visual

| Comprobación | Resultado |
|---|---:|
| Período mensual de la señal 25 | Enero 1993 – diciembre 2024 |
| Registros de la unidad 25 | 384 |
| Panel integrado con ciudades 1993–2020 | 33 señales × 336 meses = 11.088 filas |
| Donante de comportamiento | Bogotá (11) |
| Anclas propias para calibración | 2021, 2022, 2023 y 2024 |
| Ajuste máximo de un ancla oficial | 0,765 personas |
| Mayor conciliación relativa anual | 0,866 % |
| Desajuste máximo contable antes de 2007 | 0,568 % del valor directo |
| Identidades y no negatividad | Cumplen |

![Trayectoria de la unidad 25](../experimentos/05_retropolacion_nacional_1993/exports/visualizacion/05_cundinamarca_sintetica/01_senal_completa.png)

![Donante normalizado frente a receptor](../experimentos/05_retropolacion_nacional_1993/exports/visualizacion/05_cundinamarca_sintetica/02_tendencia_bogota_vs_cundinamarca.png)

![Estabilidad de factores 2021–2024](../experimentos/05_retropolacion_nacional_1993/exports/visualizacion/05_cundinamarca_sintetica/03_estabilidad_calibracion.png)

## Limitaciones y criterio para avanzar

El patrón de Bogotá es una **hipótesis de transferencia temporal**, no prueba de identidad estructural con Cundinamarca. Las razones Cundinamarca/Bogotá cambian entre 2021 y 2024 —especialmente en desocupados—, por lo que se documenta la estabilidad del factor y se conserva el carácter experimental del resultado. Se requiere comprobar su utilidad como señal en la etapa B; **no se ejecuta ni se afirma resuelta la reconstrucción departamental**.

## Archivos

- [`cundinamarca_25_urbana_sintetica_mensual_1993_2024.csv`](../experimentos/05_retropolacion_nacional_1993/cundinamarca_25_urbana_sintetica_mensual_1993_2024.csv)
- [`senales_urbanas_33_incluye_cundinamarca_sintetica_1993_2020.csv`](../experimentos/05_retropolacion_nacional_1993/senales_urbanas_33_incluye_cundinamarca_sintetica_1993_2020.csv)
- [`cundinamarca_25_anclas_oficiales_inalteradas.csv`](../experimentos/05_retropolacion_nacional_1993/cundinamarca_25_anclas_oficiales_inalteradas.csv)
- [`cundinamarca_25_calibracion_bogota_2021_2024.csv`](../experimentos/05_retropolacion_nacional_1993/cundinamarca_25_calibracion_bogota_2021_2024.csv)
- [`manifest_cundinamarca_sintetica.json`](../experimentos/05_retropolacion_nacional_1993/manifest_cundinamarca_sintetica.json)

Regenerar: `python fases/02_ciudades/src/retropolacion_nacional_1993.py` o solo la unidad 25 mediante `python fases/02_ciudades/src/cundinamarca_sintetica.py` desde la raíz del proyecto.
