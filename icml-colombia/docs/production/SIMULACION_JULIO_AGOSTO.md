# Simulación julio → agosto de 2026 (cadena laboral)

Reproducible con `tools/release/simulate_july_august.py`. Usa solo los anexos
que ya están en `datos/1_ingesta` (GEIH de julio y de agosto de 2026) y no
modifica el proyecto: copia las fuentes a una carpeta de trabajo, arma la
vintage de julio con el mismo procedimiento que la de agosto (anexo de julio,
56 ventanas, último mes 2026-07, proxies urbanos de 7 ventanas) y compara.

## Qué se comprobó con cifras reales

**1. Revisiones del DANE entre los dos anexos.** Se compararon con los mismos
lectores que usa el cálculo: todos los meses nacionales desde 2001 y las
ventanas móviles de las 32 ciudades.

| Fuente | Observaciones (julio / agosto) | Revisiones en años congelados | Revisiones en 2026 |
|---|---|---|---|
| Nacional mensual | 1.842 / 1.848 | 0 | 0 |
| Ventanas de 32 ciudades | 10.752 / 10.944 | 0 | 0 |

La diferencia entre columnas es exactamente el mes nuevo (6 cifras nacionales;
32 ciudades × 6 conceptos). Entre mayo de 2025 y agosto de 2026 tampoco hay
revisiones: estos anexos se comportan como "solo se agrega". La compuerta sí
detecta una cifra alterada (empleo de mayo de 2024 +1.000 personas → `BLOCKED`).

**1b. Revisiones en el anexo de Empleo Informal y Seguridad Social** (la
segunda fuente de la regla de dos anexos), con el extractor que usan los
modelos de informalidad: ventanas móviles de 3 meses de 25 bloques de ciudades
y 3 nacionales, 3 medidas cada una.

| Publicación previa → agosto 2026 | Observaciones | Cambios en años congelados | Estado |
|---|---|---|---|
| Julio 2026 (may–jul) | 5.460 → 5.544 | 0 | PASS |
| Enero, febrero, marzo 2026 | 4.956–5.124 → 5.544 | 0 | PASS |
| Diciembre 2025 | 4.872 → 5.544 | 0 | PASS |
| Septiembre 2025 | 4.620 → 5.544 | 252 ventanas agregadas | BLOCKED |
| Mayo 2025 | 4.284 → 5.544 | 588 ventanas agregadas | BLOCKED |
| Abril, mayo, junio 2026 | no legibles | — | rechazadas por el extractor |

Las dos publicaciones de 2025 quedan bloqueadas porque **todavía no traían las
ventanas de 2025** (año que hoy está congelado); ninguna cifra publicada fue
revisada. Los anexos de abril, mayo y junio de 2026 traen **un hueco** en la
ventana 23 del total nacional (dic 2022 – feb 2023: ocupados, formales e
informales), que el DANE restituyó en julio (22.064, 9.306 y 12.758 miles de
personas). El extractor los rechaza en vez de imputar. Por eso la compuerta
bloquea también las cifras **agregadas** dentro de un año congelado, no solo
las revisadas o eliminadas: llenar un hueco de 2023 cambia lo que la fuente dice
de un año congelado.

**2. Qué cambiaría un recálculo ingenuo en los años anclados.** Si la vintage
de agosto simplemente reemplazara a la de julio, cambiarían, **solo en
2021–2025**:

| Producto | Celdas congeladas que cambian | Por año |
|---|---|---|
| Ciudades | 11.829 | ~2.365 |
| Departamentos | 40.066 | ~8.010 (20 columnas × 33 departamentos × 12 meses) |
| Nacionales | 380 | ~76 |

Antes de 2021 no cambia ninguna celda. En departamentos el empleo se mueve hasta
3.035 personas (0,4 %) y el desempleo hasta 928 personas (2,1 %). Es el efecto
de que cada ventana nueva re-identifica los meses latentes desde 2021.

**3. El injerto.** Con el año ancla en 2025: 13.068 filas congeladas se toman de
julio y 264 filas abiertas (2026) de agosto, y **0 celdas congeladas cambian**.

## Hallazgo: la conciliación no cierra julio con la compuerta actual

