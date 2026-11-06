# icml-colombia — paquete del ICML 2.0

Versión **2.3.0.dev0** · Python 3.11 a 3.13 (versiones fijadas para 3.12 en `requirements/`). La guía de operación
está en el [README de la raíz](../README.md); este archivo describe el paquete para quien lo mantiene.

## Mapa del paquete (`src/icml/`)

| Subpaquete | Responsabilidad |
|---|---|
| `domain/` | Calendario de la vintage (`cutoff`: fuente única del corte y de las formas esperadas), períodos, territorios, identidades contables y procedencia |
| `ingestion/` | Detección de anexos en la ingesta, clasificación por nombre y verificación del período declarado en el libro |
| `operations/` | Ejecución integral (`integral.run_integral`), preparación de los nueve extractores de Excel, vista de fuentes, linaje y regeneración de H5/H6, catálogos y controles operativos heredados (H19 a H23) |
| `national/` | Etapa nacional: lector del anexo GEIH, conciliación de anclas anuales, empalme ENH→GEIH y desagregación temporal, estacionalidad |
| `urban/` | Etapa urbana: donantes para las nueve ciudades sin historia, cierre acotado, retropolación 1993-2020, señal sintética de Cundinamarca |
| `departmental/` | Etapa departamental: anclas del anexo anual, reconstrucción mensual, retroproyección de población |
| `integration/` | Ventanas móviles a valores mensuales latentes, regularización de saltos, propagación del ajuste estacional, panel urbano reciente |
| `modeling/` | Modelos departamentales de tasas con validación cruzada geográfica y selección de los paneles de 33 territorios |
| `reconciliation/` | Cierre jerárquico (los 33 departamentos suman al nacional), linealización de la PET, factores de representatividad |
| `quality/` | Puerta de calidad: identidades contables y las tres bases públicas |
| `pipeline/` | Registro de etapas y cadena completa (`chain.run_all`), manifiestos, reconstrucción laboral 1993-2000 (PET lineal y componentes) |
| `informality/` | Informalidad: fuente nacional (H5), cadena secuencial (H6), históricos, MLP, cierre integral (H9) y empalme de 2001-01 |
| `sectoral_*`, `sectoral_predictive/` | Sectorial experimental: fuentes mensuales, empalme CIIU3/CIIU4, retropolación 1993-2001, priors, conciliación, predictor H16 y capa de seguridad H17 |
| `census_bridge.py` | Puente CNPV 2018 entre el universo completo y el representado |
| `recalculation/` | Recálculo anclado o total: plan, compuertas, injerto de años congelados, comparación de vintages |
| `delivery/` | Entrega en dos universos, archivos sencillos y verificación (36 comprobaciones) |
| `regression/` | Catálogo y comparación contra las 102 referencias Golden RC1 |
| `evaluation/` | Evaluación de transferencia territorial (fuera de la cadena completa por su costo) |
| `io/` | Lectura y escritura determinista, almacén de artefactos con hashes |

## Comandos

Uso diario (comandos sencillos, `cli_amigable.py`; el atajo `icml.sh` / `icml.bat` de la raíz no pide activar el entorno):

| Comando | Qué hace |
|---|---|
| `icml estado` | Anexos, base publicada, entregas y el siguiente paso |
| `icml consolidar --desde-cero [--hasta AAAA-MM] [--si] [--simulacro]` | Recomienza todo desde cero (modo total) y publica la base; con `--hasta` ignora los anexos posteriores |
| `icml actualizar [--hasta AAAA-MM] [--simulacro]` | Solo el mes nuevo (modo anclado): los años anclados no se tocan |
| `icml graficos [--carpeta C] [--solo …] [--universo …] [--forzar]` | Gráficos de la entrega vigente (`tools/plots`) |
| `icml verificar [--carpeta C]` | Audita una entrega |

Comandos de base (los de arriba son una capa sobre ellos):

| Comando | Qué hace |
|---|---|
| `icml recalcular --root R [--simulacro] [--modo anclado\|total] [--confirmar-total] [--aceptar-modificados]` | Plan y ejecución del recálculo, entrega fechada y promoción a vigente |
| `icml entrega sencillo --carpeta C [--sin-excel]` | Archivos con solo las columnas de cada dominio |
| `icml entrega verificar --carpeta C` | Vuelve a auditar una entrega |
| `icml entrega construir --desde-corrida D --salida S [--sencillo] [--excel]` | Entrega desde una corrida integral existente |

