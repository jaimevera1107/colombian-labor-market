# Reconstrucción laboral 1993-2000: PET lineal y componentes (versión 2.4.0)

Restaura dos propiedades de la reconstrucción histórica que se perdieron al migrar las etapas, siguiendo la estimación
nacional original del autor (`1 - Estimación Nacional.ipynb`, secciones 2.7 y 2.8). Es un cambio **metodológico**, no
parte del refactor de equivalencia: reescribe la historia anterior a 2001-01 de las tres bases, de la informalidad y del
sectorial. Desde 2001-01 **las series nacionales no cambian**; los departamentos y las ciudades solo cambian en su PET,
población e inactivos (ver «Después de 2001»).

## Qué se perdió

| Propiedad | Antes (2.3.0) | Ahora (2.4.0) |
|---|---|---|
| **PET de 1993-2000** | Curva de curvatura mínima que conserva las ocho medias anuales de la ENH (ADR-006): se desvía hasta 3,65 % (827 mil personas) de una recta y cambia de sentido 6 veces en el nacional | Recta exacta, de su nivel inicial al valor oficial de 2001-01. Desviación 0, ningún cambio de sentido, en el nacional, los 33 departamentos y las 33 ciudades |
| **Componentes de las tasas de 1993-1999** | Seis veces menos estacionalidad y cinco veces menos volatilidad que la etapa GEIH (desempleo: Δ mensual 0,59 pp frente a 1,28 pp; patrón estacional 1,85 pp frente a 3,2 pp) | Dinámica de la etapa GEIH (desempleo de la referencia nacional: Δ mensual 1,30 pp, patrón estacional 3,43 pp; el notebook daba 1,25 y 3,41) |

La PET es una proyección demográfica: no puede subir y bajar. La ADR-006 la forzaba a respetar las medias anuales de la
ENH, que no son colineales (la ENH salta 9 % en 1996 por su rediseño), y de ahí salían las subidas y bajadas.

## Qué hace

Para cada serie (la referencia nacional, cada departamento y cada ciudad), con sus propios meses oficiales:

1. **PET lineal.** De la mediana de su primer año a su valor en 2001-01, con una sola pendiente a través del empalme.
2. **Niveles sobre la PET lineal**, conservando las tasas TO y TD: `ocupados = TO × PET`, `PEA = ocupados / (1 − TD)`.
3. **Plantillas.** STL del componente irregular de TO y TD oficiales (2001 en adelante).
4. **Ruido determinístico** en TO y TD, a escala `scaling_factor = 0,45` del irregular oficial. La semilla es
   `base_seed + MD5("AAAA-MM")` (el territorio agrega su código para no compartir sorteo): un mes recibe siempre el mismo
   ruido, sin importar el orden.
5. **Cambio del componente estacional** de ocupados y desocupados por el patrón 2001-2018 de esa serie, escalado por
   `media_previa / media_referencia`, conservando su tendencia e irregular STL.
6. **Cierre contable exacto:** `PEA = ocupados + desocupados` e `inactivos = PET − PEA`.

7. **Población lineal** antes de 2001, en el nacional, los departamentos y las ciudades (como en el notebook).

El ICML nacional es la suma de los departamentos. Los archivos solo reescriben las celdas que cambian.

## Después de 2001: PET y población de los territorios

Después de 2001-01 las series nacionales son oficiales y no se tocan, pero la **PET de los departamentos tiene serrucho**
(mediana de 153 cambios de sentido en 308 meses, saltos de hasta 24 % de un mes a otro) mientras la nacional es lisa
(ninguno), y la de las ciudades también (92). La población territorial es más lisa pero se quiebra cada enero. Una
proyección demográfica no se comporta así. Con `smooth_territories`:

* **Departamentos:** se suaviza la **participación** de cada uno en el total nacional con una curva de curvatura mínima que
  conserva su media anual. Es un operador lineal que lleva una constante a sí misma, así que las 33 participaciones siguen
  sumando 1 y los departamentos siguen sumando exactamente el ICML nacional. Se multiplica de vuelta por el total.
* **Ciudades:** se suaviza su propio nivel con el mismo operador (no suman a nada).
* **Ocupados, desocupados y fuerza de trabajo no cambian**; los inactivos absorben la PET (`inactivos = PET − PEA`), y las
  tasas de ocupación y participación se recalculan sobre la PET nueva. La tasa de desempleo no cambia.
