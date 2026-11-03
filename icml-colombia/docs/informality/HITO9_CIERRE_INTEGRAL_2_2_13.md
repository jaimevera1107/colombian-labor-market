# ICML 2.2.13.dev0 — Hito 9, cierre computacional de informalidad

**Cobertura:** enero de 1993 — agosto de 2026 (404 meses). 33 señales urbanas, 33 departamentos completos y dos nacionales. **Estado:** cierre computacional verificado; estimación reconstruida de investigación, NO cifra oficial DANE, NO certificada para difusión como observación oficial.

## Decisión operativa

- **Un solo universo rector:** departamento completo, anclado a la población ajustada CNPV 2018.
- **GEIH como dominio derivado:** coeficientes versionados específicos para cada variable laboral. `completo = representado + complemento` para los seis componentes laborales.
- **Un diseño neuronal:** MLP residual de 92 variables, pesos históricos y recientes separados por cambios de definición (NO dos redes entrenadas por universo).
- **Cierre:** KL de mínima divergencia sobre la tasa del departamento completo; informal+formal=ocupados fijos en cada departamento. El GEIH se deriva mediante el factor de **ocupados**, no el de población, y su tasa nacional **no se fuerza artificialmente** a igualar la tasa completa.
- **Año 2020:** prior por interpolación retrospectiva, probado previamente frente a pseudohuecos y conservado como **no observado**. Se incluyen resultados por estacionalidad 2019 y perturbación urbana como sensibilidad.

## Productos nuevos

Ubicación: `informalidad/cierre_integral_v013/`.

| Archivo | Registros | Lectura correcta |
| --- | ---: | --- |
| `13_ciudades_33_1993_2026_RECONSTRUIDAS.csv` | 13.332 | Señales urbanas NO aditivas; 23 dominios con ventanas DANE y diez señales adicionales; cabeceras de nueve departamentos con escala censal paralela |
| `13_departamentos_33_dos_universos_1993_2026_RECONSTRUIDOS.csv` | 13.332 | Departamentos completos y subconjunto GEIH, tasas e informales/formales y complementos |
| `13_nacionales_2_universos_1993_2026_RECONSTRUIDOS.csv` | 808 | Nacional completo calibrado y nacional GEIH derivado con coeficientes |
| `13_ciudades_serie_anual.csv` | 1.122 | Promedio mensual de ocupados e informales, tasa ponderada por ocupados; 2026 parcial |
| `13_departamentos_serie_anual.csv` | 1.122 | Igual, 33 departamentos |
| `13_nacionales_serie_anual.csv` | 68 | Igual, dos universos |
| `13_2020_alternativas_33_departamentos.csv` | 1.188 | 3 escenarios × 12 meses × 33 departamentos |
| `13_puerta_calidad.csv` | 34 | Puerta numérica, evidencia independiente y alertas temporales |
| `13_auditoria_mensual_de_cierre.csv` | 404 | Residuo del nacional completo, brecha de tasa GEIH derivada y ajustes KL |
| `13_resumen.json`, `manifest.json` | 2 | Metadatos y hashes reproducibles |

**Importante:** el nacional NO se construye sumando las 33 ciudades. Bogotá, sus áreas metropolitanas y la señal sintética Cundinamarca no forman particiones aditivas. Solamente se suman los 33 departamentos completos. La señal censal urbana ajustada no sobrescribe la ocupación urbana original: se publican ambas escalas con etiquetas.

## Puerta computacional

- **28/28 controles obligatorios aprobados**.
- 33×404 ciudades, 33×404 departamentos, 2×404 nacionales, sin tasas nulas; 2020 cubierto explícitamente como reconstrucción.
- Residuo máximo del nacional ICML (informales): **5.59e-09 personas**.
- Desviación media absoluta de la tasa GEIH derivada frente al margen del nacional reconstruido completo: **0.189 pp**; máximo: **0.260 pp**. No constituye error frente a una observación DANE independiente.
- Ambas identidades laborales `ocupados+desocupados=PEA` y `PEA+inactivos=PET` verificadas en ambos universos.
- Nueve cabeceras capitales de 2018: error máximo respecto al censo ajustado **2.9e-11 personas** sobre el promedio mensual del ancla geográfica.
- **328 cambios mensuales urbanos y 4 departamentales por encima de cinco puntos porcentuales**, diagnostico no certificado.
- En 2020 los tres priors producen una diferencia máxima departamental de **12.242 pp** luego de cierre nacional. La incertidumbre del año debe acompañar los resultados.
- **11 productos idénticos en dos ejecuciones**; **242 pruebas unitarias aprobadas y 6 omitidas** (ver archivo de pruebas).

## Puertas científicas todavía no demostradas

No confundir un cierre exacto con exactitud estadística del territorio. Permanecen explícitamente **sin certificar** cuatro controles: la identificación del puente entre definiciones pre-2021/2021+, observaciones mensuales comparables para 2020, mediciones de informalidad del complemento departamental no cubierto y una tasa nacional GEIH independiente del margen ICML reconstruido. Esas restricciones son estructurales de la fuente, no se resuelven imponiendo que dos universos tengan una misma tasa.

### Interpretación de las dos definiciones

1. Antes de 2001: modelo histórico sin ventanas numéricas suficientes; GEIH solo proxy geográfico.
2. 2001–2006: anclas agregadas de 13 ciudades (viejos criterios T5/T10); no son equivalentes automáticamente a la nueva GEIH.
3. 2007–2019: evidencia de ventanas DANE antiguas en 23 ciudades; mensualidades invertidas/reconstruidas, no observadas.
4. 2020: puente temporal con tres escenarios auditados.
5. 2021–agosto de 2026: nueva metodología, ventanas móviles; niveles mensuales latentes de DANE, no observaciones mensuales puntuales.
6. GEIH 2001–2013: los nueve territorios especiales tienen cobertura representada cero según cronología del puente; nunca dividir por su coeficiente. No convertir proxy retrospectivo en una observación GEIH.

## Ejecución

Desde `icml-colombia/` (con dependencias instaladas):

```bash
icml informality finalize-block --root .. --output ../informalidad/nueva_corrida_v013
```

El comando no sobrescribe resultados existentes; para ensayar otro 2020 indicar `--gap-method seasonal_2019` o `--gap-method urban_shock` con otra carpeta de salida. Las tres bases laborales en `insumos/laboral/` mantienen los SHA-256 de 2.2.12; el nuevo producto es una capa derivada, no un reemplazo silencioso.