Avanzados:

| Comando | Qué hace |
|---|---|
| `icml operations run-integral --root R --output O --mode recompute [--configs C]` | Recalculación completa de los ocho productos con su auditoría |
| `icml run --configs C --sources S --runs-dir D --run-id I` | Solo la cadena laboral |
| `icml golden capture\|verify` | Referencias RC1 |
| `icml operations certify`, `verify-products`, `check-monthly-sources` | Controles de integridad heredados |
| `icml informality …`, `icml sectoral …`, `icml census-bridge run` | Etapas y estudios de investigación por separado |

El corte activo es 2026-08. Un mes anterior se calcula con `icml consolidar --hasta AAAA-MM`: el programa arma por sí
solo una copia de trabajo del proyecto cortada en ese mes (`recalculation/vintage_root.py`; `tools/release/build_vintage_root.py`
es su envoltorio de línea de comandos) y la variable `ICML_CUTOFF` se fija reiniciando el proceso. Solo meses anteriores a la
vintage congelada.

## Configuración (`configs/rc1/`)

| Archivo | Etapa |
|---|---|
| `national.toml`, `urban.toml`, `departmental.toml`, `integration.toml`, `modeling.toml`, `reconciliation.toml`, `quality.toml` | Cadena laboral |
| `informality.toml`, `informality_sequential.toml` | Informalidad H5 y H6 |
| `census_bridge.toml`, `evaluation.toml` | Puente censal y evaluación |
| `regime_splice.toml`, `labor_reconstruction.toml` | Empalme de la informalidad y reconstrucción laboral 1993-2000 (adoptados: `enabled = true`) |
| `labor_base_splice.toml` | Empalme de la PET de 2.3.0, reemplazado por la reconstrucción laboral (`enabled = false`) |
| `configs/golden/rc1_catalog.toml` | Catálogo de las referencias RC1 (generado) |

## Pruebas

```
PYTHONPATH=src python -m pytest                                                   # sin referencias Golden
PYTHONPATH=src ICML_GOLDEN_DIR=../legacy/validacion/rc1_original python -m pytest  # suite completa (unos 10 minutos)
```

Desde un clon limpio, con el instalador (sin `torch`), la suite completa da **701 pruebas que pasan y 4 omitidas**: dos porque
falta el insumo de microdatos (fuera del árbol) y dos porque requieren `torch`, que es opcional
(`pip install -r requirements/lock-py312-ml.txt`; con él pasan 704 y se omiten 2).

`tests/unit` cubre la lógica (incluidos los guardias del corte, la entrega, el recálculo y los empalmes);
`tests/regression` compara cada etapa con RC1; las demás carpetas cubren cada etapa laboral.

## Reglas de desarrollo

* **Equivalencia:** con los dos empalmes apagados, la recalculación integral debe reproducir byte a byte los ocho
  productos congelados de agosto de 2026. Cualquier cambio que la rompa es metodológico, no un refactor.
* **Cambio metodológico:** versión menor nueva, entrada en `CHANGELOG.md`, nota en `docs/production/` y recálculo en
  modo total.
* **Sin literales del corte:** las fechas y formas de la vintage salen de `icml.domain.cutoff`; una prueba lo vigila.
* **Estilo:** PEP 8 (ruff), tipado explícito, docstrings, inglés en el código y español en la documentación.

## Herramientas (`tools/`)

| Herramienta | Uso |
|---|---|
| `release/reorganize_layout.py`, `release/rename_ingestion.py` | Migración a la estructura de datos actual y a los nombres canónicos (simulacro por defecto, sin borrar) |
| `release/build_vintage_root.py`, `release/simulate_july_august.py` | Raíz de un corte anterior y ensayo de actualización mensual |
| `release/audit_july_august_h36.py` | Auditoría de fuentes de julio y agosto |
| `plots/graficar_entrega.py` | Gráficos opcionales de una entrega: tableros por territorio y comparativos (ver `docs/production/GRAFICOS.md`) |
| `release/verify_checkout.py` | Comprueba que una copia del repositorio está completa e intacta (`SHA256SUMS`) |
| `legacy/` | Generación del catálogo RC1 y utilidades heredadas |
