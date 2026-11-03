# Bloque II · Hito 5 — Experimento histórico nacional (2.2.1.dev0)

## Decisión de la etapa

**NO APROBADO PARA PUBLICACIÓN COMO SERIE HOMOGÉNEA 1993–2026.** Se produjo
una reconstrucción **experimental**, completa por calendario, de informalidad
nacional en dos universos (`DANE_REFERENCIA` y `ICML_COMPLETO`). La completitud
numérica no equivale a una observación histórica y no resuelve automáticamente
la comparabilidad conceptual entre las fuentes.

Las tres bases laborales (ciudades, departamentos, nacionales), los seis niveles
laborales de cada una, los factores y el candidato reciente del hito 5 permanecen
**byte a byte inalterados**. El comando histórico no es parte de `icml run`.

## Qué información sí está disponible

1. **2007–marzo 2021**, GEIH de seguridad social: proxy de no afiliación a
   pensiones del total nacional, 169 ventanas móviles de tres meses. Cuatro
   ventanas de 2020 tienen ocupados y clasificaciones cero y **se excluyen**.
   Esta proxy **no es** la definición reciente de informalidad.
2. **2007–2019 y 2021–2024**, archivo aportado por el usuario de **ILOSTAT,
   Informal employment by sex (thousands)**, selección Colombia, sexo Total.
   El original se conserva en `insumos/ILOSTAT_Empleo_Informal_Mundo_Archivo_Original.xlsx`;
   la transcripción verificable se encuentra en `data/sources/informality/ilo_colombia_annual.csv`.
   El archivo original incluye países adicionales; la selección Colombia/Total
   se efectuó sin alterar el original. El uso de sus niveles anuales como
   promedios mensuales del año es una **hipótesis de correspondencia** y
   requiere verificar los metadatos de levantamiento. Contiene marcas *Break in series* en 2007, 2010 y 2022. Hay **ausencia de 2020**.
3. **2021–agosto 2026**, 66 ventanas trimestrales recientes GEIH y la mensualización
   latente de 68 meses del hito 5 anterior. Los ocupados del nacional DANE están fijos.

## Métodos ejecutados y su interpretación

| Tramo | Operación | Grado de evidencia | Riesgo / estatus |
|---|---|---|---|
| 1993–2006 | Escenario retrospectivo anclado a enero 2007, con posible sensibilidad a la tasa de desempleo; elección por dejar-un-año-fuera en 2007–2019 | Sin anclas directas de informalidad | Muy alto; extrapolación ilustrativa, no validada |
| 2007–2019 | Recuperar **dinámica** mensual latente de proxy antigua con regresión acotada y penalización de curvatura; ajustar nivel de cada año a la referencia anual ILOSTAT | Anclas anuales externas + proxy de diferente definición | Alto; equivalencia de definiciones no demostrada |
| 2020 | Evitar cuatro ventanas cero; adaptar la proxy recuperada con puente entre desplazamientos de 2019 y 2021Q1 | La definición reciente solo tiene un solapamiento 2021Q1 | Muy alto; no se deduce un 2020 mensual observado |
| 2021–2026 | Reutilizar intacta la mensualización de 66 ventanas GEIH | GEIH observada solo trimestral móvil | Latencia mensual, no observación directa |

Los dos nacionales comparten **una tasa experimental** por mes. Para
`ICML_COMPLETO`, multiplicarla por su total de ocupados es una **transferencia
supuestamente válida entre universos, no verificada con una encuesta**. Esta
hipótesis está marcada explícitamente y es otra puerta pendiente.

Ninguna cifra anterior a 2007 se etiqueta DANE/ILOSTAT observada.

## Validación cuantitativa de esta corrida

- 404 meses × 2 nacionales = **808 registros**; cero faltantes en
  `informal_estimated`, `formal_estimated` e `informality_rate_estimated`.
- Identidades `informales + formales = ocupados` y límites `[0, ocupados]`:
  **residuo máximo 0 personas** para ambas series, con ocupados congelados.
- GEIH antigua: **165 de 169 ventanas nacionales válidas**;
  4 ventanas con ceros de origen se excluyeron. Error medio absoluto de la
  proxy mensual suavizada sobre ventanas antiguas válidas: **0,102 pp**;
  máximo **0,344 pp**. La reproducción de esas ventanas es aproximada,
  **no exacta**, porque se impuso regularización y límites para evitar
  mensualidades negativas durante 2020.