* **Universo GEIH.** Los territorios que la GEIH representa por completo toman el valor suavizado (su factor sigue siendo
  exactamente 1, así que no cambian de clase de cobertura); los parcialmente representados absorben su propio cambio, y los
  no representados siguen en cero. Mientras todos los territorios estén al menos parcialmente representados (desde 2014-01)
  la suma de lo representado sigue siendo el nacional GEIH, exacta (2e-8 personas). Antes de 2014, cuando nueve territorios
  están fuera de la GEIH, esa suma (informativa) puede moverse hasta 11 mil personas.
* **El serrucho está en nueve territorios.** Arauca, Casanare, Putumayo, San Andrés, Amazonas, Guainía, Guaviare, Vaupés y
  Vichada absorben casi todo el ruido de la conciliación (su total tiene 184 cambios de sentido; el grupo de los otros 24
  tiene 2). Por eso se suaviza primero el reparto entre ambos grupos y luego cada grupo por dentro.
* El suavizado va **primero**: la recta de antes de 2001 termina en el valor suavizado de 2001-01, no en el serrucho original.

No es una recta literal: una sola recta de 2001 a 2026 no puede conservar las medias anuales ni sumar al nacional oficial,
que tampoco es recto. Es la curva más recta que cumple esas dos condiciones (2 cambios de sentido en lugar de 153).

## En qué se aparta del notebook (y por qué)

| Notebook | Aquí | Motivo |
|---|---|---|
| Ruido en TO, TGP y TD por separado; cambio estacional de PEA e inactivos por separado | Ruido en TO y TD; PEA es la suma e inactivos el resto; TGP queda implícita | El notebook dejaba `PEA − (ocupados + desocupados)` desviada hasta **357 mil personas**. La compuerta de calidad exige 1e-5 |
| Población también en línea recta | Igual, antes de 2001 (`linearize_population = true`); después de 2001 se suaviza en los territorios | Se pidió así |
| Serie desde 1991-11 | Desde 1993-01 | El proyecto empieza en 1993 |
| PET plana un mes en 2000-12 → 2001-01 | Pendiente única a través del empalme | Evita un codo de un mes |
| Solo la serie nacional | El mismo método en cada departamento y ciudad | Cada territorio recibe su estacionalidad real. Propagar el cambio del nacional a los territorios atenuaba el ICML a 70 % |

## Reemplaza al empalme de la PET (2.3.0)

La recta anclada en el valor oficial de 2001-01 ya cierra el salto de la proporción PET/población que estimaba
`labor_base_splice` (+1,6 puntos en un mes). Correr ambos movería el nivel desde el que arranca la recta, así que son
**excluyentes**: la corrida falla si los dos están activos. `labor_base_splice.toml` queda en `enabled = false` y se
conserva para reproducir 2.3.0. El empalme de la informalidad (`regime_splice`) sigue vigente.

## Resultado medido (vintage de agosto de 2026)

| Medida | Antes | Después |
|---|---|---|
| Desviación de la PET respecto de una recta, 1993-1999 (nacional) | 827 mil (3,65 %) | 0 |
| Desempleo, Δ mensual 1993-1999, ICML | 0,26 pp | 1,21 pp (2001-2010: 1,26 pp) |
| Desempleo, Δ mensual 1993-1999, referencia nacional | 0,65 pp | 1,28 pp |
| Salto de la PET en 2000-12 → 2001-01 | +2,25 % | +0,28 % (un mes de pendiente) |
| Residuo contable máximo | — | menor a 4e-9 personas |
| Suma de los departamentos frente al ICML | exacta | exacta |
| Salto de la informalidad nacional en 2001-01 | +0,32 pp | +0,32 pp (sin cambio) |
| PET departamental después de 2001, cambios de sentido (mediana de 33) | 153 | 2 |
| PET de las nueve territorios fuera de la cobertura completa, cambios de sentido | 155 a 191 | 0 a 18 |
| Población departamental después de 2001, cambios de sentido (mediana) | 6 | 2 |
| PET y población departamentales antes de 2001, cambios de sentido | 15 y 14 | 0 y 0 |
| Suma de los departamentos frente al ICML después de 2001 | exacta | exacta (error de 3e-8 personas) |
| Media anual de la PET departamental después del suavizado | — | cambia a lo sumo 0,017 % |
| Clases de cobertura GEIH (completa, parcial, sin representación) | 7.392 / 1.368 / 1.404 celdas | iguales (0 celdas cambian de clase) |

