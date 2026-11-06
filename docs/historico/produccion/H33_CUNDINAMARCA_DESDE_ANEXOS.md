# ICML H33 · Procedencia de Cundinamarca desde los anexos GEIH

**Versión 2.2.33.dev0; vintage congelada 2026-08.** No se reentrenan donantes ni se modifican series laborales, informalidad ni sectoriales.

## Qué encontramos en las copias antiguas

El ZIP RC2 contiene `fases/02_ciudades/docs/09_CUNDINAMARCA_SENAL_SINTETICA.md`, el módulo antiguo `cundinamarca_sintetica.py`, las anclas oficiales 2021–2024, el catálogo de Bogotá (11) como donante de tendencia y su calibración por razón. La documentación se conservó aquí con fines de trazabilidad, **no se reutiliza su código**.

El código antiguo construía una **señal sintética de modelado** para Cundinamarca (25) usando: (a) nivel del departamento DANE 2021–2024; (b) patrón anual de Bogotá 2007–2020 trasladado por factores de razón individuales; (c) tendencias nacionales homólogas para 1993–2006; (d) perfil mensual inferido y conciliación de identidades. Es una estimación auxiliar y no una medición de la cabecera de Cundinamarca.

## Corrección del H32

El H32 estaba utilizando un JSON de 24 valores congelados como **entrada de generación**. El H33 lo reemplaza por una lectura directa de tres hojas del Excel oficial `Anexo_GEIH_Departamentos_2025.xlsx`, listado en `insumos/catalogo_fuentes.json` bajo `departmental.annex`. Sus SHA-256 se verifica antes de la preparación histórica.

* `Departamentos anual`: total de Cundinamarca; esta es la ancla histórica de escala que usó el modelo existente.
* `Departamento anual Cabeceras`: población de cabeceras de Cundinamarca, observada por el DANE en el anexo, **no** reemplaza automáticamente la ancla total del modelo.
* `Departamento anual CentrosP`: centros poblados y rural disperso; cierra con el total dentro del redondeo publicado.

Las seis cantidades en cada hoja vienen en miles de personas, y el lector convierte a personas y compara por concepto, año y dominio. Se exige cierre total = cabecera + resto con tolerancia máxima de 2 personas para redondeos, y se validan las identidades laborales por ámbito y año. Los **24 valores de la ancla total 2021–2024 coinciden exactamente** con el JSON histórico, que pasa a ser una *referencia de prueba* opcional, no una fuente de estimación.

**Ejemplo de 2024, ocupados:** total 1.711.836; cabeceras 1.349.239; centros poblados y rural disperso 362.597 personas.

La hoja departamental contiene también 2025, pero **no se incorpora a la calibración congelada 2021–2024** ni autoriza recalcular factores en una actualización ordinaria.

## Qué se verificó

* Preparación histórica de las 660 señales del H32 desde GEIH urbano + Excel departamental: PASS, 0 claves faltantes, 0 violaciones contra histórico.
* Preparación de los nueve derivados Excel del H32: PASS.
* Pruebas unitarias nuevas de lectura de los tres ámbitos, identidad y equivalencia de 24 valores.
* Batería completa disponible en esta ejecución: 381 aprobadas y 141 omitidas. No se cuentan las omisiones como aprobaciones.
* Auditoría de los ocho productos congelados: PASS; sin modificación de insumos o salidas H32.

## Otros ZIP y estado de dependencia

* RC1/RC2 aportan el origen, la motivación y los informes de donantes, sin reemplazar el código actual.
* Los ZIP H25/H26 aportan la recuperación del anexo departamental y las referencias de calibración; su código no se mezcla.
* El H31/H32 permite regenerar las señales urbanas 2007–2026 desde los anexos; la desagregación departamental 2021–2024 ahora también se rastrea hasta el Excel.
* Los seis campos `*_spliced` antiguos pertenecen a **otra vintage comparativa y no son insumos activos** del motor nacional. No deben convertirse en una dependencia artificial que el usuario tenga que actualizar.
* El mapa histórico de donantes usado para replicar el CSV 2007–2026 es distinto del catálogo Pareto de nueve receptores; los dos permanecen versionados y no se recalibran automáticamente.

El generador conserva deliberadamente la **política estadística congelada**. Si se quiere redefinir la unidad de modelado para que use cabeceras en vez del total departamental, se requiere una revisión metodológica separada y pruebas comparativas; no es una corrección automática de procedencia.

**Operación:** `python -m icml operations prepare-all-excel --root .. --output <nueva_carpeta_fuera_del_checkpoint>`.
