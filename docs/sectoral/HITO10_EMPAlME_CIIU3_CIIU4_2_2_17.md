# ICML 2.2.17.dev0 — Hito 10: puente sectorial de vintages 2001–2015

**Ámbito:** anexo DANE GEIH de marzo de 2015 (`anexo_empleo_mar_15.xls`, SHA-256 `bd808ab6a5f2a1323862e79febfbd3f1151747a4180c04aa52065c0404587aa2`), la extracción numérica del mismo vintage y los 140 meses sectoriales **realmente mensuales** de enero de 2015 a agosto de 2026. **No utiliza microdatos**.

## Alcances confirmados

- **2001-09 a 2015-03:** 163 trimestres móviles observados por el DANE con **10 agrupaciones CIIU Rev. 3 y `No informa`**, incluido el nacional y ámbitos urbanos (13 ciudades individuales). No son 163 meses sectoriales observados.
- **2015-01 a 2026-08:** 140 mensualidades directas de **13 grupos CIIU Rev. 4 A. C.** con `B+D+E` combinado y `No informa` aparte. No son 14 ramas observadas directamente.
- **2015-01 a 2015-03:** período común válido solo al comparar la ventana histórica **enero–marzo** con el promedio de los tres meses del **mismo ámbito** de la versión reciente. La escala ocupacional del vintage 2015 difiere ~5,31 % frente a la versión reciente; no es un error atribuible automáticamente a ocupación reconstruida.

## Correspondencia por grupos comunes (no es equivalencia exacta de clases)

| Bloque común | CIIU Rev. 3, anexo marzo 2015 | Agrupaciones CIIU Rev. 4 |
|---|---|---|
| A | Agricultura y pesca | A |
| B_DE | Minas y canteras + electricidad, gas y agua | B + D_E (versión reciente publica `B_D_E_COMBINED`) |
| C | Industria | C |
| F | Construcción | F |
| G_I | Comercio, hoteles y restaurantes | G + I |
| H_J | Transporte, comunicaciones | H + J |
| K | Intermediación financiera | K |
| L_MN | Inmobiliarias, empresariales, alquiler | L + M_N |
| OPQ_RSTU | Servicios comunales, sociales y personales | O_P_Q + R_S_T_U |
| NO_INFO | No informa | No informa: categoría residual, no sector 14 |

**Riesgo:** cambios en CIIU entre revisiones, fronteras de actividad y reclasificaciones. Los grupos son **comparables conceptualmente, no identidades estadísticas certificadas**. El detalle de cuatro particiones internas modernas (`G/I`, `H/J`, `L/M_N`, `O_P_Q/R_S_T_U`) no se observa desagregado en los trimestres antiguos. `B/D_E` está separado en el vintage antiguo, pero no es una observación mensual Rev. 4.

## Método de empalme (tres escenarios trazables)

1. Para cada ventana histórica, dividir las cantidades antiguas entre el total **de ese mismo vintage y ventana**. Esto elimina el desajuste nominal de la escala sin llamar nuevo al valor histórico.
2. En enero–marzo de 2015, agrupar las 13 ramas recientes en nueve bloques más `No informa` y calcular las diferencias de **participación** frente al vintage 2015.
3. Obtener el factor constante de composición por bloque, `participación_reciente_2015 / participación_antigua_2015`. Probar las potencias `0`, `0.5` y `1`, renormalizando entre todos los bloques. El caso `1` coincide con los bloques actuales en 2015 **por construcción, no por validación externa**.
4. Dividir los cuatro bloques antiguos que contienen dos categorías modernas usando la proporción observada entre esas categorías en el promedio enero–marzo 2015; **esa proporción mantenida hacia atrás es un supuesto**. En `B/D_E` se mantiene la razón antigua minas/servicios públicos de cada trimestre.
5. Aplicar exactamente una composición reconstruida al universo principal de **ocupados ICML completos** y al universo derivado GEIH representado; usar como denominador la media de ocupados de los **tres meses** respectivos, nunca el valor de un mes.
6. Rechazar la atribución de `observación oficial mensual` a cualquiera de los 163 candidatos históricos y conservar la versión original de las 140 mensualidades recientes. La conversión de ventanas a mensualidades individuales no queda identificada por estas fuentes.

## Resultados y puertas

- **163** ventanas observadas CIIU 3, 140 mensualidades CIIU 4, **tres escenarios** y **dos universos**. Los candidatos suman 14 ramas **estimadas** más `No informa`; producen 14.670 filas experimentales ventana × categoría × universo × escenario.
- Las sumas sectoriales calibradas reproducen cada denominador de ocupados **de la misma ventana y universo** a precisión numérica, sin alterar los ocupados de la base laboral.
- Las diferencias entre escenarios cuantifican la sensibilidad a la corrección del vintage y a la correspondencia. **No se han recuperado 14 mensualidades observadas para 2001–2014.**
- Anomalías originales del anexo: cuatro discrepancias en Pasto/Manizales 2009; una discrepancia entre la ventana nacional de enero 2004 y el promedio de ocupados mensuales del mismo vintage. Permanecen registradas en la auditoría recibida y no se sustituyen por valores inventados.
- **No se publican como canónicas** las desagregaciones experimentales ni se utilizan como objetivos obligatorios para departamentos hasta superar una puerta de clasificación y validación temporal más sólida.

## Ejecución

Desde `icml-colombia`, con el módulo `icml` instalado o `PYTHONPATH=src`:

```bash
python -m icml.cli sectoral bridge-vintages \
  --historic-csv ../insumos/sectorial/anexos_historicos/01_observaciones_ramas_2001_2015_trimestres.csv \
  --recent-monthly-csv ../sectorial/hito10_mensual_v001/10_observaciones_oficiales_mensuales_13_grupos.csv \
  --recent-totals-csv ../sectorial/hito10_mensual_v001/10_totales_oficiales_mensuales.csv \
  --nationals-csv ../insumos/laboral/nacionales.csv \
  --source-xls ../insumos/sectorial/anexos_historicos/anexo_empleo_mar_15.xls \
  --output ../sectorial/hito10_empalme_v004
```

**Siguiente paso (Hito 11):** revisar si otras versiones de anexos ofrecen más períodos comunes y agrupaciones comparables; elegir con evidencia la desagregación de ventanas móviles a meses verdaderamente **estimados**, probarla ocultando ventanas y medir su estabilidad, sin alisar las observaciones mensuales DANE ni borrar rupturas de 2020. Después conectar el mismo esquema sectorial a departamentos con márgenes compatibles; no replicar el RAS antiguo.
