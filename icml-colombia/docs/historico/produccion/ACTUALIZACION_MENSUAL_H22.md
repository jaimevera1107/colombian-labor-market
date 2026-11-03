# ICML 2.2.23.dev0 — Hito 22 · recepción de una mensualidad real

## Estado exacto (2 de noviembre de 2026)

**Código de recepción, extracción parcial y controles: implementado y probado.**
**Nueva serie mensual de septiembre de 2026: NO GENERADA.**
**Publicación de nueva vintage del ICML: BLOQUEADA.**

El DANE publicó el anexo GEIH de septiembre de 2026 el **30 de octubre de 2026**.
El archivo oficial se ofrece en:

https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIH-sep2026.xlsx

La fuente oficial de informalidad disponible al cierre de este hito es junio–agosto de 2026;
no se afirma que exista aún el anexo julio–septiembre. Fuentes de consulta:

- https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo
- https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-informal-y-seguridad-social

El entorno de elaboración **no logró descargar el XLSX de septiembre**. Por tanto,
no se extrajeron niveles oficiales ni se calculó o anexó ninguna cifra nueva al ICML.
Los valores publicados en la página del DANE (TD 8,0 %, TO 58,7 %, TGP 63,8 %)
se usan **solo como pruebas independientes de coherencia del XLSX** cuando se reciba.
Para las 13 ciudades: TD 8,3 %, TO 60,6 %, TGP 66,1 %.

## REGLA OBLIGATORIA — DOS ANEXOS DANE SINCRONIZADOS (H22b)

**Ninguna actualización mensual integral del ICML está autorizada con un solo anexo.**
La metodología requiere **ambas fuentes oficiales del DANE**:

1. **Mercado Laboral GEIH:** anexo con referencia al mes objetivo `M`.
2. **Empleo Informal y Seguridad Social:** anexo del **trimestre móvil que termina en `M`** (no un anexo mensual puntual de informalidad).

La condición de correspondencia temporal es:

`mes_referencia_GEIH == mes_final_trimestre_movil_Seguridad_Social == mes_objetivo_ICML`

Para septiembre de 2026, las fuentes válidas como par son **GEIH septiembre 2026**
y **Empleo Informal y Seguridad Social julio–septiembre 2026**. **Junio–agosto
2026 no es válido para actualizar septiembre**. Tampoco se permite tomar una
edición posterior que informe otro mes y trasladarla artificialmente a septiembre.

Si falta **cualquiera** de las fuentes, si una contiene una referencia temporal
incompatible, si la edición no está verificada o si hay revisiones que necesitan
aprobación, la puerta queda **BLOQUEADA**: no ejecutar el pipeline mensual integral,
no extrapolar informalidad, no actualizar sectores, no construir candidatos finales,
no publicar productos y **no crear una nueva vintage de resultados**.

Es legítimo **descargar y auditar por separado** el GEIH ya publicado, guardándolo en
`staging` sin producir estimaciones. Ese paso no constituye una actualización del ICML.
Los meses anteriores permanecen congelados (último corte: agosto 2026).

**Publicación de la fuente faltante:** se espera aproximadamente a mediados de
noviembre de 2026 conforme al calendario comunicado; **esta previsión no equivale
a comprobar que el DANE la haya publicado**. Debe verificarse directamente la
publicación oficial y su período de referencia antes de procesar.

El cierre de este requisito debe ser verificable: identidad de fuentes,
identificación del período real dentro de ambos XLSX, SHA-256, clasificación de
revisiones y puertas contables. La coincidencia de nombres de archivo o fechas de
publicación por sí sola **no basta**.

### Control técnico de sincronía

El comando `check-monthly-sources` bloquea ausencias y divergencias de calendario,
pero **no sustituye la extracción y verificación del contenido** del anexo de
Seguridad Social. Incluso cuando las fechas declaradas coinciden, el reporte indica
que el par aún está pendiente de esa validación; no habilita publicación.

```powershell
python -m icml operations check-monthly-sources `
  --period 2026-09 `
  --geih-annex "C:\DatosDANE\anex-GEIH-sep2026.xlsx" `
  --geih-month 2026-09 `
  --social-annex "C:\DatosDANE\anexo-informalidad-seguridad-social.xlsx" `
  --social-start 2026-07 `
  --social-end 2026-09 `
  --report "C:\ICML\auditorias\par_2026_09.json"
```

Los períodos de los parámetros deben provenir de la inspección de los anexos,
no de una suposición basada en su fecha de publicación. `intake-geih` conserva
su función exclusivamente de recepción, sin publicar ni habilitar el siguiente mes.

## Qué quedó programado

`icml operations intake-geih` audita el XLSX por SHA-256, extrae exclusivamente
las observaciones mensuales en *miles de personas* de las hojas `Total nacional`
y `Total 13 ciudades A.M.`, comprueba calendarios y cierres laborales,
contrasta las tasas publicadas y genera reportes no destructivos. Puede recibir
el XLSX anterior y comparar valores solapados, remitiendo cualquier revisión
a aprobación separada. No usa `openpyxl`, ni depende de la instalación del
motor de cómputo o de un servidor externo para extraer las celdas cacheadas.

No estima una matriz territorial, ni retropola nuevos períodos, ni actualiza
informalidad ni la sectorial, ni representa el resultado como observación
completa del universo ICML. No sobreescribe ningún insumo, modelo o producto.

### Cómo ejecutarlo cuando el XLSX se encuentre disponible

```powershell
cd icml-colombia
python -m pip install -e .
python -m icml operations intake-geih `
  --root .. `
  --period 2026-09 `
  --annex "C:\DatosDANE\anex-GEIH-sep2026.xlsx" `
  --previous-annex "..\insumos\sectorial\Anexo_GEIH_Agosto_2026.xlsx" `
  --output "..\vintages\staging_2026_09"
```

Si el archivo falta o es incompatible, el comando genera una auditoría de bloqueo
y no publica productos. El directorio de salida debe ser **nuevo**.

La extracción de agosto se ensayó con el Excel original existente: generó dos
observaciones y mantuvo intacta la base nacional congelada. La puerta de
septiembre se ejecutó y quedó `BLOCKED_OFFICIAL_XLSX_NOT_AVAILABLE_LOCALLY`.

## Siguientes controles antes de emitir septiembre

1. Disponer de la copia original verificable del XLSX septiembre GEIH.
2. Extraer y contrastar niveles de las hojas oficiales contra los datos de agosto,
   revisando eventuales cambios de historia. No tratar toda revisión como ordinaria.
3. Ejecutar reconstrucción completa de septiembre en un nuevo espacio temporal
   del ICML (nacionales, ciudades, departamentos), con identidades y cierre.
4. **Antes de cualquier actualización integral**, disponer del anexo de Empleo Informal y Seguridad Social julio–septiembre, verificar que su trimestre móvil termina en septiembre y comprobar que su contenido corresponde a la misma referencia temporal del anexo GEIH. Sin este par sincronizado la actualización se bloquea.
5. Prolongar las series sectoriales mensuales respetando la separación entre
   los 13 grupos DANE observados y la división experimental a 15 categorías.
6. Ejecutar `operations stage-update` contra cada base congelada, verificar
   históricos, registrar el delta y aprobar explícitamente la nueva vintage.
7. Ejecutar pruebas Golden con las 102 referencias originales cuando estén disponibles.

**No cambiar el estatus de investigación por disponer de un nuevo mes.**
