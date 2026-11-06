# ICML 2.2.8.dev0 — Hito 8: evaluación posterior al cierre de informalidad

**Estado:** EXPERIMENTAL. Ninguna estimación departamental de informalidad se promueve a las tres bases canónicas.

## Alcance

La estimación completa que se evalúa es **predicción de tasa departamental + calibración nacional**. El comparador utiliza exclusivamente las tres salidas ya calibradas de 2.2.7, el panel laboral congelado 2.1.2 y el nacional experimental de informalidad producido por la secuencia 13 áreas → nacional → 23 ciudades. No reentrena redes ni cambia las fuentes o modelos. El cierre se ajusta a dos márgenes cuando las definiciones lo permiten: ICML completo y DANE representado (desde 2001); entre 1993–2000 solo el ICML completo.

## Lo que sí queda verificado

- Identidades `formales + informales = ocupados` para cada territorio–mes, sin alterar los ocupados.
- Suma de informales ICML igual a su objetivo nacional, y suma representada igual al margen DANE desde 2001, dentro de 0,1 persona en CSV exportados.
- Comparación territorial de modelos en **392 meses comunes**, excluyendo 2020 de ambos MLP.
- Medición de desplazamiento de las tasas, cambios en posiciones relativas, oscilaciones temporales y divergencias de candidatos **después** de calibrar.
- Ablación del segundo margen: cierre ICML solamente versus cierre ICML + DANE representado, sin modificar los modelos.
- Sensibilidad del cierre a un escenario de ±1 punto porcentual de tasa nacional, **simultáneo en ambos universos**. No es un intervalo de confianza ni dos fuentes nacionales independientes.

## Resultados cuantitativos de la corrida

| Candidato | Meses | Cambio medio absoluto ponderado por ocupados | Máximo local | Fracción de meses con mismo top 5 antes/después |
|---|---:|---:|---:|---:|
| Señal urbana directa | 404 | 12,07 pp | 15,03 pp | 24,5 % |
| MLP residual, 92 variables | 392 | 16,08 pp | 22,44 pp | 24,5 % |
| MLP residual, 19 variables | 392 | 8,08 pp | 13,61 pp | 25,5 % |

En el intervalo común de 392 meses, la diferencia media absoluta entre dos distribuciones departamentales finales es de **4,14 pp** (MLP 92 vs MLP 19), **5,92 pp** (urbana vs MLP 92) y **6,03 pp** (urbana vs MLP 19). Los máximos locales ascienden respectivamente a **18,35**, **30,07** y **28,17 pp**. Que todos cumplan el nacional **no los convierte en estimaciones territoriales equivalentes**.

### Efecto independiente del segundo margen

Cuando se conserva el cierre ICML y se añade la restricción DANE representado, el ajuste medio **adicional** ponderado es 0,58 pp (señal directa), 0,46 pp (MLP 92) y 0,39 pp (MLP 19). Aun así, el orden relativo puede cambiar por diferencias entre factores territoriales: la menor correlación de rangos de Spearman al comparar solo ICML con doble cierre es 0,567, 0,371 y 0,539, respectivamente. Si se calibrara exclusivamente con ICML, la brecha frente al objetivo DANE representado alcanzaría 0,36 pp para la señal directa en los períodos evaluados. Estas diferencias NO demuestran que el segundo margen sea opcional: cuantifican su costo territorial.

### Alertas temporales

Se identifican los cambios de tasa de más de 5 pp mes a mes, distinguiendo saltos que ya existían en la predicción de aquellos introducidos por el cierre. Hay **421**, **17** y **192** combinaciones territorio–mes con ese tipo de alerta (urbana, MLP 92, MLP 19), respectivamente; de ellas **93**, **12** y **41** quedan por primera vez por encima del umbral tras el cierre. Son observaciones para revisión, no errores demostrados. No se comparan diciembre de 2019 y enero de 2021 como meses consecutivos en las MLP.

### Sensibilidad del margen

En un escenario de +1 y −1 pp **en ambas tasas nacionales**, los cambios locales máximos respecto al escenario base fueron aproximadamente **1,17 pp** (urbana), **1,10 pp** (MLP 92) y **1,16 pp** (MLP 19). La media ponderada es aproximadamente 1 pp por construcción del cambio agregado. Esto mide sensibilidad **condicionada** a conservar el modelo y las demás restricciones; no mide la incertidumbre del empalme nacional histórico.

## Lo que no se puede inferir de estos resultados

- Las tasas urbanas usadas en los pliegues de validación son latentes, no observaciones mensuales oficiales.
- La exactitud del margen después del cierre es una propiedad contable, **no error predictivo departamental**.
- Las tasas nacionales de ambos universos utilizan la misma tasa inferida: el doble margen no es una doble validación estadística independiente.
- No hay etiquetas oficiales departamentales mensuales de informalidad para validar directamente los diez territorios sin ancla. No deben exigirse.
- La validación urbana de 2.2.6 (cinco pliegues por definición) y el piloto de 2.2.7 no son equivalentes a una validación territorial después del cierre. El modelo MLP 19 tiene un piloto de **dos pliegues por definición**: no es una comparación concluyente contra los diez pliegues del MLP 92.
- La comparación retrospectiva no usa verdaderos vintages históricos de covariables. El puente de definición y los valores de 2020 siguen pendientes.

## Puerta de publicación

- G1 Integridad y calendario: **PASS** para señal directa; **BLOCKED_2020** para las MLP (12 meses).
- G2 Empleo fijo e identidades: **PASS**.
- G3 Cierres nacionales: **PASS**, a precisión de exportación.
- G4 Estabilidad territorial: **REVIEW** (saltos y rankings).
- G5 Validación geográfica: **NOT_VERIFIABLE** con etiquetas departamentales independientes; se requieren pruebas de transporte/pseudovintages, no datos inexistentes.
- G6 Comparabilidad de definiciones y universos: **BLOCKED**; no hay ancla nacional independiente para los dos universos.

**Decisión:** conservar las tres candidatas, no seleccionar ganadora ni actualizar `ciudades.csv`, `departamentos.csv` ni `nacionales.csv` de mercado laboral. La próxima iteración debe tratar la correspondencia de universos, completar un puente explícito para 2020 y evaluar el procedimiento completo con escenarios de márgenes nacionales previamente definidos y los pliegues históricos comparables. La presente puerta está creada para que esas decisiones no se tomen por el simple hecho de obtener cierre exacto.

## Ejecución

```bash
icml informality audit-postclosure \
  --closures informalidad/national_calibration_v008 \
  --departments insumos/laboral/departamentos.csv \
  --national informalidad/secuencia_v003/02_nacionales.csv \
  --output informalidad/postclosure_NUEVO \
  --sensitivity-pp 1.0
```

La ruta de salida debe ser nueva. El programa valida contratos y falla cuando faltan claves, cambia el empleo congelado o el cierre no coincide con el margen correspondiente. Genera tablas de intervención por territorio/mes, estabilidad por mes/año, comparación entre candidatas, prueba de margen simple/doble, sensibilidad y manifiestos SHA-256.
