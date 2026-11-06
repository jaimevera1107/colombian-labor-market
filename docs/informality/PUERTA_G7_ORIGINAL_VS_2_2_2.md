# Puerta G7 — Auditoría metodológica de informalidad antes de entrenar

**Corte:** 2026-11-01 · **Versión:** 2.2.3.dev0, auditoría únicamente. **Estado:** NO CERTIFICADO. No modifica el proyecto laboral ni sus CSV de informalidad.

## Comprobación sobre las fuentes originales

Se revisó el notebook original `2 - Estimación Departamental.ipynb` dentro de `ICML_Original_Produccion_Integral` y su integración `src/icml_v2/informalidad_original_integrada.py`.

| Secuencia requerida | Evidencia original | Qué hace 2.2.2 | Puerta |
|---|---|---|---|
| 1. Informalidad de las 13 áreas | `OldInformalityExcelParser`, `NewInformalityExcelParser`, `InformalityConsolidation`, `InformalityRetropolarizer`, `SeasonalityUnifierCities`, `CityInformalityPostprocessor` | El candidato genera las 33 señales a la vez, utiliza 6 anclas **agregadas** de 13 áreas 2001–2006 T5; hay evidencia T10 individual 2005–2006 solo como contraste | **Pendiente:** etapa separada, 13 series auditadas y su agregado, antes de usarlas para el nacional |
| 2. Informalidad nacional histórica | `InformalityBackcastEstimator`, `ModelSelector`, `PostAdjusterNationalInformality` y los agregados del anexo | Nacional experimental con señal DANE 13 áreas y proxy de pensiones; nacional `DANE_REFERENCIA` e `ICML_COMPLETO` comparten tasa provisional | **Precaución:** puente de definiciones, universo nacional, validación independiente |
| 3. Informalidad 23 ciudades extendida con el nacional | `SplicingInformalityCities` utiliza `informals_nat`/`formals_nat` como señales de extensión mediante `Retropolarizer(method='linear_regression')`, además del empalme urbano anterior | 2.2.2 construye las 23 ciudades desde sus ventanas y dona a diez señales adicionales, **pero no hace la segunda extensión nacional→23 después del nacional** | **Pendiente: dependencia metodológica omitida** |
| 4. Panel ciudad–departamento y clústeres | `LaborMarketRateCalculator` + ratios de población urbana/rural + clústeres + `national_unemployment_rate` | No existe matriz de diseño para informalidad 2.2.2; sólo CSV de tasas/cantidades urbanas y nacionales | **Pendiente** |
| 5. Predicción departamental | `MLPConfig`, `MLPInformality`, evaluación, entrenamiento con ciudades y predicción en departamentos | No hay MLP ni validación nueva LOGO/temporal, ni una comparación contra trasladar directamente la señal urbana | **Pendiente** |
| 6. Conciliación de informalidad | `InformalityProcessor`: participaciones de informales/formales y calibración contra el nacional | No hay producto departamental de informalidad 2.2.2; el original no es automáticamente compatible con los ocupados/factores congelados 2.1.2 | **Pendiente: conciliador restringido que deje ocupados invariables** |

**Matiz de secuencia:** el notebook original realiza un primer empalme de fuentes urbanas antes de estimar el nacional, y después vuelve a extender ciudades empleando el nacional. No sería correcto describir el original como un único paso de retropolación. La secuencia solicitada 13→nacional→23→predicción debe materializarse como dependencias **separadas** y verificables, respetando ese doble papel.

## Qué pruebas sí aprobó 2.2.2

- Hay 33 señales urbanas × 404 meses y dos nacionales × 404 meses sin nulos de informalidad formal e informal; el denominador `employed_frozen` coincide con las bases laborales. Eso comprueba **completitud aritmética**, no capacidad predictiva.
- Las ventanas oficiales recientes se reconstruyen en su dominio original, pero la inversión de ventanas móviles no identifica de forma única los meses subyacentes. No hay observaciones mensuales GEIH directas en esos puntos.
- Las seis anclas T5 agregadas de las trece áreas, 2001–2006, no identifican por sí solas tasas T5 para cada una de las 13 ciudades. **No se deben exigir datos que el DANE no publica.** Se debe evaluar su inferencia mediante anclas realmente disponibles, capacidad de extrapolación y sensibilidad a donantes.
- No se pueden mezclar valores individuales T10 con agregado T5 ni informar que `DANE_REFERENCIA` y `ICML_COMPLETO` son tasas observadas equivalentes.

## Auditorías nuevas y reglas de interpretación

- **G0 Fuentes:** procedencia, año, ventana y definición; comprobación hash de todos los insumos.
- **G1 Completitud:** claves únicas, calendario 1993–2026, tasas en [0,1] y seis columnas laborales congeladas.
- **G2 Etapa 13 áreas:** fidelidad al agregado T5, error al ocultar una ancla; no confundir con validación individual.
- **G3 Nacional:** sensibilidad del puente urbano–nacional y diferencias de universo; no adoptar mismos niveles por conveniencia.
- **G4 23 ciudades:** anclas disponibles, donantes y verificación de segunda extensión mediante nacional.
- **G5 Dinámica:** ventanas móviles, cambios mayores a 5 puntos porcentuales intermensuales, 15 pp interanuales, aumentos mayores al 200 % o disminuciones a menos de un tercio del nivel anterior, contrastes de medias móviles pre/post 12 meses mayores a 5 pp. Candidatos a ruptura **no** son errores confirmados ni deben corregirse automáticamente.
- **G6 Predicción:** disponibilidad de rasgos laborales, variables urbanización/ruralidad y clústeres, sin fuga; MLP y línea base urbana comparados con ocultamiento territorial y después del cierre.
- **G7 Cierre:** `informales + formales = ocupados` para 33 departamentos y ambos nacionales, respetando factores. Ningún ajuste modifica ocupados, PET ni población.

## Orden de corrección recomendado

Primero materializar **13 áreas** como un resultado reproducible propio, con reglas de anclaje y diagnóstico. Segundo, generar **nacional** y validar su transferencia de definición/universo. Tercero, construir **23 ciudades** a partir de su evidencia y nacional, y donar a las diez restantes. Cuarto, construir **panel predictivo**, entrenar y comparar modelos con la línea base; por último, conciliar los **33 departamentos** sin cambiar mercado laboral.

Estas etapas son trabajo posterior: la auditoría presente NO afirma que ya fueron implementadas.

## Ejecución de la auditoría en el paquete

```bash
icml informality audit-historical \
  --candidate RUTA/informalidad/hito6_urbano_hito5_revision_nacional_v001 \
  --cities-labor RUTA/insumos/laboral/ciudades.csv \
  --nationals-labor RUTA/insumos/laboral/nacionales.csv \
  --previous-national RUTA/2_2_1/national_informality_1993_2026_experimental.csv \
  --output RUTA/auditoria_secuencia_informalidad_v001
```

El código de retorno **2** indica que alguna puerta está bloqueada (el resultado metodológico sigue experimental); no implica que los CSV estén corruptos.
