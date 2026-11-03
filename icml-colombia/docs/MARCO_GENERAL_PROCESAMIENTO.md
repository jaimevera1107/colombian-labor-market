# MARCO GENERAL DE PROCESAMIENTO DE DATOS — ICML 2.0

2026-11-03 · versión 2.3.0.dev0. Su complemento, con la matriz de trazabilidad, las brechas y las recomendaciones, es
[INFORME_TRAZABILIDAD.md](INFORME_TRAZABILIDAD.md).

## 1. Objetivo y alcance

El ICML 2.0 (paquete `icml-colombia`, versión 2.3.0.dev0) produce series mensuales de mercado laboral, informalidad y empleo por sector para los 33 territorios de Colombia, desde 1993-01 hasta el último mes con anexos DANE disponibles (hoy 2026-08), en dos universos: **censo** (territorio completo, población del CNPV 2018) y **GEIH** (la parte del territorio que la GEIH representa).

- **Entradas:** anexos DANE en Excel (mercado laboral mensual de la GEIH, informalidad en trimestre móvil, mercado laboral departamental anual), referencias históricas (ENH 1993-2001, proyecciones de población, PIB e ISE, anexos sectoriales de 2015), el CNPV 2018 y parámetros congelados (puente censal, priors del modelo de informalidad, características del modelo sectorial).
- **Productos:** ocho tablas internas —laboral, informalidad y sectorial, cada una en nacional, departamentos y ciudades (el sectorial sin ciudades)— que se entregan separadas por universo, en versión completa con trazabilidad y en versión sencilla.
- **Unidades:** territorio-mes. Departamentos = 32 departamentos y Bogotá (aditivos al nacional); ciudades = 33 dominios urbanos de la GEIH (señales no aditivas); sectorial = 15 sectores.
- **Alcance del procesamiento:** recepción y validación de anexos, preparación de fuentes, estimación laboral, empalme de 2001-01, estimación de informalidad, estimación sectorial, auditoría cruzada y entrega. Los resultados son de investigación: no son estadísticas oficiales, el sectorial es experimental y la publicación no está autorizada por el propio sistema.

## 2. Procesos obligatorios

Una ejecución válida recorre nueve procesos en este orden; cada uno depende de los anteriores y cualquier falla bloqueante detiene la ejecución sin publicar nada.

1. **Recepción y planificación.** Se comparan las huellas (hashes) de la ingesta y de los parámetros congelados con las de la última entrega. Se detectan los anexos, se fija el corte en el último mes con los dos anexos mensuales y se verifica que cada libro declare por dentro el mes que indica su nombre. El plan resulta `EJECUTAR`, `SIN_CAMBIOS` o `BLOQUEADO`.
2. **Preparación de fuentes.** Nueve extractores convierten los Excel en tablas auditadas y se arma una vista inmutable de fuentes laborales con su manifiesto. Los nueve deben terminar sin error.
3. **Cadena laboral.** Siete etapas encadenadas: nacional; urbana y departamental, que dependen de la nacional; integración; modelación; conciliación jerárquica; y calidad. Producen las tres bases laborales (nacionales, departamentos y ciudades).
4. **Reconstrucción laboral de 1993-2000.** Dibuja la población en edad de trabajar como una recta que termina en el valor oficial de 2001-01 y da a las tasas de 1993-2000 la dinámica de la etapa GEIH (ruido determinístico y patrón estacional oficial), con identidades exactas; reemplaza al empalme de la PET de 2.3.0. Las identidades contables cierran exactamente y los meses oficiales no cambian.
5. **Regeneración de la secuencia de informalidad (H5/H6).** Reconstruye la serie nacional latente y la secuencia urbana desde los anexos y el laboral nuevo, y la compara con la secuencia congelada.
6. **Cierre de informalidad (H9).** Calibra cada mes los priors departamentales al objetivo nacional, deriva ciudades y nacionales en los dos universos y aplica el empalme de 2001-01.
7. **Estimación sectorial (H16/H17).** Predice la composición sectorial por territorio, la concilia con el empleo laboral y la exporta como producto experimental.
8. **Auditoría cruzada.** Verifica la coherencia de los ocho productos entre sí y los compara con la vintage de referencia.
9. **Consolidación y entrega.** En modo anclado injerta los años congelados desde la vintage vigente; luego divide por universo, verifica la entrega y la promueve como vigente. Los archivos sencillos se generan después, desde la entrega ya verificada.

