# ICML 2.2.2.dev0 — Hito 6 urbano histórico y revisión experimental del Hito 5

**Fecha:** 2026-11-01  
**Estado:** `EXPERIMENTAL_NOT_CANONICAL`. Los tres productos laborales 2.1.2 permanecen inmutables.  
**Política de fuentes:** exclusivamente publicaciones y anexos históricos del **DANE** para este experimento. El trabajo de ILOSTAT del 2.2.1 se conserva como experimento anterior, **no se utiliza ni calibra esta corrida**.

## Objetivo

Reordenar la reconstrucción de informalidad: primero ventanas DANE de 23 ciudades desde 2007; después anclas de 13 áreas de 2001–2006 y retropolación histórica; finalmente usar una señal reconstruida de las **13 áreas en su propio dominio** para derivar una tasa nacional histórica, sin alterar los ocupados del Bloque I. Mantener 33 señales urbanas y los dos nacionales, 1993-01 a 2026-08, sin nulos en estimaciones esenciales.

## Fuentes y diferencias de definición (no intercambiables)

| Período | Fuente | Uso |
| --- | --- | --- |
| 1993–2000 | Método ENH y proyecciones laborales ya reconstruidas, **sin tasas urbanas numéricas ENH recuperadas** | Retropolación; evidencia muy alta incertidumbre, nunca `observado` |
| 2001–2006 | DANE ECH, **13 áreas agregadas** criterio de hasta **5** trabajadores, abril–junio anual (revisión retrospectiva 2009) | Seis restricciones agregadas sobre la señal T5; NO equivalen a seis observaciones mensuales |
| 2005–2006 | DANE ECH, 13 áreas **individuales** con cantidades de informales, y tasas individuales de 2006, criterio de hasta **10** trabajadores | Diagnóstico separado de definición; NO se impone como tasa T5 individual |
| 2007–marzo 2021 | DANE GEIH, 23 ciudades + 13 áreas agregadas, criterio T5, ventanas móviles de 3 meses | Inversión regularizada de tasas; descartar ventanas con 0 anómalo en 2020 |
| enero 2021–agosto 2026 | DANE GEIH nueva definición, 23 ciudades + 13 áreas + nacional, ventanas de 3 meses | Inversión exacta de conteos mediante mínima segunda diferencia; producto mensual **latente** |

Los catálogos CSV incluyen URL de origen por ancla. Fuentes institucionales adicionales para el régimen reciente:
- DANE: https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-informal-y-seguridad-social/empleo-informal-y-seguridad-social-historicos
- DANE: https://geoportal.dane.gov.co/servicios/atlas-estadistico/src/Tomo_II_Social/7.6.-empleo-informal.html

**Cuidado con ámbitos:** 13 áreas `DANE` ≠ suma de 13 señales urbanas `ICML`, por diferencias de niveles y denominadores; se publican las dos señales en columnas separadas. **El criterio T10 2005–2006 no se transforma automáticamente en T5 individual**. Tampoco el indicador antiguo de no afiliación a pensiones se considera observación de informalidad de definición reciente.

## Algoritmos nuevos

1. Inversión de las ventanas de T5 para cada una de las 23 ciudades, con penalización de segunda diferencia y exclusión de ceros anómalos; conserva residuales medidos y la procedencia de cada valor.
2. Retropolación a enero de 1993 con cambios de desempleo de la propia ciudad y una elasticidad acotada (parámetro asumido, no estimación oficial). Las 13 áreas principales reciben además la restricción agregada histórica DANE T5 para abril–junio 2001–2006.
3. Para 10 señales sin ventanas individuales (nueve capitales y Cundinamarca sintética), asignación explícita de donante entre las 23 ciudades según similitud laboral pre-pandemia y ajuste limitado por brecha de desempleo; el catálogo registra los donantes y su distancia, **no los presenta como cifras DANE**.
4. Para las 23 ciudades publicadas desde 2021, inversión exacta de los **conteos** de ocupados e informales de los 66 trimestres móviles en 68 mensualidades latentes con mínimo de segunda diferencia. La reconstrucción respeta el dominio DANE de esas ventanas; después se transfiere **la tasa latente** al denominador de ocupados urbano congelado del ICML. Es una inferencia, no una observación mensual.
5. Empalme entre T5 y nueva GEIH a través del período común enero–marzo 2021 usando un diferencial en logit por ciudad. El diferencial se extrapola como hipótesis histórica; es una **transferencia de definición**, no una serie histórica observada bajo la definición nueva.
6. Para el nacional, crear primero una señal DANE **13 áreas agregadas**, distinta de la tasa ponderada de 13 ciudades ICML. Antes de 2021, modelar su trayectoria usando T5 DANE más el puente estimado en 2021. Reconstruir el nacional desde enero 2021 hacia atrás con esa señal y la variación relativa auxiliar del antiguo indicador nacional sin afiliación a pensiones (peso por defecto 0,5). **No se equiparan sus niveles**. Desde 2021 se preserva, sin alteración, la tasa latente nacional del Hito 5. Para `DANE_REFERENCIA` e `ICML_COMPLETO`, usar los ocupados fijos del tipo nacional correspondiente.
7. Auditar fidelidad a fuentes, cierre, meses, definciones, discontinuidades, sensibilidad al peso nacional y validación por exclusión de un año en las anclas agregadas 2001–2006.