La vintage de julio falla en la etapa de conciliación con
`Annual anchor not kept: labor_population_reconciled`. La causa es **numérica,
no metodológica**: una sola celda de 437 (Valle del Cauca, 2020) queda a
0,000131 personas del ancla, frente a una tolerancia de 0,0001. Es un error
relativo de ~3e-11. La compuerta (`anchor_tolerance_persons = 1e-4`) está en
una escala incompatible con el IPF (`ipf_tolerance = 1e-9`, relativa); agosto la
cumple por margen estrecho.

**Decisión (2 de noviembre de 2026):** solo se considera alarmante una
diferencia de 1e-3 personas; 1e-4 es demasiado restrictivo. Los umbrales de
auditoría `national_tolerance_persons` y `anchor_tolerance_persons` de
`configs/rc1/reconciliation.toml` pasan de 1e-4 a 1e-3 (igual que
`joint_tolerance_persons`). Son umbrales de la compuerta: **no alteran ningún
valor calculado**. Con ellos, la vintage de julio cierra sin ningún override.

Quedan otras tolerancias de 1e-4 en el código (`departmental.toml`, constantes
de linealización e integración). No fallaron en julio y no se tocaron; si un mes
nuevo falla en una de ellas, se aplica el mismo criterio.

## Qué NO cubre esta simulación

* Solo la cadena laboral (nacional, urbano, departamental, integración,
  modelado, conciliación, calidad). **Informalidad (H5/H6/H9) y sectorial (H16)
  no se simularon como vintage**, aunque su anexo fuente sí se comparó: sus calendarios siguen siendo constantes del módulo
  (`FROZEN_CUTOFF`, `N_MONTHS`) y hay que convertirlos en parámetros.
* La vintage de julio es una **reconstrucción**: usa el anexo de julio y el
  código actual, no la salida que se habría publicado en julio.
* Ninguna cifra publicada fue **revisada** en estos anexos. La compuerta
  quedó probada con una cifra alterada y con un caso real de cifras
  **agregadas** (el hueco de 2023), no con una revisión de valores.
* El anexo departamental anual solo tiene una publicación (2025), así que no
  hay nada que comparar.

## Vintage de julio de los 8 productos (laboral + informalidad + sectorial)

Construida con `tools/release/build_vintage_root.py` y `ICML_CUTOFF=2026-07`
sobre una raíz de proyecto "como estaba en julio" (anexos de julio, paneles
recortados, manifiestos resellados). La corrida integral completa los 8
productos y la **auditoría cruzada interna da PASS** (métricas ~1e-5 personas,
como en agosto). La comparación con los productos congelados de agosto no
aplica a otro corte y se informa como `NOT_APPLICABLE_DIFFERENT_VINTAGE`.

**Qué cambiaría un recálculo ingenuo (agosto reemplaza a julio), por producto:**

| Producto | Celdas congeladas que cambian | Primer año afectado | Tras el injerto |
|---|---|---|---|
| Laboral nacional / departamental / ciudades | 380 / 40.066 / 11.829 | 2021 | 0 |
| Informalidad nacional / departamental / ciudades | 4.283 / 122.691 / 72.814 | **1993** | 0 |
| Sectorial nacional / departamental | 7.596 / 510.924 | **1993** | 0 |

En informalidad y sectorial un recálculo ingenuo reescribe **toda la
historia**, no solo desde 2021 (la retropolación nacional depende de los meses
re-identificados). La magnitud es pequeña: tasa de informalidad nacional y
departamental ≤ 0,05 pp en todas las épocas (hasta ~10.900 personas informales
a nivel nacional); ciudades ≤ 0,005 pp antes de 2021 y ≤ 0,16 pp de 2021 a 2025;
participaciones sectoriales departamentales ≤ 0,19 pp. El congelamiento por año
deja todo esto en 0.

**Bloqueos reales que la corrida de julio destapó y que ya están resueltos**
(todos eran suposiciones de agosto escondidas): 8 ventanas fijas para 2026,
`range(…, 2027)`, 660 señales, 192 proxies, 68 meses recientes, 66 ventanas de
13 ciudades, 140 meses sectoriales, el nombre del anexo de informalidad, un rol
del registro con el mes en el nombre, los conteos y el hash de la instantánea en
`informality.toml`, y la comparación estricta de H5/H6 contra lo congelado (ahora
solo es obligatoria para el corte congelado). Ver también el cuadre del residuo
de 2021 en `NOMBRES_Y_CORTE.md`.
