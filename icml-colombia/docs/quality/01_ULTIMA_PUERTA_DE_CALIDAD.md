> **Archivo histórico (2.1.1.dev0).** Describe el diseño anterior
> del panel único `territorial_unified.csv` y factores nacionales nulos
> antes de 2001. No es el contrato vigente. La entrega 2.1.2.dev0
> utiliza tres bases separadas, sin `00` en ciudades/departamentos, y
> factores históricos iguales a 1. Consultar `TRES_BASES.md`.

# ICML — Puerta final de calidad laboral (2.1.1.dev0)

## Alcance y veredicto

Se ejecuta **después** de `reconciliation`, consumiendo sin modificación los seis
productos de `icml-colombia 2.1.0`. **No vuelve a estimar** PET, población,
ocupados, desocupados ni tasas. La salida principal es un panel de 34 filas por
mes (`00` nacional + 33 territorios).

**Resultado sobre los productos entregados:**

- **Integridad contable y representatividad: aprobadas.** Ninguna falla dura.
- **Publicación metodológica: pendiente.** `REQUIERE_REVISION_METODOLOGICA`;
  las alertas de linealidad deben resolverse o justificarse con su procedencia.
- **No debe etiquetarse como una versión laboral certificada ni pasarse
  automáticamente a informalidad.** Puede utilizarse como base de inspección.

### Conteo verificado

| Control | Resultado | Tratamiento |
|---|---:|---|
| Registros de panel único | 13.736 | 34 x 404; `00` no aditivo |
| Identidades | 0 fallas duras | Tolerancia de 1e-5 personas |
| Representatividad 2001–2026 | 0 fallas | Residuos hasta 1 persona por redondeo GEIH |
| Comparaciones contra referencia oficial | 2.320 | Desviación máxima 1,8924 % (desocupados) |
| Variación extrema por factor 3 (mensual o anual) | 18 | Todas urbanas, desocupados, comparación YoY |
| Desplazamientos sostenidos de tasas | 496 | Exploratorios; no equivalen a 496 rupturas auténticas |
| Variaciones mensuales de población/PET >1 % | 2.033 | Mezcla de escalones, efectos reales y anomalías |
| Series-año con población exactamente plana | 506 | Todas en panel territorial unificado |
| Series-año que superan 2 % de desvío frente a recta anual | 36 | Todas de PET: 23 territoriales, 13 urbanas |

La mayor desviación de PET es Chocó (27), año 2020: **13,2119 %** del
promedio anual. Es un caso para inspección de fuente y reconciliación, no
una autorización para imponer una recta por edición manual.

La población nacional `00` es constante dentro de cada año 1993–2000, con
escalones de enero entre años. Los nueve territorios parcialmente representados
(81, 85, 86, 88, 91, 94, 95, 97 y 99) presentan población anual escalonada
más allá de 2000. Esto contradice la expectativa de una interpolación mensual
lineal estricta. No se corrige en esta puerta para no alterar las estimaciones
laborales ya entregadas sin reconstruir sus dependencias.

## Producto unificado `quality/products/territorial_unified.csv`

- Clave: (`dep_code`, `period`), donde `dep_code` **es texto** de dos dígitos:
  `00`, `05`, `08`, ... `99`. Al importar CSV en pandas usar
  `pd.read_csv(..., dtype={'dep_code': 'string'})`.
- Alternativa de clave inequívoca: `territory_id` (`CO-00`, `CO-05`, ...).
- `territory_level=NACIONAL_ICML` y `is_aggregate=true` para `00`.
- `is_additive_member=false` para `00`; **nunca** sumar las 34 filas para
  obtener el nacional. La suma correcta utiliza solo las 33 filas con
  `is_additive_member=true`.
- `employed`, `unemployed`, `inactive`, `labor_force`, `working_age`, `population`:
  magnitudes del **universo completo del ICML**, también para `00`.
- `*_represented`: magnitudes asignadas al dominio nacional de referencia.
  En `00` a partir de enero 2001 equivalen al referente GEIH usado por el
  proyecto; antes de 2001 son una **referencia reconstruida**, **no** cifra
  nacional observada del DANE.