## 3. Reglas específicas por fuente o componente

Todas las fuentes se registran con su hash y se leen desde la ingesta; lo que cambia por fuente es cómo se identifica el período y qué la bloquea.

| Fuente | Rol | Período | Regla particular | Bloquea si |
| --- | --- | --- | --- | --- |
| Anexo mensual GEIH (mercado laboral) | Totales nacionales y ventanas urbanas | Último mes del cuadro nacional, leído del libro | Fija el corte junto con el de informalidad | Falta su par, el contenido declara otro mes o dos archivos distintos reclaman el mismo mes |
| Anexo de informalidad | Ventanas trimestrales móviles nacionales y urbanas | Fin de la última ventana | Las ventanas incompletas se rechazan | En modo anclado, aparecen cifras nuevas o revisadas en años congelados |
| Anexo departamental anual | Anclas anuales de los 33 territorios | Último año cubierto | Define los años que el modo anclado congela (hoy hasta 2025) | Las anclas no cierran dentro de la tolerancia de la etapa |
| Referencias históricas (ENH 1993-2001, población, PIB e ISE, anexos sectoriales de 2015) | Reconstrucción anterior a la GEIH y señales auxiliares | Fijo | Catálogo con hashes; los `.xls` binarios nunca deciden el corte | Falta un archivo del catálogo o cambia su hash |
| CNPV 2018 y parámetros congelados | Universo censo, puente entre universos y priors | Fijo | Se reutilizan sin reentrenar | En modo anclado, cambia su huella |

**Modalidades.** El modo **anclado** (por defecto) recalcula todo pero conserva intactos los años cubiertos por el anexo departamental, injertándolos desde la vintage vigente. El modo **total** reescribe la serie completa y exige confirmación explícita; se usa tras un cambio metodológico. Un corte anterior a la vintage congelada se reconstruye con una herramienta aparte, no con el recálculo ordinario. Un mes posterior a 2026-08 se bloquea aunque estén los dos anexos, porque no está definida la extensión de los parámetros congelados a meses nuevos.

## 4. Tratamientos y transformaciones

El sistema no elimina registros por calidad: completa cada territorio-mes por reconstrucción o estimación con procedencia declarada, y conserva vacíos solo donde la magnitud no existe.

| Tratamiento | Qué hace | Tipo | Aplicación |
| --- | --- | --- | --- |
| Normalización | Períodos `AAAA-MM`, códigos DANE de dos dígitos, nombres de anexos sin tildes ni espacios | Formato | Obligatoria |
| Conciliación contable | Anclas anuales nacionales y departamentales; los 33 departamentos suman exactamente al nacional (programación cuadrática y ajuste proporcional) | Corrección determinística | Obligatoria |
| Empalme ENH→GEIH y desagregación temporal | Lleva la historia anual de 1993-2001 a meses (Chow-Lin) y transfiere la estacionalidad de la GEIH | Estimación | Obligatoria |
| Ventanas a meses | Recupera valores mensuales latentes de las ventanas móviles publicadas y controla saltos inverosímiles | Estimación | Obligatoria |
| Reconstrucción urbana | Donantes para las nueve ciudades sin historia GEIH (2007-2020), retropolación 1993-2020 y señal sintética de Cundinamarca | Estimación por semejanza | Obligatoria |
| Modelos departamentales | Tasas para los territorios sin observación directa, con validación cruzada geográfica | Imputación basada en modelos | Obligatoria |
| Linealización de la PET | Tratamiento de curvatura mínima de la población en edad de trabajar reconstruida | Corrección determinística | Obligatoria |
| Representatividad | Factores que separan el universo GEIH del universo censo | Derivación | Obligatoria |
| Informalidad | Serie nacional latente y secuencia urbana desde los anexos; priors de un modelo neuronal congelado calibrados mes a mes al nacional; tres escenarios para el hueco de 2020 (uno elegido, dos como sensibilidad) | Estimación e imputación por modelo | Obligatoria |
| Puente censal | Refresca sus niveles desde el laboral vigente cuando difieren en más de 1e-3 personas; el universo GEIH se reconstruye con los factores congelados | Corrección determinística | Condicional |
| Residuo 2020-2021 | La diferencia entre departamentos y nacional se registra y se absorbe por la tasa; solo bloquea si supera el 1 % del empleo | Conservación documentada | Condicional |
| Sectorial | Meses calendario observados, inversión de promedios móviles, homologación 1993-2001, priors departamentales y conciliación por entropía | Estimación experimental | Obligatoria |
| Empalmes de 2001-01 | Desplazan el tramo anterior a 2001 al nivel del régimen anclado (tasa de informalidad; proporción PET con tasas laborales intactas) | Estimación | Condicional (activos desde 2.3.0) |
| Universo GEIH sin representación | Donde la GEIH no representa a nadie (9 territorios, 2001-2013) los niveles son 0 y las tasas quedan vacías, con estado explícito | Conservación de ausentes | Obligatoria |