Los niveles de ocupados cambian entre −2,3 % y +2,1 % según el año respecto de 2.3.0 (el cambio de PET se traslada a los
niveles porque las tasas se conservan). Las participaciones sectoriales no cambian (1e-12); los ocupados por sector suman
exactamente los ocupados laborales.

## Límites

* **El suavizado de los territorios mueve cifras del periodo oficial.** La mediana del cambio de la PET departamental es
  0,18 % y el percentil 99, 2 %; el máximo, 12,7 %, ocurre en seis celdas de Chocó en 2020, donde el original traía un pico.
  La población cambia hasta 3,2 %; en las ciudades 4,1 % y 3,3 %. Las medias anuales casi no cambian (0,017 %) y los totales
  nacionales no cambian.
* **Efecto indirecto en el sectorial.** La integración sectorial (H16) usa la PET y los inactivos departamentales como
  márgenes, así que después de 2001 las participaciones sectoriales de los departamentos se mueven poco: mediana de 0,003
  puntos, percentil 99 de 0,15 puntos y máximo de 0,40 puntos (Vichada, sector agropecuario, 2021-07). Las del nacional no
  cambian (1e-12).
* **Redondeo.** En informalidad y sectorial, columnas que no cambian (ocupados, desocupados, informales) difieren en el
  último dígito del texto (hasta 1e-6 personas): se vuelven a derivar con otro orden de operaciones. La cifra es la misma.
* **Las medias anuales de la ENH de 1993-2000 ya no son anclas.** La PET deja de respetarlas por diseño y los niveles
  anuales de ocupados y desocupados varían hasta un par de puntos porcentuales; las tasas de la ENH sí se conservan.
* **El ruido y la estacionalidad son generados**, no observados. Dan a la historia la dinámica de la etapa GEIH, pero no
  informan de lo que ocurrió mes a mes en 1993-1999: son un recurso de continuidad, no evidencia.
* **El ICML tiene menos ruido de ocupación que la referencia** (Δ mensual de TO 0,84 pp frente a 1,26 pp): el ruido de los 33
  departamentos es independiente y al sumarse se diversifica. Es la diferencia natural entre un agregado de muestras
  pequeñas y una cifra nacional.
* **La informalidad de 1993-1999 no gana dinámica mensual propia** (Δ mensual de la tasa 0,13 pp): su tasa sigue siendo la
  retropolada y solo cambian los conteos, que son tasa × ocupados.
* La corrida nacional original del notebook usa su propia desagregación mensual; aquí la entrada es la serie nacional ya
  reconciliada de la etapa nacional, así que los niveles difieren del Excel del notebook entre −8 % y +7 % según la
  variable y el año, mientras que la forma (PET recta, volatilidad, estacionalidad) coincide.

## Parámetros

`configs/rc1/labor_reconstruction.toml`: `linearize_population = true`, `smooth_territories = true`, `scaling_factor = 0.45` (el del notebook), `base_seed = 42`, STL de periodo 12
con ventana estacional 13 y robusto, patrón de referencia 2001-2018, piso de seguridad de 5 % por nivel (no se aplicó en
ningún caso en la corrida de agosto).

## Para revertir

1. Poner `enabled = false` en `labor_reconstruction.toml` (y, si se quiere el empalme de 2.3.0, `enabled = true` en
   `labor_base_splice.toml`).
2. Recalcular en modo total: `python -m icml recalcular --root . --modo total --confirmar-total`.

Con la restauración apagada y el empalme de la PET encendido, la vintage coincide byte a byte con la de 2.3.0.

## Verificación

`tests/unit/test_labor_reconstruction.py` (41 pruebas): la PET es una recta exacta y pasa por el ancla con una sola
pendiente; las identidades cierran; el ruido de un mes no depende del orden; el intercambio estacional da a un segmento
liso el patrón de referencia; los tres productos (departamentos, ciudades, nacional) quedan coherentes y el ICML es la
suma de los departamentos; desde 2001-01 el nacional es idéntico y los territorios solo cambian PET, población e inactivos; el suavizador conserva las medias anuales y deja pasar rectas y constantes; la configuración se valida, y el empalme de la PET y
esta restauración no pueden correr juntos. Sobre los productos congelados reales: PET recta, 33 departamentos y
sin pisos aplicados.