## Resultados reproducidos en esta ejecución

| Indicador | Resultado |
| --- | ---: |
| Señales urbanas mensuales | 33 × 404 = **13.332** |
| Nacionales mensuales | 2 × 404 = **808** |
| Ventanas urbanas T5 válidas (2007–2021) | **3.795** |
| Ventanas urbanas nuevas (2021–2026) | **1.518** |
| Error medio absoluto T5 por ventana (inversión regularizada) | **0,221 pp** |
| Error máximo absoluto T5 por ventana | **1,061 pp** |
| Error de las ventanas GEIH nuevas (inversión exacta de conteos) | Precisión numérica, **~0 personas** |
| Desviación máxima 13 áreas T5, anclas 2001–2006 con calibración | **0,060 pp** |
| MAE al ocultar cada ancla anual 2001–2006 | **0,458 pp** |
| Error máximo al ocultar una ancla anual | **1,081 pp** |
| Alertas temporales exploratorias | **328**, en ciudades |

**No es una calibración de precisión histórica total:** el ejercicio año oculto solo usa seis anclas agregadas de las trece áreas, no etiquetas individuales de los diez territorios sin información. La calidad del nacional reconstruido anterior a 2021 no puede demostrarse sin referencia nacional comparable de esa definición.

## Límite de identificabilidad y disyuntiva observada

Las ventanas móviles de tres meses no identifican por sí solas cada mensualidad. Para 2021–2026, exigir la reproducción exacta de los conteos DANE permite oscilaciones latentes de hasta **12,34 pp en un solo mes**; una regularización alternativa reduce el máximo a **7,82 pp**, pero deja error medio de **0,197 pp** y máximo próximo a **1,03 pp** en las tasas de ventana. El reporte `auditoria_tradeoff_fidelidad_suavidad.csv` detalla ambas elecciones. **Ninguna se incorpora automáticamente al producto canónico**.

El nacional anterior a 2021 varía con la contribución del indicador auxiliar de seguridad social: `sensibilidad_puente_nacional.csv` compara cinco pesos y constituye el indicador de incertidumbre de especificación, no un intervalo de confianza.

## Puertas de calidad

- **Cobertura:** completa para 33 señales, dos nacionales y las cantidades informales/formales del candidato.
- **Identidades:** `informales + formales = ocupados` del panel laboral fijo, precisión inferior a 0,001 personas.
- **DANE nuevo, 2021–2026:** ventanas reproducidas exactamente en su dominio de conteos; las mensualidades son **latentes**.
- **DANE antiguo, 2007–2021:** reproducciones aproximadas con residuales explícitos por ventana; ceros fuente anómalos se excluyen.
- **Definiciones:** todos los cambios de definición están marcados; las cifras T10 individuales y el proxy de pensión NO son anclas de la tasa reciente.
- **Publicación definitiva:** **BLOQUEADA** hasta evaluar mejor los saltos de las mensualidades latentes, el puente urbano-nacional y el universo 1993–2000. La rutina jamás sobrescribe las tres bases laborales ni el candidato anterior del Hito 5.

## Ejecución

Desde la raíz de `icml-colombia`, tras instalar las dependencias fijadas:

```bash
icml informality urban-history \
  --sources ../insumos/informalidad/informality_source_observations.csv \
  --cities ../insumos/laboral/ciudades.csv \
  --nationals ../insumos/laboral/nacionales.csv \
  --recent ../insumos/informalidad/national_informality_monthly_2021_2026.csv \
  --anchors13 ../insumos/anclas_dane/anclas_dane_agregado_13_areas_2001_2009.csv \
  --anchors-cities ../insumos/anclas_dane/anclas_dane_ciudades_13_2005_2006.csv \
  --output ../informalidad/hito6_urbano_hito5_revision_nacional_v001
```

Todos los parámetros de origen y de identificación se verifican con los hashes del manifiesto. No se ejecuta `icml run` laboral ni se altera ningún archivo de entrada.

## Pendientes fundamentados

1. Recuperar tabulaciones numéricas ENH 1994–2000 por ciudad cuando estén disponibles; su existencia metodológica no equivale a poseer cifras comprobables. **No bloquea la reconstrucción experimental**.
2. Evaluar nuevos métodos de desagregación mensual restringida que disminuyan saltos sin romper las ventanas oficiales, con pseudovintages y sensibilidad de identifiabilidad.
3. Contrastar definición de informalidad nueva y proxy nacional de seguridad social contra cualquier período de solapamiento genuinamente comparable. No extrapolar niveles sin explicar el puente.
4. Solo después, revisar si el nacional urbano-prior mejora frente al candidato 2.2.1; no promoverlo por la sola completitud del CSV.
