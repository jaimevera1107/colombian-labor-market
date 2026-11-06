# Traceability report and improvement opportunities — ICML 2.0

Version 2.6.0 (originally written 2026-11-03 for 2.4.0). It complements the [Processing framework](PROCESSING_FRAMEWORK.md). Module paths, test names and the gap list are updated to the 2.5.0 layout and to what 2.6.0 resolved; the evidence of the 2.4.0 runs is kept as written.

## Scope of the verification

The consolidated repository was examined (in 2.4.0: 133 modules in 18 subpackages, about 33,600 lines of source code counting `.py` files without `__init__`; 92 test files; 15 configurations) together with the runs executed while building it. The main execution evidence:

- the adopted total recompute (`2026-11-03_064801_corte-2026-08_total`), with the verified delivery (36 of 36 checks at the time; 52 since 2.4.0's final gate set);
- the three usage routines (`rebuild --through 2026-07`, `update` and `plots`) executed end to end on a clean copy, with the evidence of `docs/production/MONTHLY_UPDATE.md`;
- the reverted recompute (reconstruction off and PET splice on), byte-identical in the eight products to the 2.3.0 vintage;
- the July 2026 vintage;
- the full suite with the Golden references: 801 tests passing, 2 skipped (one of them, sectoral microdata that live outside the source tree).
- **2.5.0:** a `rebuild --through 2026-07` + `update` on the refactored code reproduced the 2.4.0 deliveries byte for byte (64/64 CSVs, 8/8 published-base files); **2.6.0:** two independent recomputes at the frozen cutoff reproduce the refrozen eight products byte for byte, and within 0.01 persons under the latest numpy/scipy/scikit-learn/pandas with xgboost 3.1.x.

The equivalence with the frozen vintage with **all** methodological changes off was verified in 2.3.0 and not repeated in 2.4.0.

States: **A** implemented and verified (code plus test or run); **B** partially implemented or verified only indirectly; **C** documented without sufficient evidence; **D** recommendation, not implemented. Line numbers are omitted because they change with every edit.

## A. Traceability matrix

| Process | Component (file · function) | Evidence | State | Notes |
| --- | --- | --- | --- | --- |
| Annex detection and cutoff | `ingestion/discovery.py` · `discover`, `detect_cutoff`; `ingestion/validation.py` · `verify_annex` | `test_ingestion_discovery.py` (with real workbooks) | A | The name classifies and the content decides; Excel lock files are ignored |
| Two-annex rule | `operations/source_pair.py` · `check_monthly_sources`; `detect_cutoff` | `test_h22_source_pair.py`, `test_recalculation_runner.py` | A | A month with one annex stays pending |
| Recompute plan and gates | `recalculation/plan.py` · `plan_recalculation`; `gates.py`; `policy.py` · `AnchorPolicy`; `runner.py` · `recalculate` | `test_recalculation.py`, `test_recalculation_runner.py`; real dry runs | A | Total requires confirmation |
| Preparation of the nine extractors | `operations/excel_staging.py` · `run`; `excel_sources.py`; `excel_historical_sources.py`; `urban_annex.py` | `test_excel_source_preparation_h29.py`, `test_h31_excel_lineage.py`, `test_h32_urban_annex.py`; integral report | B | The orchestrator `run` has no test of its own; its extractors do |
| Labor source view | `operations/prepared_sources.py` · `stage_labor_source_view` | `test_h34_prepared_sources.py` | A | Manifest with hashes |
| Labor chain | `pipeline/chain.py` · `run_all`, `STAGES`; each stage's `pipeline.py` | Per-stage tests and `test_rc1_golden.py`; 8 of 8 products byte-identical | A | `run_all` is validated by regression and runs, without a unit test of its own |
| Hierarchical reconciliation and PET linearization | `reconciliation/hierarchical.py`, `linearization.py`, `solvers.py` | `test_reconciliation_stage.py`, `test_reconciliation_solvers.py` | A | Tolerances of 1e-3 persons |
| Representativeness (GEIH universe) | `reconciliation/representativeness.py` | `test_representativeness.py` | A | Factor 1 in 1993-2000, 0 in 2001-2013 for 9 territories; straight segments since `92a9465` |
| Labor quality gate | `quality/gate.py`, `consolidated.py` | `test_quality_gate.py`, `test_three_bases.py` | A | Identities at 1e-5 persons |
| Labor reconstruction 1993-2000 (linear PET and components) | `pipeline/labor_reconstruction.py` · `reconstruct_labor_products` | `test_labor_reconstruction.py` (41); adopted run; exact straight PET and residuals below 4e-9 | A | The components are generated, not observed; the ENH annual means stop being anchors |
| 2.3.0 labor PET splice | `pipeline/labor_base_splice.py` · `splice_labor_products` | `test_labor_base_splice.py` (12) | D | Replaced in 2.4.0; kept to reproduce 2.3.0 |
| H5/H6 regeneration | `operations/informality_regeneration.py` · `run` | `test_h35_regeneration_gates.py`, `test_h35_semantic_comparison.py`; runs | B | The strict window `strict_from` has no test of its own |
| H9 informality closure | `informality/finalize_block.py` · `run`, `_calibrate_full` | `test_informality_finalization.py`, `test_informality_quality_gate.py`; runs | A | The independent scientific evidence controls fail by design and do not block |
| Census bridge refresh | `finalize_block.py` · `_refresh_bridge_levels` | July and August runs | B | No unit test of its own |
| Informality splice | `informality/regime_splice.py` · `splice_regime`, `estimate_break` | `test_regime_splice.py`; adopted run | A | National break of 2.46 pp |
| Sectoral H16/H17 | `sectoral/predictive_integration.py`; `sectoral/integral.py` · `validate_bundle`, `export_experimental` | `test_h17_sectoral_integral.py` and the H10 to H13 tests; cross audit | A | Experimental product; bundle refrozen on the current labor base in 2.6.0 |
| Cross audit and reference comparison | `operations/integral.py` · `audit_products`, `compare_candidate` | `test_integral_h24.py`, `test_h27_product_equivalence.py`; runs | A | 0.1 persons, 1e-6 in rates since 2.6.0; the comparison is enforced at the frozen cutoff |
| Graft of anchored years | `recalculation/graft.py` · `graft_frozen_years`, `assert_frozen_unchanged` | `test_recalculation.py`, `test_replay_and_annex.py`; July-to-August rehearsal | A | Zero frozen cells changed |
| Delivery per universe | `delivery/spec.py`; `builder.py` · `build_delivery` | `test_delivery.py` | A | GEIH coverage status included |
| Delivery verification | `delivery/verify.py` · `verify_delivery`, `coverage_report` | `coverage_report` tested; `verify_delivery` on real deliveries (52 of 52) and on a synthetic delivery with tampering (`test_delivery.py`, 2.6.0) | A | — |
| Simple files | `delivery/simple.py` · `build_simple` | `test_delivery.py` | A | Real date in XLSX |
| Single cutoff | `domain/cutoff.py`; literal guard | `test_cutoff.py`, `test_no_cutoff_literals.py` | A | `ICML_CUTOFF` set by the CLI when it relaunches for another month |
| Vintage of another cutoff | `recalculation/vintage_root.py` · `build_vintage_root`; `recalculation/extension.py` | July vintage: 8 products and cross audit; `test_extension.py`; September smoke test of the extended panels | B | Library function used by `rebuild`/`update`; earlier cutoffs cut, later cutoffs extend; the end-to-end run with real September annexes is pending |
| RC1 regression | `regression/catalog.py`, `compare.py`, `golden.py` | 102 references; suite of 704 tests | A | Requires `ICML_GOLDEN_DIR`; the references are not in the repository |
| Figures of a delivery (optional tool) | `plots/delivery.py` · `build_all`, `plot_dashboard` | `test_plots_delivery.py` (17) and visual inspection of the 87 figures | A | Read-only; changes no number |
| Integrity of a repository copy | `operations/checksums.py`; `SHA256SUMS`; `icml checksums` | `test_checksums.py`, including a test that fails when the listing is stale | A | Detects missing or altered files; the listing equals the git-tracked set |
| Months after the frozen vintage | `recalculation/extension.py`; `vintage_root.py` | `test_extension.py`; smoke test with `ICML_CUTOFF=2026-09` | B | Rules defined and tagged; not yet run end to end |
| Delivery READMEs | Not generated by `build_delivery` | Manual review | B | Can drift from the delivery |

## B. Gaps and risks

| # | Gap or risk | Type | Priority | Effect | Status 2.6.0 |
| --- | --- | --- | --- | --- | --- |
| 1 | No rule to extend the informality priors and the census bridge to new months; the model weights (`weights.pt`) are not in the repository, only its priors | Confirmed failure | High | September 2026 could not be computed | **Resolved** with explicit carried-forward rules (seasonal persistence for the priors and the national sectoral composition, last month for the bridge), tagged in the products. Pending: the end-to-end run with real annexes and wiring the H10 extraction of the new annex for the sectoral composition |
| 2 | Three pieces without a unit test of their own: the census bridge refresh, the strict H5/H6 window and `verify_delivery` | Confirmed failure | Medium | A regression in them is only detected in a full run | `verify_delivery` covered in 2.6.0; the other two remain open |
| 3 | The RC1 references, the current vintage and the deliveries travelled inside the repository (about 600 MB) | Potential risk | Low | Dependence on the remote repository | **Changed:** deliveries and the current vintage are generated locally and ignored by git; the repository is about 100 MB; the RC1 references are outside it (46 golden tests skip) |
| 4 | The cutoff is fixed at import time through `ICML_CUTOFF`, and an earlier vintage needed a separate tool | Potential risk | Medium | A process with the wrong variable would mix calendars | **Partly resolved:** the CLI relaunches with the right cutoff and the vintage root is a library function; the import-time variable remains |
| 5 | The delivery READMEs are written at packaging time, not by the builder | Confirmed failure | Low | They can drift from the real delivery | Open |
| 6 | In an earlier vintage the informality observations keep the provenance label "Agosto 2026" | Confirmed failure | Low | Cosmetic | Open |
| 7 | Heterogeneous tolerances: 1e-4 in departmental anchors, 1e-3 in reconciliation and audit, 1e-5 in quality, 1.1 persons against the published reference | Potential risk | Low | No single documented policy | **Documented** in the framework's gate table; the reference comparison uses 0.1 persons / 1e-6 for rates since 2.6.0 |
| 8 | The torch version used to generate the original priors is not recorded, and the multiple-optima warning of rho (0.989 local vs 0.898 global) is not measured | Needs confirmation | Medium | Affects reproducing the priors, not reusing them | Open |
| 9 | 2001-01 splices: about 0.9 pp error in the PET share (around 1.4 % in the 1993-2000 levels); 8 small cities with residual above 0.5 pp measured by windows; an employment jump of +2.8 % persists | Documented methodological limitation | Medium | Uncertainty of the reconstructed history | Open |
| 10 | Independent scientific validation of H9 not approved; publication is not authorized by the system itself | Governance | High | Results are not publishable as official | Open |
| 11 | Dependency pins covered Python 3.12 while the package declared 3.11 to 3.13 | Potential risk | Low | Reproduction not guaranteed outside 3.12 | **Resolved:** installable from PyPI on 3.11+; the reference is reproduced under the latest numpy/scipy/scikit-learn/pandas; the one real cap is `xgboost<3.2` |
| 12 | Two sectoral microdata tests skip because their input is outside the tree | Confirmed failure | Low | The B / D_E split with microdata is not verified in the suite | Open |
| 13 | The main flow drops no rows, but every Excel extractor was not audited row by row | Needs confirmation | Medium | A silent exclusion inside an extractor would go unnoticed | Open |
| 14 | MIT license | Governance | Low | None | Resolved |
| 15 | *(new in 2.6.0)* The reference vintage was five products behind the code and the equivalence gate did not block | Confirmed failure | High | A code change could alter numbers without a refreeze | **Resolved:** refrozen from one recompute; the gate blocks; `tools/refreeze_reference.py` and `REFERENCE_VINTAGE.md` |
| 16 | *(new in 2.6.0)* The modeling stage changes its estimates across xgboost minor versions (up to 38,900 persons of departmental PET between 3.1 and 3.4) | Methodological fragility | Medium | The reference is reproducible only under xgboost 3.1.x | Capped in `pyproject.toml`; a more version-stable predictor is a methodological decision |

## C. Recommendations

| Priority | Recommendation | Addresses | Status 2.6.0 |
| --- | --- | --- | --- |
| 1 | Define and approve the extension rule to new months (priors and bridge); validate with the first real month after August | Gap 1 | Rule implemented and tagged; the first real month is the validation |
| 2 | Wire the H10 monthly sectoral extraction of the new annex into the recompute | Gap 1 | Open |
| 3 | Add unit tests for the census bridge refresh, the strict H5/H6 window and `verify_delivery` | Gap 2 | Open |
| 4 | Generate the delivery READMEs from the builder, with cutoff, date, version and active methods | Gap 5 | Open |
| 5 | Record the torch version, seeds and training configuration of the priors, and measure the multiple-optima warning | Gap 8 | Open |
| 6 | Pass the cutoff as an explicit parameter of each run instead of an import-time variable | Gap 4 | Partly (CLI relaunch); open at the library level |
| 7 | Audit the nine extractors row by row and declare any exclusion | Gap 13 | Open |
| 8 | Fix the provenance labels per vintage and include a minimal input for the microdata tests | Gaps 6, 12 | Open |
| 9 | Evaluate a predictor whose estimates do not depend on the xgboost minor version, or pin the tree algorithm explicitly | Gap 16 | Open (methodological) |