- ILOSTAT 2007–2019: 13 promedios anuales recuperados a precisión numérica.
  **Eso es una restricción impuesta, no validación fuera de muestra**.
- Evaluación dejándolo fuera cada año de ILOSTAT al inferir su factor:
  **MAE 0,486 %**, error absoluto máximo **2,136 %**.
  Esta prueba evalúa interpolación de ajustes entre años; **no** prueba
  comparabilidad de definiciones ni el pasado anterior a 2007.
- Sensibilidad del parámetro de curvatura: 0,02/0,075/0,25; las tasas mensuales
  de la proxy cambian hasta **0,513 pp** respecto a la configuración central.
- Contraste **no usado para ajuste** ILOSTAT/GEIH latente:
  2021: −7,590 %; 2022: −0,356 %; 2023: −0,253 %; 2024: −0,428 %.
  2021 exige cautela especial: no puede tratarse como discrepancia puramente
  atribuible a error del ICML, por los marcos/definiciones.
- Exceso >3 pp mensual en tasas o >100 % interanual en cantidad informal:
  **0 alertas** en este candidato. Este resultado no demuestra adecuación causal
  ni que no se hayan suavizado cambios reales.
- En 1993–2006 el modelo seleccionó un coeficiente de sensibilidad de
  desempleo en escala logit de **1,1390**, con errores de validación anual
  retrospectiva 2,57 pp frente a 2,77 pp de la referencia plana; no existe
  validación independiente de este tramo.

## Entrega y fronteras de publicación

- `informalidad/hito5_historico_v001/evidence/candidates/national_informality_1993_2026_experimental.csv`:
  **candidato para investigación, NO base oficial ni canónica**.
- `evidence/audit/old_proxy_windows.csv`: ventanas antiguas y sus residuos.
- `evidence/audit/ilo_annual_anchor.csv`: anclas y factor aplicado.
- `evidence/audit/ilo_leave_year_out.csv`: prueba reteniendo un año.
- `evidence/audit/proxy_sensitivity.csv`: sensibilidad a regularización.
- `evidence/audit/ilo_external_comparison.csv`: comparación independiente.
- `evidence/audit/rate_jump_flags.csv`: eventos extremos detectados.
- `evidence/manifest.json`: SHA-256 de entradas/salidas, estatus experimental.

## Pendientes para cerrar Hito 5 de manera científica

1. Verificar definiciones y universo de ILOSTAT año por año contra sus metadatos,
   especialmente los cambios de 2007/2010/2021/2022; contrastar si es
   justificable usar esas series como anclas de la **definición objetivo GEIH**.
2. Someter a validación adicional el puente 2019–2021 y su sensibilidad a los
   cuatro trimestres nulos de 2020; idealmente distinguir cambios reales de
   artefactos muestrales.
3. Evaluar por separado si la tasa del dominio DANE puede transferirse sin sesgo
   al nacional `ICML_COMPLETO` que agrega los 33 territorios.
4. Extender a 1993–2006 con evidencia independiente o declarar formalmente un
   escenario de extrapolación con mayor incertidumbre, en vez de convertirlo
   en una cifra publicada sin respaldo.

**Siguiente hito:** reconstrucción de informalidad urbana (Hito 6),
con los mismos controles de estimando, ventanas, nulos anómalos,
proveniencia y desempeño frente a una referencia simple.

## Reproducir el experimento

Desde la raíz del repositorio, con la dependencia `tempdisagg==0.6.3` disponible:

```bash
icml informality historical \
  --sources data/sources/informality/informality_source_observations.csv \
  --nationals ../productos/bases/nacionales.csv \
  --recent ../informalidad/hito5_nacional_v001/candidates/national_informality_monthly_2021_2026.csv \
  --ilo data/sources/informality/ilo_colombia_annual.csv \
  --output ../informalidad/hito5_historico_v001/nueva_corrida_inmutable
```

La corrida rechaza sobrescribir una salida existente. El reporte contiene
las huellas de los archivos que efectivamente se usaron.