Los parámetros congelados (puente censal, priors del modelo de informalidad, características sectoriales) nunca se reentrenan durante una ejecución.

## 5. Validación, trazabilidad y control de calidad

Un resultado es aceptable solo si supera todas las compuertas bloqueantes; las comprobaciones de diagnóstico y de evidencia científica independiente se registran pero no detienen la ejecución.

**Compuertas bloqueantes**

| Momento | Control | Límite |
| --- | --- | --- |
| Recepción | Par de anexos del mismo mes, período del contenido igual al del nombre, sin archivos ambiguos | Exacto |
| Plan anclado | Huella de los parámetros congelados sin cambios; insumos existentes modificados solo con autorización expresa | Exacto |
| Preparación | Los nueve extractores terminan correctamente | 9 de 9 |
| Etapa nacional | Identidades anuales y mensuales; desplazamientos relativos de la reconstrucción | 1 persona; 10 % anual, 15 % mensual |
| Conciliación | Cierre nacional, conjunto y de anclas | 1e-3 personas |
| Calidad laboral | Identidades contables de las tres bases | 1e-5 personas |
| Informalidad | Secuencia regenerada equivalente a la congelada (desde 2001-01 con la reconstrucción laboral); controles requeridos de completitud e identidades PEA y PET | Tolerancias de la comparación |
| Empalme de informalidad y reconstrucción laboral | Identidades PEA = ocupados + desocupados y PET = PEA + inactivos exactas; PET recta de 1993 a 2000; meses oficiales idénticos; proporciones dentro de (0, 1] | 1e-6 personas en las identidades; 1e-9 (5e-4 en el nacional ICML) en las proporciones |
| Auditoría cruzada | Coherencia entre laboral, informalidad y sectorial (empleo, identidades formal e informal, sumas departamentales) | 1e-3 personas; participaciones 1e-8 |
| Modo anclado | Ninguna celda de un año congelado cambia tras el injerto | Exacto |
| Entrega | 36 comprobaciones: hashes, formas, identidades entre universos y cobertura completa | 36 de 36 |

**Trazabilidad.** Cada etapa escribe sus artefactos con el hash SHA-256 de entradas y salidas y un manifiesto de ejecución. La corrida integral deja un informe con el estado de cada componente. Cada entrega guarda en su manifiesto el hash de cada archivo, el mapa de columnas, la versión del software, las huellas de los insumos y los métodos activos. Las carpetas de salida deben ser nuevas: el sistema se niega a sobrescribir. El repositorio completo lleva además `SHA256SUMS`, que permite comprobar que cualquier copia está completa e intacta.

**Reproducibilidad.** Las dependencias están fijadas, las lecturas y escrituras son deterministas y la regresión compara cada etapa con 102 referencias RC1. Con los empalmes apagados, la recalculación reproduce byte a byte los ocho productos de la vintage de agosto de 2026; dos corridas con la misma configuración también coinciden byte a byte.