- `factor_*`: para cada magnitud, `*_represented / nivel completo`; en 2001+
  la suma `factor_* × nivel` sobre 33 departamentos reproduce la referencia.
  **Los factores de `00` son nulos en 1993–2000:** no existe una restricción
  nacional GEIH oficial para esos meses.
- `coverage_gap_*`: nivel completo menos representado. Antes de 2001 no
  debe interpretarse como población excluida por una GEIH oficial.
- `source`, `reference_status`, `territory_name`, `year` y tres tasas calculadas
  forman parte del contrato público.
- Las comparaciones por unidad se obtienen de
  `reconciliation/products/official_deviation.csv`, conservado sin cambios.

## Auditorías y límites

- `identities_territories.csv`: cierre por registro de las 34 unidades;
  `identities_urban.csv`: cierre de las 33 señales urbanas.
- `reference_alignment.csv`: comparación mensual entre los 33, `00` y la
  referencia nacional. **La exigencia de igualdad del dominio representado
  empieza en 2001-01**. Antes es solo diagnóstico, sin recalibrar historia.
- `official_deviation_check.csv`, `official_accuracy_summary.csv`: se revisan
  2.320 líneas oficiales y sus fórmulas; ningún valor de entrada se redondea
  para forzar cierre.
- `extreme_changes.csv`: aumentos `>=200 %` o descensos simétricos (se reduce
  al menos a un tercio), además de transiciones cero. Se calculan MoM y YoY.
  La variación porcentaje y la regla aparecen por separado. No se dividen ceros.
- `structural_breaks.csv`: búsqueda con ventanas contiguas de 12 meses sobre
  tasas. Umbrales: desempleo 5 pp; ocupación 4 pp; participación 4 pp.
  Consolidación de episodios próximos. Etiquetas contextuales para 2001,
  pandemia 2020, marco 2021 y ampliación 2014. **No prueba estadística causal
  de cambio estructural ni acusación automática de error.**
- `demographic_jumps.csv`: alerta al cambiar PET o población más de 1 % entre
  meses, distinguiendo los escalones típicos de proyecciones anuales antiguas.
- `annual_linearity.csv`: ajuste OLS separado por territorio-año-variable y
  máxima desviación relativa respecto a la recta. También detecta años
  completamente planos que generan saltos entre diciembre y enero.
- `audit/summary.json`: estado, tolerancias, conteos y fallas bloqueantes.

## Criterios para cerrar la puerta

1. Fallas contables, duplicados, meses ausentes, tasas fuera de [0,1] o
   diferencia inexplicada con las referencias **bloquean técnicamente**.
2. Las alertas sobre linealidad o roturas importantes **bloquean la
   certificación metodológica** mientras no tengan revisión y decisión
   documentada. Un salto por pandemia puede admitirse con evidencia; un
   escalón de proyección anual debe explicarse o corregirse aguas arriba.
3. Si se cambia un denominador o método en origen, generar un **nuevo
   vintage**, revalidar sus modelos/dependencias y volver a correr G0–G6.
   No se modifica el producto 2.1.0 ni sus referencias.
4. La salida unificada puede consumirse como **candidato de inspección**.
   Para consumo productivo por informalidad, exigir un manifiesto de aprobación
   explícita del responsable autorizado y verificación del vintage.

## Ejecución

```bash
icml quality run \
  --config configs/rc1/quality.toml \
  --reconciliation-run runs/<id>/reconciliation \
  --runs-dir runs \
  --run-id puerta-final-001
```

Se generan SHA-256 y `manifest.json` de etapa mediante `ArtifactStore`; no se
modifica la etapa anterior. `icml run` incluye esta séptima etapa después de
`reconciliation`. El `run.json` de una corrida **nueva** incluye
`quality_gate.certified_for_publication` y el hash del resumen.

### Reproducción entregada

La puerta se ejecutó en este entorno con los 13 archivos del ZIP de productos
2.1.0 verificados byte por byte. Se superaron 162 pruebas unitarias (incluidas
6 nuevas). La suite de regresión completa 2.1.0 requiere el entorno congelado
Python 3.12 (numpy 2.4.4, scipy 1.17.1, xgboost 3.1.3, tempdisagg 0.6.3)
y sus artefactos golden. Esta entrega **no afirma** reproducir esos 288
ensayos bajo el entorno de ejecución actual.
