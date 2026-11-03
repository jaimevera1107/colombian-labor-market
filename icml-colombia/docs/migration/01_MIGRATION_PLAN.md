# Migration plan

## Contract

* **Pure refactor.** Same statistical logic as RC1. Methodological
  changes (denominators, Bogotá anchoring, validation redesign) start only
  after the migration and are released as separate versions.
* **Equivalence.** Each migrated stage reproduces its RC1 artifacts within
  `1e-6` persons (`icml.regression.compare`). Structural invariants
  (identities, coverage, provenance) are tested independently.
* **Environment.** Locked by `requirements/lock-py312.txt`, and the lock
  is part of the method. The Chow-Lin autoregressive parameter is found by
  a numerical optimizer: with scipy 1.18 / numpy 2.5 the legacy code itself
  drifts from RC1 by up to 0.03 persons (rho differs at the 8th decimal),
  while scipy 1.17.1 / numpy 2.4.4 reproduce RC1 to 1e-8. Likewise, XGBoost
  3.4 trains different trees than the 3.1.3 used by RC1 (out-of-fold rates
  differ by up to 2.4 pp), while 3.1.3 reproduces them to 1e-12. The lock
  pins the reproducing versions; golden tests refuse to run in any other numerical
  environment. With this lock, 228/228 legacy tests pass and the RC1
  closure reproduces byte-for-byte. pandas is capped below 3 because the
  legacy code mutates arrays returned by `to_numpy()` (read-only under
  pandas 3 copy-on-write); new code always uses writable copies.
* **Serialization.** Artifacts are written with the shortest decimal that
  round-trips (Python `repr`), as RC1 did; see the phase 6 notes.
* **Repository content.** Code plus minimal sources; large outputs and the
  golden set are release assets.

## Phases

| Phase | Scope | Exit gate |
|---|---|---|
| 0 | Lock, golden catalog, domain model, I/O, artifact store, manifests, comparator, CI | Done |
| 1 | National: DANE readers, splicing, temporal disaggregation, reconciliation, seasonality | Done: 6/6 `national.*` artifacts, max diff 3e-8 persons |
| 2 | Urban: donor selection, closure, retropolation, synthetic Cundinamarca | Done: 19/19 `urban.*` equivalences, max diff 5e-9 persons |
| 3 | Departmental: anchor extraction, reconstruction, population revision | Done: 13/13 `departmental.*` equivalences, max diff 5e-9 persons |
| 4 | Integration: propagation, recent urban panel, regularization, quality filter | Done: 19/19 equivalences; 98 cells of 2 flexible cities under a documented 1e-6 relative tolerance |
| 5 | Modeling: features, clustering, CV, XGBoost, selection | Done: 22/22 equivalences; predictions bit-exact after RC1's float32 serialization |
| 6 | Reconciliation: hierarchical closure, PET treatment; end-to-end CLI | Done: 12/12 equivalences and the three products (see notes) |
| 7 | Documentation and release `2.0.0` | Done; charts and HTML reports deferred to `2.1` |

Each phase migrates its stages in dependency order, feeding them with the
RC1 golden inputs so that errors cannot propagate between phases.

## Out of scope for the package

Exploratory studies (Pareto donor alternatives, aggregated donors,
non-canonical seasonal variants, hito 3.2 benchmarks, phase 07 candidate)
are archived with the legacy tree. Their conclusions survive as frozen
decisions and ADRs.

## Phase 1 notes (national)

* Replaces, on the canonical path: `national_063.py`, `cierre_nacional.py`,
  the numerical part of `estacionalidad_nacional.py`, the GEIH reading
  path of `lectores.py`/`geih_parsing.py` (`NationalMonthlyProcessor`,
  `process_national_geih`) and the series combination embedded in
  `visualizacion_nacional.py`.
* Deferred: the monthly publication workflow (`runtime.py`,
  `monthly_update.py`, `nacional.py`) moves to the vintage/publication
  phase; charts and HTML galleries move to `icml.reporting`.
* Unused legacy code not migrated: `ENHLoader`, `ExternalDataLoader` and
  `merge_spliced_with_external` have no caller in RC2.
* Behavior kept on purpose (pure refactor): disaggregation quality gates
  are reported, not enforced (RC1 marks the run as a non-publishable
  candidate); reconciliation and seasonality gates keep RC1 semantics.

## Phase 2 notes (urban)

* Replaces, on the canonical path: the decision part of `estudio_base.py`
  and `estudio_pareto.py`, `cierre_ciudades.py`, the audit inputs of
  `auditoria_etapa_a.py` that the closure needs, `retropolacion_nacional_1993.py`
  and `cundinamarca_sintetica.py`.