## 6. Consolidación y generación de resultados

La entrega se construye solo después de que la recalculación termina en estado limpio y la auditoría cruzada pasa.

1. **Productos de partida.** Tres bases laborales de la etapa de calidad, tres de informalidad del cierre H9 y dos sectoriales de la capa experimental.
2. **Injerto (solo modo anclado).** Para los años cubiertos por el anexo departamental se toman las cifras de la vintage vigente y para los años abiertos las recalculadas; después se comprueba que ninguna celda congelada cambió.
3. **División por universo.** Cada producto se reparte según una especificación declarativa:
    - el universo **censo** recibe los niveles completos;
    - el universo **GEIH** recibe los representados, sus tasas derivadas y el estado de cobertura de cada departamento-mes;
    - el nacional GEIH laboral es la cifra publicada por el DANE, con la suma de departamentos representados como diagnóstico;
    - las ciudades son la misma serie en ambos universos.
4. **Manifiesto y verificación.** Se escriben el manifiesto, la verificación de 36 comprobaciones y el informe de la recalculación en una carpeta fechada (hora de Bogotá) que nombra el corte y el modo.
5. **Promoción.** Los ocho productos pasan a ser la vintage vigente, que el siguiente recálculo anclado tomará como referencia de los años congelados.
6. **Archivos sencillos.** Se cortan de la entrega ya verificada: solo fecha, año, mes, territorio y las variables de cada dominio, en CSV y XLSX, sin columnas de trazabilidad.

| Producto | Proviene de | Universo censo | Universo GEIH |
| --- | --- | --- | --- |
| Laboral nacional | Calidad + reconstrucción laboral | ICML completo | Publicado por el DANE |
| Laboral departamentos | Conciliación + calidad | Niveles completos | Representados y tasas derivadas |
| Laboral ciudades | Integración + calidad | Señal urbana | Igual |
| Informalidad (3 niveles) | Cierre H9 + empalme | Completo | Universo representado |
| Sectorial (nacional y departamental) | Predictor H16 + capa H17 | Completo | Proxy representado |

## 7. Condiciones generales de cumplimiento

- **Orden:** los procesos se ejecutan en la secuencia de la sección 2; ninguna etapa consume salidas de una etapa que no terminó correctamente.
- **Inmutabilidad:** la ingesta y los parámetros congelados no se modifican durante una ejecución; cada ejecución escribe en carpetas nuevas y nunca sobrescribe una entrega.
- **Conservación:** los 33 departamentos suman al nacional; se cumplen las identidades PET = PEA + inactivos, PEA = ocupados + desocupados y ocupados = informales + formales.
- **Cobertura:** cada producto tiene los 33 territorios y todos los meses desde 1993-01 hasta el corte; los únicos vacíos permitidos son los de territorios sin representación en el universo GEIH.
- **Trazabilidad:** todo archivo de entrega tiene su hash en el manifiesto, y el manifiesto registra versión, insumos y métodos activos.
- **Control de cambios:** un cambio que altere cifras publicadas de años cerrados es metodológico. Exige versión nueva, nota metodológica, registro de cambios y recálculo en modo total. Un cambio en los parámetros congelados bloquea el modo anclado.
- **Reproducibilidad:** con la misma ingesta, los mismos parámetros y la misma configuración, los productos son idénticos byte a byte.

**Criterio de ejecución completada.** Una ejecución se considera correctamente completada cuando se cumplen todas estas condiciones:

1. El plan resultó `EJECUTAR` sin bloqueos.
2. Los nueve extractores y todas las etapas superaron sus compuertas.
3. La recalculación terminó en estado auditado (o auditado con empalmes, siempre que haya un empalme activo) y la auditoría cruzada pasó.
4. En modo anclado, ninguna celda congelada cambió.
5. La entrega superó las 36 comprobaciones, con cobertura completa en sus 16 archivos.
6. El manifiesto quedó escrito y los productos se promovieron a vigente.

Para la vintage congelada sin empalmes, se exige además identidad byte a byte de los ocho productos con la referencia.
