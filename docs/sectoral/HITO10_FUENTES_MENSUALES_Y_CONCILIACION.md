# ICML 2.2.14.dev0 — Hito 10: puerta de mensualidad y conciliación sectorial

**Fecha:** 2026-11-01  
**Resultado:** **APROBADO para las 13 agrupaciones mensuales publicadas (2015–2026)**; **BLOQUEADO para declarar 14 ramas mensuales oficiales o construir productos sectoriales finales**.  
**Universo rector de ICML:** ocupados del departamento completo, sin modificarlos.  
**Segundo universo:** GEIH representado mediante puente por dominio; nunca se reentrenan modelos paralelos por universo.

## Corrección metodológica crucial

El anexo DANE **«Anexo GEIH Agosto 2026.xlsx»** contiene la hoja
`Ocupados TN_T13_rama`, con título **«Serie mensual 2015 - 2026»**.
Se verificaron y extrajeron las **140 mensualidades enero de 2015 – agosto de 2026**,
13 grupos sectoriales publicados por mes, sus ocupados totales y la categoría
`No informa`: **1.820 observaciones sector-mes oficiales mensuales**, sin suavizamiento,
sin inversión de medias móviles y sin imputar datos mensuales de trimestres móviles.

El archivo de la fuente está incluido en `insumos/sectorial/Anexo_GEIH_Agosto_2026.xlsx`,
con SHA-256 `ade9b213c799e967c121091438a53617f3a3ab8d85d311f5cada08e2461473d9`.

Las cantidades del anexo están en miles y se convierten a personas mediante ×1.000.
El residuo máximo absoluto al sumar 13 grupos + `No informa` es de
**3 personas**, consistente con redondeo.

## Revisión cuantitativa del error antiguo

`sector_national_checks.csv` del ejecutor antiguo corresponde a **138 ventanas móviles de 3 meses**
(marzo 2015 a agosto 2026); no son 138 meses observados de rama.

| Comparación | Resultado |
|---|---:|
| MAE relativo al comparar erróneamente trimestre móvil con último mes | **1.285 %** |
| MAE en personas tras comparar ventanas de igual duración (solo auditoría) | **0.0009** |
| Error de asignar al mes de abril de 2020 el dato trimestral móvil | **+18.22 %** |
| Ocupados oficialmente estimados **abril de 2020, mes calendario** | **15,987,843** |
| Ocupados de la ventana **febrero–abril 2020**, no abril solo | **18,900,828** |

**Regla:** una media móvil puede usarse como **control de su ventana**, nunca se le cambia
la etiqueta a «dato mensual» ni se usa como señal mensual observada. El comparador
trimestral solo existe para demostrar el desajuste antiguo; no alimenta ningún predictor.

## Universos y compatibilidad

Los ocupados mensuales oficiales del anexo coinciden con `DANE_REFERENCIA` de la base
laboral congelada, con diferencia porcentual absoluta media de
**0.0000000286 %**.
La diferencia porcentual absoluta media frente a `ICML_COMPLETO` es
**2.0143 %**.
Ese 2 % aproximado es una **diferencia de dominio**, no un error que haya que resolver
reemplazando ocupados ICML por ocupados DANE. Se conservan ambas referencias.

## Por qué no hay todavía 14 ramas observadas mensuales

El anexo mensual identifica 13 grupos y **combina** explotación de minas (`B`)
con electricidad, gas, agua y gestión de desechos (`D_E`) en un único grupo `B_D_E_COMBINED`.
La rama residual `No informa` **no** es una decimocuarta rama económica.

- No separar `B` y `D_E` usando participaciones suavizadas, coeficientes trimestrales
  arbitrarios o interpolación y llamarlas cifras oficiales mensuales.
- El paso siguiente será reconstruir esa separación desde **microdatos GEIH del mes**,
  clasificación CIIU Rev. 4 A.C. y factor de expansión correspondiente, cuando estén
  disponibles, y contrastar que `B + D_E = B_D_E_COMBINED` dentro de tolerancias del
  ámbito y la revisión del archivo.
- Los meses sin microdatos elegibles y 1993–2014 deben quedar **estimados con etiqueta**;
  no presentarse como cifras observadas. Pueden emplearse métodos econométricos,
  predictores y fuentes auxiliares con validación, **no suavizamiento por defecto**.

## Conciliador nuevo y puerta de márgenes

Se implementó `icml.sectoral_monthly.reconcile_sector_matrix`:

- Hace RAS/IPFP en **personas** para `departamento × rama`, nunca en filas de
  participaciones con suma 1 contra columnas que suman 1 en total.
- **Rechaza** márgenes incompatibles (`Σ_d O_d != Σ_k N_k`), valores negativos,
  dimensiones erradas, ceros estructurales inviables y falta de convergencia.
- Comprueba simultáneamente `Σ_k X[d,k] = O[d]` y `Σ_d X[d,k] = N[k]`.
- No tiene ningún posajuste `force_national_totals` que invalide el cierre departamental.
- Las sumas nacionales GEIH observadas **no** pueden usarse directamente como columnas
  obligatorias frente a ocupados `ICML_COMPLETO`: primero hay que especificar
  el complemento sectorial no cubierto, bajo una hipótesis explícita y auditable.

**Puerta H10:**

| Control | Resultado |
|---|---|
| Fuente oficial mensual identificada, hashes y unidades | APROBADO |
| Clasificación de soporte temporal (mes vs. trimestre móvil) | APROBADO |
| Cobertura temporal mensual observada 2015–2026-08 | APROBADO |
| Suma de grupos + No informa vs. total oficial | APROBADO |
| Compatibilidad de ocupados oficiales con `DANE_REFERENCIA` | APROBADO |
| No modificar ocupados `ICML_COMPLETO` | APROBADO |
| Nuevo RAS: cierre simultáneo, rechazo de márgenes errados | APROBADO en pruebas unitarias |
| 14 ramas mensuales directas, `B` y `D_E` separadas | **PENDIENTE: fuente mensual independiente** |
| 1993–2014 mensual por rama con evidencia/etiquetas | **PENDIENTE: Hito 11** |
| Conciliación 33 × 14 por 404 meses | **PENDIENTE: Hitos 12–13** |

## Próximo trabajo

1. **H10 continuación:** extraer microdatos DANE mensuales de *Ocupados*, factor de
   expansión y CIIU Rev. 4 A.C.; recuperar `B` y `D_E` de forma verificable y
   probar dominio/clasificación y referencia, sin modificar la fuente 13 grupos.
2. **H11:** evaluar fuentes mensuales ENH/ECH/GEIH y reconstruir 1993–2014,
   con procedencia, incertidumbre y sin falsos meses observados.
3. **H12:** un solo predictor composicional de 14 ramas entrenado sobre el mismo
   universo rector; validación geográfica y temporal, clústeres sin fuga.
4. **H13:** generar márgenes nacionales **compatibles con el completo** usando
   el complemento no cubierto; conciliar simultáneamente y derivar GEIH.

## Ejecución

```bash
icml sectoral audit-monthly \
  --workbook ../insumos/sectorial/Anexo_GEIH_Agosto_2026.xlsx \
  --nationals ../insumos/laboral/nacionales.csv \
  --legacy-checks ../insumos/sectorial/legacy_sector_national_checks.csv \
  --output ../sectorial/hito10_mensual_v001
```

**Modo portátil sin `artifact_tool`:** la extracción oficial quedó normalizada y
versionada. Es posible reauditar los CSV y verificar el hash del XLSX sin volver
a importarlo:

```bash
icml sectoral audit-monthly \
  --workbook ../insumos/sectorial/Anexo_GEIH_Agosto_2026.xlsx \
  --observations-csv ../sectorial/hito10_mensual_v001/10_observaciones_oficiales_mensuales_13_grupos.csv \
  --totals-csv ../sectorial/hito10_mensual_v001/10_totales_oficiales_mensuales.csv \
  --nationals ../insumos/laboral/nacionales.csv \
  --legacy-checks ../insumos/sectorial/legacy_sector_national_checks.csv \
  --output ../sectorial/hito10_verificacion_portatil
```

La auditoría portátil reproduce las cantidades a precisión numérica, sin
recalcular medias móviles para la estimación. El SHA-256 del XLSX se contrasta
con el declarado en las observaciones normalizadas.

Se conservan todos los insumos y productos previos. **No se recalcularon series
sectoriales, laborales ni de informalidad canónicas.**

### Documentación del DANE sobre mensualidades

- GEIH, guía de uso de microdatos anonimizados:
  https://microdatos.dane.gov.co/catalog/750/download/21521/Acceso_y_Uso_de_Bases_Anonimizadas-GEIH.pdf
- GEIH, boletín abril 2026 (incluye «Población ocupada según rama, mes abril 2026»):
  https://www.dane.gov.co/files/operaciones/GEIH/bol-GEIH-abr2026.pdf