* The urban stage runs on the national artifacts produced by the package,
  so the regression tests cover the national-to-urban chain end to end.
* The 23-city backtest is kept only for the guarded rule, because its
  95th percentiles flag recipients in the closure audit. The other five
  rules, mixtures of donors, tolerance sensitivity and the June/August
  vintage comparison are archived exploratory studies; their RC1 columns
  are listed explicitly as `reference_only` in the regression mapping.
* Values hard-coded in RC1 (recipient list, calibration, holdout and seam
  years, guard tolerance, Pareto tie-break weights, bridge bounds) live in
  `configs/rc1/urban.toml`. City names come from the package catalog.
* RC1 inconsistency kept visible: the synthetic unit is called
  "señal sintética" in one RC1 table and "señal urbana sintética" in the
  others; the package uses one name and the mapping documents the
  difference.

## Phase 3 notes (departmental)

* Replaces `dane_departments.py`, `reconstruccion.py` (B1_v03) and the
  numerical part of `cierre_b1.py` (B1_v04). The departmental stage runs
  on the package's national artifacts (end-to-end chain in the tests).
* **Legacy BIFF reader removed.** RC1 used `xlrd` when available and a
  hand-written BIFF8/OLE2 parser (`legacy_biff.py`) otherwise. On the RC1
  annex both return the same 51,097 cells, so the package depends on
  `xlrd==2.0.1` (maintained, still reads `.xls`) and drops the custom
  binary parser. Less code to maintain, same anchors.
* Annex layout knowledge (concept regexes, title prefix, missing-value
  markers, the 23 published territories, the Bogotá alias) moved to
  `configs/rc1/departmental.toml`; territory names come from the package
  catalog instead of a dictionary inside the code.
* Stricter on one point: an unidentified block title is now an error.
  RC1 skipped it and only failed if fewer than 23 blocks were found; the
  RC1 annex has no unidentified block, so outputs are unchanged.
* Not migrated (superseded audits of B1_v03): the 1993-2025 population
  gap table, the v03 2006-2007 transition table and the warning list.
  B1_v04's link audit and population backtest replace them. The 33-signal
  coverage contract (`contrato_prediccion.py`) moves to integration, where
  the signals are consumed.
* The rho sensitivity audit of Cundinamarca's inactive population is kept
  (global optimum 0.898 versus the competing 0.989); it documents that the
  monthly path is not unique even though annual anchors are exact.

## Phase 4 notes (integration)

* Replaces `propagar_consolidar.py`, `completar_ciudades_2021_2026.py`,
  the strict scenario of `regularizar_senales_urbanas.py` and
  `seleccionar_panel_calidad_urbana.py`. Integration consumes the
  national, urban and departmental runs produced by the package, so the
  regression tests cover the four-stage chain end to end.
* **Rolling-window reading by labels.** RC1 read the 32 city blocks at fixed
  row offsets (`10 + 19 * i`). The package reuses the block parser of the
  national annex (region title, `Concepto` marker, end marker) and checks
  that every city has exactly 57 windows; the values are identical.
* **Ill-conditioned flexible cities.** For Leticia, Inírida and Mitú the
  quality filter solves a soft-constrained quadratic program whose optimum
  is flat in some directions. Evidence:
  - with identical inputs, the package solver equals the RC1 solver bit for
    bit (difference 0.0);
  - RC1 fed the solver windows read back from a CSV written by pandas,
    which changed some values by 2.3e-13 persons; the package uses the
    exact source values;
  - that 2.3e-13 perturbation moves the solution by up to 5.0e-4 persons
    (relative 4.6e-7) in 98 of 4,488 latent cells (Leticia and Inírida);
  - even the RC1 code itself, run on the RC1 inputs in the locked
    environment, differs from the RC1 output by 7.6e-6 persons.
  The equivalence for those rows is therefore one part per million
  (`RELAXED_TOLERANCE`), applied only to the affected columns of the three
  flexible cities and listed explicitly in the regression mapping. Every
  other cell of every integration artifact meets 1e-6 persons.
* Not migrated: the FLEX scenario of the regularization study (cap 2 with
  minimum tolerance + 0.25 pp for every city), which no later stage
  consumes; and four descriptive tables of the propagation run
  (`base_predictora_33_senales_1993_2020`, the labeled training table,
  the three-level panel and the coverage file), which have no consumer.
  Charts and Markdown reports move to `icml.reporting`.
* RC1 hard-coded the expected filter outcome (3 flexible, 7 strict, 22
  unchanged); the package derives the rules from the data and the tests
  check that the outcome still matches RC1.

