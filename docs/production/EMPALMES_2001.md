> **Actualización (2.4.0):** el empalme laboral de la PET descrito aquí quedó **reemplazado** por la restauración de la
> PET lineal y de los componentes (`RECONSTRUCCION_LABORAL.md`). El empalme de la informalidad sigue vigente. Esta nota
> describe lo que hizo 2.3.0 y se conserva para reproducirlo.

# Empalmes de la costura de 2001-01

**Versión:** 2.3.0.dev0. **Estado:** adoptado. **Tipo:** cambio metodológico (no es parte del refactor de equivalencia).

## Problema

En 2001-01 cambia el régimen de medición. Hasta 2000-12 los valores son reconstrucciones (ENH para el
laboral, retropolación sin ancla oficial para la informalidad); desde 2001-01 están anclados al DANE. Las dos
partes no empatan, y el escalón no es un cambio de la realidad:

* Informalidad: la tasa nacional salta +2,78 pp en un mes (3 veces el percentil 99 de los cambios mensuales),
  en las 33 ciudades y en 29 de 33 departamentos.
* Laboral: los ocupados saltan +5,19 %. Descompuesto, el quiebre real está en la proporción PET/población
  (+1,64 pp en un mes; su variación mensual normal tiene p99 de 0,06 pp). La población no tiene quiebre propio
  (+0,3 % ± 0,3 %), y las tasas TGP, TO y TD tienen saltos de un mes dentro de lo normal.

## Método

**Quiebre.** Regresión con salto y pendiente común sobre ventanas de 24 meses a cada lado:
`serie = a + b*k + delta*posterior`. Una diferencia de promedios anuales mezcla el quiebre con un año de deriva, y
la de un solo mes amplifica su ruido. El estimador es estable con ventanas de 18 a 36 meses (informalidad 2,46 a
2,55 pp; PET 1,46 a 1,61 pp); con ventanas cortas sube porque el tramo retropolado de 2000 trae una caída que no es
información. Se reporta el error estándar ajustado por autocorrelación.

**Informalidad** (`icml.informality.regime_splice`). Se desplaza el tramo anterior al quiebre una constante, con
dinámica mensual intacta: el objetivo nacional, cada ciudad y los priors de cada departamento (que luego se
recalibran al objetivo nacional, de modo que siguen sumando).

**Laboral** (`icml.pipeline.labor_base_splice`). Solo se empalma la proporción PET/población; los niveles se
reconstruyen con las tasas intactas:

    PET' = (proporción + quiebre) x población      PEA' = TGP x PET'      ocupados' = TO x PET'
    desocupados' = PEA' - ocupados'                inactivos' = PET' - PEA'

Todo nivel salvo la población se multiplica por `k = (proporción + quiebre) / proporción`, de modo que todas las
identidades y las tasas se conservan. Departamentos con quiebre propio (27 de 33 individualmente significativos); el
nacional ICML es la suma de los departamentos corregidos; la referencia DANE anterior a 2001 tiene el suyo; las
ciudades usan un quiebre común (mediana) porque su tramo 1993-2000 es una retropolación de la serie nacional y las
estimaciones individuales son ruidosas (8 de 33 significativas).

**Por qué no empalmar las tasas laborales.** Alrededor de 2000-2001 el desempleo cambia de sentido con el ciclo; un
estimador de quiebre no distingue un giro de un quiebre (daba -4,6 pp para la TD frente a -1,0 pp del salto mensual).

## Alcance

* Cambia 1993-01 a 2000-12 en laboral, informalidad y sectorial. **Desde 2001-01 todo queda idéntico.**
* No cambian la población, las tasas laborales de departamentos, ciudades y referencia DANE (2e-16), ni los
  parámetros congelados. Las tasas del nacional ICML se recalculan desde sus niveles (cambian como máximo 6,3e-5).
* Como cambia historia cerrada, la vintage se recalcula en modo total (`icml recalc --modo total --confirmar-total`).
* El puente censal sigue siendo un parámetro congelado: sus niveles departamentales se refrescan desde el laboral
  vigente cuando difieren, y su universo GEIH se reconstruye con los factores congelados.

## Resultados

| | Antes | Después |
|---|---|---|
| Quiebre de PET/población, nacional ICML | +1,56 pp | +0,01 pp |
| Quiebre de PET/población, departamentos | mediana +1,58 pp | 0,00 pp en los 33 |
| Ciudades con paso mayor que su variación normal | 27 de 33 | 0 de 33 |
| Salto de ocupados 2000-12 a 2001-01, nacional ICML | +5,19 % | +2,80 % |
| Salto de informales, nacional | +9,55 % | +3,28 % |
| Paso de un mes de la tasa de informalidad, nacional | +2,78 pp | +0,32 pp |

## Limitaciones

* La proporción PET se estima con un error de unos 0,9 pp, unos 1,4 % en los niveles de 1993-2000.
* En 8 ciudades pequeñas el estimador por ventanas muestra un residuo mayor a 0,5 pp (estimación individual no
  significativa); su paso de un mes sí queda cerrado.
* El salto de empleo que queda en 2001-01 (+2,8 %) está dentro de la variación mensual normal (mediana 1,4 %; p99 5,2 %).

## Para revertir

`enabled = false` en `configs/rc1/regime_splice.toml` y `configs/rc1/labor_base_splice.toml`, y recalcular.
Reproduce la vintage congelada de agosto de 2026 byte a byte.
