# ICML 2.2.26.dev0 — H24: ejecución integral con corte agosto de 2026

## Objetivo

Unificar **sin alterar modelos ni publicar estadísticas oficiales** la cadena laboral,
de informalidad y sectorial. La fecha vigente es **agosto de 2026**. El flujo de
septiembre es otra operación (`monthly-cycle` H23), y SIEMPRE requiere GEIH del
mes objetivo y Empleo Informal y Seguridad Social con igual mes de cierre.

### Grafo de dependencias

```text
fuentes nacionales / urbanas / departamentales del DANE
  -> nacional -> urbano -> departamental -> integración
  -> modelado -> conciliación -> calidad
  -> laboral (3 productos) ----------------------------------+
                                                             |
  H9 fuentes históricas y auxiliares CNPV-2018 + MLP --------+--> informalidad (3)
                                                             |
  H11 composición nacional + 38 características originales --+--> H16 (2 sectoriales)
                                                             |
                                                auditoría cruzada de 8 productos
                                      -> comparación contra vintage agosto 2026
                                      -> reporte NO CANÓNICO, NO PUBLICADO
```

La cadena de informalidad requiere la base laboral y otros insumos intermedios del
Hito 9. El modelo H16 utiliza departamentos laborales y una vintage auxiliar
histórica de informalidad original (2007–2025) congelada como característica del
modelo seleccionado. **No se reemplaza esa vintage por la nueva salida H9:** eso
cambiaría los predictores y la metodología congelada.

## Modos operativos

Desde `icml-colombia` después de instalar `python -m pip install -e .`:

**1. Verificación íntegra del corte ya calculado (sin recalcular):**

```powershell
python -m icml operations run-integral `
  --root .. --mode verify --output ..\..\auditorias\ICML_2026_08_verificacion
```

Comprueba hashes de ocho productos, dimensiones, calendario, claves únicas,
identidades laborales, cierres de informalidad y los márgenes sectoriales
nacionales/departamentales. Comprueba además los hashes del paquete H16.

**2. Recalcular H9 y H16 utilizando el trabajo laboral congelado:**

```powershell
python -m icml operations run-integral `
  --root .. --mode recompute-components --output ..\..\corridas\ICML_2026_08_H9_H16
```

Este modo **ejecuta los estimadores** de informalidad y sectorial y compara sus
salidas, pero **no recalcula laboral desde fuentes primarias**. En equipos más
modestos puede ser pesado. Si se detiene, no modifica los insumos y puede
reanudarse desde etapas completas verificadas.

**3. Reanudar con resultados de H9/H16 ya ejecutados y verificados:**

```powershell
python -m icml operations run-integral `
  --root .. --mode recompute-components `
  --resume-informality "D:\\corridas\\H9_completo" `
  --resume-sectoral "D:\\corridas\\H16_completo" `
  --output "D:\\corridas\\ICML_2026_08_ensamblado"
```

Comprueba el manifiesto de H9, que los hashes laborales utilizados por H9 y H16
sean los mismos y la integridad completa de H16. No reentrena nada en la
invocación de reanudación: **ensambla dos cálculos previos reales**, y lo declara
expresamente en el reporte.

**4. Reejecutar las ocho bases desde fuentes primarias:**

```powershell
python -m icml operations integral-preflight `
  --root .. --mode recompute --sources "D:\\ICML_Fuentes_Completas"

python -m icml operations run-integral `
  --root .. --mode recompute `
  --sources "D:\\ICML_Fuentes_Completas" `
  --output "D:\\corridas\\ICML_2026_08_desde_fuentes"
```

Primero se validan todas las entradas requeridas. **Si falta alguna, se bloquea
antes de ejecutar**. Se necesita la estructura de fuentes originales referida
por `configs/rc1/*.toml` y los insumos congelados H9. El proyecto H24 recupera
los cuatro insumos H9 desde el checkpoint H18, pero la distribución no contiene
varios archivos originales del árbol `fases/` requeridos por las siete etapas
laborales. Por eso **no está demostrada todavía la reejecución completa desde
fuentes originales**; consultar `ENTREGA_H24/24_preflight_recalculo.json`.

No se recomienda fabricar esos insumos a partir de los resultados publicados:
una prueba de reproducción así sería circular.

## Reglas de cierre

- Un universo **ICML completo** por departamento: comparable entre bases.
- GEIH representado de informalidad, calibrado mediante puente CNPV-2018,
  **no es necesariamente idéntico** a la columna representada laboral; registrar
  la brecha, nunca imponer un cierre ficticio.
- Las 33 señales urbanas no se suman para formar totales nacionales.
- La suma de los sectores sobre el representado nacional es **proxy derivado
  de departamentos**, no un margen DANE oficial.
- `NO_INFO` no se redistribuye clandestinamente como sector productivo.
- Las observaciones oficiales se mantienen diferenciadas de las estimaciones.
- No se publica ni sobrescribe la vintage de agosto mediante estos comandos.
- No se permite septiembre sin **ambos anexos** válidos y sincronizados.

## Archivos y estados

`integral_execution_report.json` contiene los preflight, hashes, conteos,
identidades, brechas por universos y diferencias por columna contra el corte
congelado. `VERIFIED_EXISTING_VINTAGE_NOT_REEXECUTED` significa solo auditoría;
`RECOMPUTED_H9_H16_FROM_VERIFIED_STAGE_RUNS` significa que se ensamblaron
etapas previamente recalculadas y validadas. No equivale a una ejecución
end-to-end de las siete etapas laborales originales.

## Evidencia reproducida en esta entrega

- H9 reconstruido con insumos reales de checkpoint: **11/11 archivos idénticos**.
- H16 recalculado: **15/15 archivos idénticos**.
- Tres laborales preservados y verificados sin recalcular de fuentes primarias.
- Comparación final de **8/8 productos SHA-256 idénticos** y auditoría
  conjunta aprobada.
- Golden RC1 externos y Python 3.12 bloqueado siguen pendientes de certificación.
- Las estimaciones de informalidad/sectorial continúan siendo de investigación.