## Phase 5 notes (modeling)

* Replaces `preparar_base_laboral.py` (hito 2), the K-Means/Ward part of
  `evaluar_clustering_avanzado.py`, `entrenar_desde_cero.py` (hito 3) and
  `cerrar_hito4.py` with its `benchmark_postajustes.py` helpers (hito 4).
  The stage consumes the package's integration and departmental runs, so
  the regression tests cover the full chain from the DANE sources to the
  33-territory departmental panels.
* **XGBoost version.** RC1 trained with XGBoost 3.1.3 (recorded in its run
  summary). With 3.4.1 the trees differ and out-of-fold rates move by up
  to 2.4 percentage points; with 3.1.3 they match RC1 to 2e-12. The lock
  now pins `xgboost==3.1.3`; the 228 legacy tests and the RC1 closure
  replay still pass with it.
* **Float32 predictions.** XGBoost returns float32. RC1 stored them with the
  shortest float32 decimal and later stages read those decimals back. The
  package keeps the exact float32 values. The regression tests check that
  (a) re-serializing the package predictions the RC1 way reproduces RC1
  bit for bit, (b) feeding the RC1 predictions to the package panel builder
  reproduces the RC1 panels within 1e-6 persons, and (c) the pipeline's
  own panels differ from those by at most four float32 units in the last
  place.
* The two hito 4 inputs without a traced producer are now derived inside
  the stage: `objetivos_test.csv` is the target block of the targets table
  and `poblacion_proyeccion.csv` the projection column of the features.
* Not migrated (exploratory, no downstream consumer): the per-fold K-Means
  cluster-feature files of hito 2, the GMM/DTW benchmark of hito 2.1, the
  hito 3.2 60-combination post-adjustment benchmark and the hito 3
  post-closure comparison. Their conclusions remain in the RC1 ADRs.
* Selection outcome matches RC1 exactly: Ward is selected in CV, the
  declared hybrid passes the hito 4 guards and is selected (hybrid minus
  Ward −0.409 pp, 95 % cluster-bootstrap interval −0.791 to −0.035).

## Phase 6 notes (reconciliation and products)

* Replaces `cierre_jerarquico.py` (hierarchical closure of both panels) and
  `linealizacion_pet_hierarquica.py` (ADR-006 minimum-curvature working
  age). The departmental product is the Ward panel, as decided in ADR-006
  (`[reconciliation.product] operational_model = "reference"`); the hybrid
  panel is reconciled too and kept as the alternative.
* **Ill-conditioned closure.** The joint smoothers solve KKT systems with
  404 monthly national totals and 437 annual anchors. Anchor values that
  differed by 1.2e-10 persons (two units in the last place) moved
  reconciled months by up to 7e-5 persons. The cause was serialization:
  artifacts were written with `%.17g` and pandas' default parser reads
  some 17-digit strings back one or two units off, while RC1 wrote the
  shortest round-trip decimal, which reads back exactly. Artifacts are now
  written the RC1 way. Parsing everything with `round_trip` precision was
  also tried and rejected: RC1 itself was produced with the default parser,
  and the national Chow-Lin optimizer then drifts by 5e-3 persons.
* **Layered equivalence.** Fed with RC1's own panels and national series,
  the package reproduces all twelve closure tables and both products
  within 1e-9 persons. In the full pipeline, the national product differs
  from RC1 by at most 6.5e-6 persons (relative 3e-13): the curvature
  smoother amplifies the 3e-8-person upstream national differences about
  200 times. The departmental product differs from its decoupled
  counterpart by at most 9e-8 relative, i.e. under four float32 units in
  the last place inherited from the model predictions (phase 5).
* `icml run` executes the six stages and writes `run.json` with the SHA-256
  of the three products; a test checks that it reproduces the per-stage
  chain bit for bit.
* Not migrated: the preliminary and no-component-regularization closure
  variants, the exhaustive audit and the HTML reporting scripts.

## Final status

| Stage | RC1 tables checked | Result |
|---|---|---|
| National | 12 | ≤ 3e-8 persons |
| Urban | 19 | ≤ 1e-8 persons |
| Departmental | 13 | ≤ 1e-8 persons |
| Integration | 19 | ≤ 1e-8 persons; 98 cells of 2 flexible cities at 1e-6 relative |
| Modeling | 22 | ≤ 1e-6; predictions bit-exact after float32 serialization |
| Reconciliation | 12 + 3 products | ≤ 1e-9 decoupled; pipeline within the bounds above |

Every relaxation is documented next to its evidence; nothing was relaxed
without first reproducing the difference with RC1's own code or inputs.
