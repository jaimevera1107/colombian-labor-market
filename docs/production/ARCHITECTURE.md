# Architecture

One Python package, `icml`, installed from `src/`, drives everything: the stage pipeline, the monthly recalculation, the deliveries and the operational gates. The data tree `datos/` is the only state outside the code.

## Package layout

| Package | Responsibility |
|---|---|
| `icml.cli` | Argument parsing and dispatch only. One module per command group (`project`, `delivery`, `pipeline`, `sectoral`, `operations`); every parser registers its `handler`. |
| `icml.layout` | The shared paths of a checkout (`datos/1_ingesta`, `configs/rc1`, …) and `find_project_root`. |
| `icml.domain` | Territories, periods, quantities, provenance labels and the frozen cutoff. |
| `icml.ingestion` | Discovery and validation of the DANE annexes placed in `datos/1_ingesta`. |
| `icml.national`, `icml.urban`, `icml.departmental`, `icml.integration`, `icml.modeling`, `icml.reconciliation`, `icml.quality`, `icml.evaluation` | The labor stages, each with its `pipeline.py` and configuration loader. |
| `icml.pipeline` | Stage registry, run manifests and the chain that runs the stages in order. |
| `icml.informality` | National, urban and departmental informality: historical reconstruction, sequential closure, MLP experiments, quality gates. |
| `icml.sectoral` | Sectoral employment: observed DANE monthly support, historical bridges, experimental priors and the territorial predictor. |
| `icml.census` | CNPV-2018 coverage bridge between the complete and the GEIH-represented domains. |
| `icml.recalculation` | Planner, gates, graft of the frozen years, vintage root for an earlier cutoff, and `service.run_recalculation` (the orchestration behind `rebuild`/`update`). |
| `icml.delivery` | Timestamped two-universe deliveries, their simple files and the 52 audit checks. |
| `icml.operations` | Read-only gates and staging: frozen products, source catalog, GEIH intake, monthly cycle, certification, checkout checksums, Excel-derived sources. |
| `icml.regression` | RC1 golden catalog and comparison helpers. |
| `icml.plots` | Optional figures of a delivery and audit charts of the frozen products. |

## Command groups

* **Everyday** (`icml.cli.project`): `status`, `rebuild`, `update`, `plots`, `verify`, `checksums`. They never compute on their own: `rebuild` and `update` call `icml.recalculation.service`.
* **Expert**: `recalc` (the planner with every knob), `delivery build|simple|verify`, `run` and `<stage> run`, `informality <experiment>`, `sectoral <tool>`, `census-bridge run`, `operations <gate>`, `golden capture|verify`.

## Data flow of a recalculation

1. `ingestion.discovery` detects the last month with both annexes (`--through` caps it).
2. When the cutoff differs from the frozen one, `recalculation.vintage_root` builds a working copy of the project cut at that month (configs re-sealed by hash).
3. `operations.integral.run_integral` recomputes the eight products from the sources in a temporary folder and cross-audits them.
4. `recalculation.runner.recalculate` grafts the frozen years (anchored mode) or takes everything (total mode), writes the delivery under `datos/3_salida/` and points `datos/2_procesamiento/vigente/` at it.
5. `delivery.verify` runs the 52 checks; `delivery.simple` writes the simple files.

## Proving that a change keeps the numbers

Run `icml rebuild --through 2026-07 --yes` and `icml update` on the current `main` and on the branch (same clean clone each), then `python tools/compare_runs.py <datos A> <datos B>`. It pairs the deliveries by name, requires byte-identical CSVs, compares the manifests after dropping run ids, timestamps, the software version and the checkout path, and compares the `.xlsx` files member by member. The 2.5.0 refactor was accepted on that basis (see CHANGELOG).

## Rules

* The data tree keeps its Spanish folder names: manifests, catalogs and migration maps record those paths and the hash gates depend on them.
* Persisted values (plan statuses such as `BLOQUEADO`/`SIN_CAMBIOS`, mode names `anclado`/`total`, folder suffixes `_sencillo`/`_graficos`, delivery column names) are part of the published contract and are not translated.
* Bug fix: bump the version and add a regression test; never change frozen data silently.
* Ordinary update: a new vintage that adds a month within the revisable window.
* DANE revision: a new vintage with the documented cause and the difference against the history.
* Methodological change: a new method version, never mixed with an ordinary update.
