# The reference vintage: what is frozen, what reproduces it, when to refreeze

## What is frozen

Eight products of the August 2026 cutoff, listed with their hashes in `datos/2_procesamiento/productos_congelados/catalogo_h19/19_catalogo_unificado.csv`:

| Product | Location |
|---|---|
| labor (cities, departments, nationals) | `productos_congelados/laboral/`, mirrored in `productos_congelados/pruebas_calidad/` |
| informality (cities, departments, nationals) | `parametros_congelados/informalidad_cierre_h9/13_*.csv` |
| sectoral (departmental, national) | `productos_congelados/sectorial/*_EXPERIMENTAL.csv` |

Next to them, the sectoral predictor bundle (`sectorial_h16/inputs`, `sectorial_h16/outputs`) and the H9 closure lineage (`13_resumen.json`, `manifest.json`) record exactly which labor base those products were derived from.

## What they are for

1. **Reproducibility gate.** `run-integral --mode recompute` at the frozen cutoff (what `rebuild` and `update` do at 2026-08) compares its eight candidates with the frozen ones. Since 2.5.0 a mismatch is a failure (`RECOMPUTED_BUT_CROSS_AUDIT_OR_REFERENCE_EQUIVALENCE_FAILED`, `reference_equivalence = FROZEN_VINTAGE_MISMATCH_REFREEZE_REQUIRED`); before, it was reported and ignored.
2. **Fixtures.** The tests that check the accounting identities, the cross audit between products and the resume mode read them.
3. **First-run inputs.** The sectoral bundle inputs and the H9 priors are the starting point of the first recompute on a fresh clone.

They are **not** the published base (`vigente/`) and not a delivery: those are generated locally.

## What happened in 2.4.0

The frozen products were refreshed in the "Caso A" commits, and then one more code change (the straight GEIH factor of the nine partial territories, commit `92a9465`) changed the `*_represented` and `factor_*` columns of the labor departments, and through them the GEIH-universe informality and the sectoral proxies. Five of the eight frozen products no longer matched what the code produced; the gate reported `eight_product_equivalence_passed: false` on every run and nobody saw it because the status still counted as clean. The sectoral bundle was older still (trained on the labor base before 2.4.0). 2.5.0 refroze everything from one recompute.

## Which dependency versions reproduce it

The frozen products were measured against fresh recomputes under different dependency versions (2.6.0):

| Environment | Result |
|---|---|
| the locked environment (`requirements/lock-py312.txt`) | 8/8 products byte-identical |
| latest numpy, scipy, scikit-learn, pandas, **tempdisagg 0.6.4** with **xgboost 3.1.x** | differences of at most 0.01 persons and 1e-9 in rates: floating-point noise, accepted by the gate |
| latest everything with **xgboost 3.4** | the ten modelled territories change: up to 38,900 persons of departmental PET, 1,050 of national labor force, 1.3 pp of sectoral share |

That is why `pyproject.toml` caps `xgboost>=3.1,<3.2`; `tempdisagg>=0.6.3,<0.7` stays open because 0.6.3 and 0.6.4 were both measured to reproduce the frozen products (max difference 0.013 persons) and the code guard accepts the same range and leaves the other ranges open, and why the comparison tolerances are 0.1 persons and 1e-6 for rates. Raising the xgboost cap is a methodological change: recompute, read the differences, refreeze.

## The reference depends on the platform

The frozen products were computed on Linux x86_64 (`productos_congelados/REFERENCE_PLATFORM.json`, written by `refreeze_reference.py`). Tree models are not bit-reproducible across operating systems and CPU builds: on Windows, with exactly the same Python and library versions, the ten territories modelled with xgboost came out different (up to ~6 % of a small department's unemployed level; population and rates essentially unchanged), while the cities and every identity were unchanged. Two measures follow:

* `modeling.toml` runs xgboost single-threaded (`n_jobs = 1`): multi-threaded histogram building sums in a machine-dependent order. On the reference platform this changed nothing (byte-identical products).
* On a platform other than the recorded one, the reference comparison accepts a **bounded, purely numeric** difference: on the reported columns (levels and rates, never the diagnostic residual-share or factor columns) no cell may move by more than `PLATFORM_RELATIVE_BOUND` (12 %) of its column's typical magnitude, rates by at most that many percentage points, no key, column or category may differ, and the cross audit must pass. The run then ends in `RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES_ON_ANOTHER_PLATFORM` with `reference_equivalence = PLATFORM_DEPENDENT_MISMATCH_ACCEPTED`, the measured maximum relative difference is in the report, and `rebuild`/`update` print it. Anything else is still a mismatch.

To make your own computer the reference (strict comparison there from then on): `run-integral --mode recompute`, then `python tools/refreeze_reference.py --run <output>`, which also rewrites `REFERENCE_PLATFORM.json`.

## When and how to refreeze

Refreeze whenever a change is adopted that alters any number at the frozen cutoff: a methodological change, a new frozen parameter, a fix in a stage. Never for a layout, naming or performance change (those must leave the numbers byte-identical; prove it with `tools/compare_runs.py`).

```
python -m icml operations run-integral --root . --output /tmp/refreeze --mode recompute
python tools/refreeze_reference.py --root . --run /tmp/refreeze
git diff --stat                       # review: products, catalogs, bundle
icml checksums --write
```

Then bump the version, describe the change in `CHANGELOG.md` with the before/after metrics that matter (the sectoral predictor's LOGO MAE is in `sectorial_h16/outputs/16_puerta_calidad.json`, the informality closure gate in `informalidad_cierre_h9/13_puerta_calidad.csv`), and commit the refreeze separately from the code change so both can be reviewed on their own.

A refreeze changes the reference the next anchored update compares against; it does not change any published delivery.
