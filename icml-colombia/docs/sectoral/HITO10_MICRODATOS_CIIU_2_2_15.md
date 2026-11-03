# ICML 2.2.15.dev0 — Hito 10, preparación de separación mensual por microdatos

**Naturaleza:** checkpoint de infraestructura y puerta de calidad. **NO** es una serie sectorial de 14 ramas validada. Ninguna cifra laboral, informal, ni serie sectorial definitiva se modificó.

## Hallazgo de fuentes

- `insumos/sectorial/Anexo_GEIH_Agosto_2026.xlsx`: 140 **observaciones mensuales publicadas** de las 13 agrupaciones, 2015-01 a 2026-08, con `B_D_E_COMBINED` y `No informa` separado.
- **DANE 2015–2019:** `https://microdatos.dane.gov.co/index.php/catalog/661/get_microdata`, archivos anuales de clasificación CIIU Rev. 4 que **deben unirse** a Ocupados por `DIRECTORIO`, `SECUENCIA_P`, `ORDEN`. DANE: `https://microdatos.dane.gov.co/catalog/750/download/21521/Acceso_y_Uso_de_Bases_Anonimizadas-GEIH.pdf`.
- **DANE 2020–2026:** CIIU Rev. 4 (`RAMA2D_R4` o `RAMA4D_R4`) en Ocupados, con el factor de expansión válido (en Ocupados o Características generales). 2025: `https://microdatos.dane.gov.co/index.php/catalog/853/get-microdata`; 2026: `https://microdatos.dane.gov.co/index.php/catalog/900/get-microdata`.
- **Pre-2015:** catálogo histórico pendiente; no se reetiquetan trimestres móviles como meses ni se fabrican anclas mensuales. ENH/ECH y marcos GEIH requieren compatibilización posterior.

## Algoritmo de separación, solamente si existe evidencia mensual validada

Por mes, el microdato produce `s_B = sum(fex_i para CIIU 05–09) / [sum(fex_i para 05–09) + sum(fex_i para 35–39)]`. Después:

- `O_B_estimado = O_BDE_publicado_mensual * s_B`
- `O_DE_estimado = O_BDE_publicado_mensual * (1-s_B)`.

Así `B + D_E = B_D_E_COMBINED` a precisión de redondeo y **el resto de las ramas publicadas queda INTACTO**. Son **estimaciones mensuales a partir de microdatos, no cifras de las dos ramas publicadas independientemente por DANE**. El anexo oficial de 13 grupos sigue siendo la fuente única de niveles sectoriales GEIH.

## Puertas implementadas

- [x] Fecha explícita y soporte temporal = mes calendario.
- [x] 2015–2019: cruce obligatorio con CIIU externo y claves personales únicas; cero uniones muchos-a-muchos.
- [x] 2020+: admite clasificación en el módulo de Ocupados.
- [x] Factor de expansión: presente, positivo, sin imputación y sin ambigüedad entre versiones.
- [x] Divisiones CIIU: minería 05–09, servicios públicos 35–39.
- [x] Muestra >99 ocupados y >=10 observaciones de cada rama para aceptar automáticamente un mes.
- [x] Total expandido de ocupados dentro de ±5% del oficial del mes y combinado B+DE dentro de ±15%; si no, detiene el mes para revisar dominio/versión y ponderadores.
- [x] Los meses sin microdatos no obtienen división artificial: producto vacío de 14 ramas, con catálogo explícito de pendientes.
- [x] Series históricas 1993–2026 con matriz de procedencia, sin suplantar observaciones.
- [x] Fuentes y archivos originales inmutables; hashes de microdato cuando estén disponibles.

**Límites:** los umbrales son una puerta de plausibilidad y no sustituyen una reproducción exacta de la metodología DANE, ni la varianza del diseño muestral/coeficientes de variación. La diferencia entre nacional marco GEIH y total ICML completo sigue siendo de universo y se resolverá en el Hito 13, no imponiendo columnas incompatibles al RAS.

## Comando ejecutado sin los ZIP de microdatos

```bash
icml sectoral split-microdata \
 --observations-csv ../sectorial/hito10_mensual_v001/10_observaciones_oficiales_mensuales_13_grupos.csv \
 --totals-csv ../sectorial/hito10_mensual_v001/10_totales_oficiales_mensuales.csv \
 --workbook ../insumos/sectorial/Anexo_GEIH_Agosto_2026.xlsx \
 --output ../sectorial/hito10_microdatos_v002
```

**Resultado actual correcto**: 140 meses con 13 grupos originales; **cero meses con desagregación respaldada** porque no se dispone todavía de los ZIP de microdatos en el entorno. La puerta permanece `PARTIAL_REQUIRES_MONTHLY_MICRODATA`.

## Uso al incorporar microdatos DANE

Crear `insumos/sectorial/manifest_microdatos.csv` con columnas `period,occupied,classification,characteristics`. Las rutas pueden ser a CSV o a `archivo.zip::ruta_dentro_de_zip.csv`. Las rutas relativas se interpretan desde el directorio del manifiesto. Ejemplo de esquema (rutas de ejemplo, no se entregan como fuentes existentes):

```csv
period,occupied,classification,characteristics
2018-04,archivos/2018-04/Ocupados.csv,archivos/2018-04/CIIU4.csv,archivos/2018-04/Caracteristicas.csv
2026-08,archivos/2026-08/Ocupados.csv,,
```

Luego volver a ejecutar el comando anterior añadiendo `--manifest ../insumos/sectorial/manifest_microdatos.csv`. El flujo puede correr con una mensualidad o muchas, pero solo genera candidatos para los meses que pasen todas las verificaciones.

## Lo que sigue, por orden

1. Obtener los ZIP originales mensuales y los 5 archivos CIIU de 2015–2019; verificar codificación, pesos, ámbito y procedencia.
2. Extraer y validar B/D_E **mes a mes**; cuantificar error respecto a publicado, muestra y cambios entre marcos.
3. H11 recuperar 2001–2014 y anclas ENH/ECH (1993–2000), sin maquillar periodicidad.
4. H12 predictor composicional con clústeres laborales y validación temporal/territorial.
5. H13 reconciliar con los ocupados **ICML_COMPLETO** de 33 departamentos y derivar el universo GEIH con el puente censal y complemento; preservar el modelo único.

La batería unitaria del código (incluida la anterior) se comprobó en el entorno con código local de `tempdisagg`.
