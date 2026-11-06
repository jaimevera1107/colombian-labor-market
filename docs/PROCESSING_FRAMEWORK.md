# GENERAL DATA PROCESSING FRAMEWORK — ICML 2.0

Version 2.6.0 (originally written 2026-11-03 for 2.3.0; command names, statuses and the behaviour after the frozen cutoff updated). Its companion, with the traceability matrix, the gaps and the recommendations, is [TRACEABILITY_REPORT.md](TRACEABILITY_REPORT.md).

## 1. Purpose and scope

ICML 2.0 (package `icml`) produces monthly series of labor market, informality and employment by sector for the 33 territories of Colombia, from 1993-01 to the last month with DANE annexes available (today 2026-08), in two universes: **census** (whole territory, CNPV 2018 population) and **GEIH** (the part of the territory the GEIH represents).

- **Inputs:** DANE annexes in Excel (monthly GEIH labor market, informality in moving quarters, annual departmental labor market), historical references (ENH 1993-2001, population projections, GDP and ISE, 2015 sectoral annexes), the CNPV 2018 and frozen parameters (census bridge, informality model priors, sectoral model features).
- **Products:** eight internal tables (labor, informality and sectoral, each national, departmental and by city; the sectoral one without cities) delivered per universe, in a full version with traceability and in a simple version.
- **Units:** territory-month. Departments = 32 departments and Bogotá (additive to the national total); cities = 33 GEIH urban domains (non-additive signals); sectoral = 15 sectors.
- **Scope of the processing:** reception and validation of annexes, source preparation, labor estimation, 2001-01 splice, informality estimation, sectoral estimation, cross audit and delivery. The results are research products: they are not official statistics, the sectoral component is experimental and publication is not authorized by the system itself.

## 2. Mandatory processes

A valid run goes through nine processes in this order; each depends on the previous ones and any blocking failure stops the run without publishing anything.

1. **Reception and planning.** The fingerprints (hashes) of the ingestion and of the frozen parameters are compared with those of the last delivery. The annexes are detected, the cutoff is set at the last month with both monthly annexes, and every workbook is checked to declare inside the month its name claims. The plan is `RUN`, `NO_CHANGES` or `BLOCKED`.
2. **Source preparation.** Nine extractors turn the Excel files into audited tables and an immutable view of the labor sources is assembled with its manifest. All nine must finish without error.
3. **Labor chain.** Seven chained stages: national; urban and departmental, which depend on the national one; integration; modeling; hierarchical reconciliation; and quality. They produce the three labor bases (nationals, departments and cities).
4. **Labor reconstruction 1993-2000.** Draws the working-age population as a straight line ending at the official 2001-01 value and gives the 1993-2000 rates the dynamics of the GEIH stage (deterministic noise and official seasonal pattern), with exact identities; it replaces the 2.3.0 PET splice. The accounting identities close exactly and the official months do not change.
5. **Regeneration of the informality sequence (H5/H6).** Rebuilds the latent national series and the urban sequence from the annexes and the new labor product, and compares them with the frozen sequence.
6. **Informality closure (H9).** Calibrates the departmental priors to the national target every month, derives cities and nationals in both universes and applies the 2001-01 splice.
7. **Sectoral estimation (H16/H17).** Predicts the sectoral composition per territory, reconciles it with labor employment and exports it as an experimental product.
8. **Cross audit.** Checks the coherence of the eight products with each other and compares them with the reference vintage.
9. **Consolidation and delivery.** In anchored mode it grafts the frozen years from the current vintage; then it splits by universe, verifies the delivery and promotes it as current. The simple files are generated afterwards, from the verified delivery.

## 3. Rules per source or component

Every source is registered with its hash and read from the ingestion; what changes per source is how its period is identified and what blocks it.

| Source | Role | Period | Particular rule | Blocks if |
| --- | --- | --- | --- | --- |
| Monthly GEIH annex (labor market) | National totals and urban windows | Last month of the national table, read from the workbook | Sets the cutoff together with the informality one | Its pair is missing, the content declares another month, or two different files claim the same month |
| Informality annex | National and urban moving-quarter windows | End of the last window | Incomplete windows are rejected | In anchored mode, new or revised figures appear in frozen years |
| Annual departmental annex | Annual anchors of the 33 territories | Last year covered | Defines the years the anchored mode freezes (today through 2025) | The anchors do not close within the stage tolerance |
| Historical references (ENH 1993-2001, population, GDP and ISE, 2015 sectoral annexes) | Pre-GEIH reconstruction and auxiliary signals | Fixed | Catalog with hashes; binary `.xls` files never decide the cutoff | A catalog file is missing or its hash changed |
| CNPV 2018 and frozen parameters | Census universe, bridge between universes and priors | Fixed | Reused without retraining | In anchored mode, their fingerprint changes |

**Modes.** The **anchored** mode (default) recomputes everything but keeps the years covered by the departmental annex intact, grafting them from the current vintage. The **total** mode rewrites the whole series and requires explicit confirmation; it is used after a methodological change. A cutoff other than the frozen vintage is handled by the vintage root (`icml.recalculation.vintage_root`): an earlier cutoff cuts the frozen panels, a later one extends the frozen parameters with explicit, tagged rules (see [production/EXTENSION_BEYOND_FROZEN_CUTOFF.md](production/EXTENSION_BEYOND_FROZEN_CUTOFF.md)).

## 4. Treatments and transformations

The system does not drop records for quality reasons: it completes every territory-month by reconstruction or estimation with declared provenance, and keeps gaps only where the magnitude does not exist.

| Treatment | What it does | Type | Application |
| --- | --- | --- | --- |
| Normalization | `YYYY-MM` periods, two-digit DANE codes, annex names without accents or spaces | Format | Mandatory |
| Accounting reconciliation | National and departmental annual anchors; the 33 departments add exactly to the national total (quadratic programming and proportional adjustment) | Deterministic correction | Mandatory |
| ENH→GEIH splice and temporal disaggregation | Takes the 1993-2001 annual history to months (Chow-Lin) and transfers the GEIH seasonality | Estimation | Mandatory |
| Windows to months | Recovers latent monthly values from the published moving windows and controls implausible jumps | Estimation | Mandatory |
| Urban reconstruction | Donors for the nine cities without GEIH history (2007-2020), 1993-2020 backcast and Cundinamarca's synthetic signal | Estimation by similarity | Mandatory |
| Departmental models | Rates for the territories without direct observation, with geographic cross-validation | Model-based imputation | Mandatory |
| PET linearization | Minimum-curvature treatment of the reconstructed working-age population | Deterministic correction | Mandatory |
| Representativeness | Factors that separate the GEIH universe from the census universe | Derivation | Mandatory |
| Informality | Latent national series and urban sequence from the annexes; priors of a frozen neural model calibrated month by month to the national total; three scenarios for the 2020 gap (one chosen, two as sensitivity) | Estimation and model-based imputation | Mandatory |
| Census bridge | Refreshes its levels from the current labor product when they differ by more than 1e-3 persons; the GEIH universe is rebuilt with the frozen factors | Deterministic correction | Conditional |
| 2020-2021 residual | The difference between departments and the national total is recorded and absorbed by the rate; it blocks only above 1 % of employment | Documented conservation | Conditional |
| Sectoral | Observed calendar months, inversion of moving averages, 1993-2001 homologation, departmental priors and entropy reconciliation | Experimental estimation | Mandatory |
| 2001-01 splices | Shift the pre-2001 stretch to the level of the anchored regime (informality rate; PET share with labor rates untouched) | Estimation | Conditional (active since 2.3.0) |
| GEIH universe without representation | Where the GEIH represents nobody (9 territories, 2001-2013) the levels are 0 and the rates are empty, with an explicit status | Conservation of gaps | Mandatory |

The frozen parameters (census bridge, informality model priors, sectoral features) are never retrained during a run. For a month later than the frozen cutoff they are carried forward with tagged rules.

## 5. Validation, traceability and quality control

A result is acceptable only if it passes every blocking gate; diagnostic checks and independent scientific evidence are recorded but do not stop the run.

**Blocking gates**

| Moment | Control | Limit |
| --- | --- | --- |
| Reception | Pair of annexes of the same month, content period equal to the name's, no ambiguous files | Exact |
| Anchored plan | Fingerprint of the frozen parameters unchanged; modified existing inputs only with express authorization | Exact |
| Preparation | The nine extractors finish correctly | 9 of 9 |
| National stage | Annual and monthly identities; relative displacements of the reconstruction | 1 person; 10 % annual, 15 % monthly |
| Reconciliation | National, joint and anchor closure | 1e-3 persons |
| Labor quality | Accounting identities of the three bases | 1e-5 persons |
| Informality | Regenerated sequence equivalent to the frozen one (from 2001-01 with the labor reconstruction); required completeness checks and PEA/PET identities | Comparison tolerances |
| Informality splice and labor reconstruction | Identities PEA = employed + unemployed and PET = PEA + inactive exact; PET straight from 1993 to 2000; official months identical; shares within (0, 1] | 1e-6 persons in the identities; 1e-9 (5e-4 in the ICML national) in the shares |
| Cross audit | Coherence between labor, informality and sectoral (employment, formal and informal identities, departmental sums) | 1e-3 persons; shares 1e-8 |
| Reference equivalence (frozen cutoff only) | The eight candidates reproduce the frozen products | 0.1 persons; rates, shares and factors 1e-6 |
| Anchored mode | No cell of a frozen year changes after the graft | Exact |
| Delivery | 52 checks: hashes, shapes, identities between universes and full coverage | 52 of 52 |

**Traceability.** Every stage writes its artifacts with the SHA-256 of inputs and outputs and a run manifest. The integral run leaves a report with the state of each component (`INTEGRAL_RECOMPUTE_REPORT.json` next to the delivery). Every delivery records in its manifest the hash of each file, the column map, the software version, the input fingerprints and the active methods. Output folders must be new: the system refuses to overwrite. The whole repository also carries `SHA256SUMS`, which lets anyone check that a copy is complete and intact (`icml checksums`).

**Reproducibility.** Reads and writes are deterministic and the regression suite compares each stage with the 102 RC1 references when they are available. At the frozen cutoff a recompute reproduces the eight products of the reference vintage byte for byte in the locked environment, and within 0.01 persons under the latest numpy, scipy, scikit-learn and pandas; two runs with the same configuration also coincide byte for byte. The modeling stage depends on the xgboost minor version, which is therefore capped (see [production/REFERENCE_VINTAGE.md](production/REFERENCE_VINTAGE.md)).

## 6. Consolidation and generation of results

The delivery is built only after the recompute ends in a clean state and the cross audit passes.

1. **Starting products.** Three labor bases from the quality stage, three informality ones from the H9 closure and two sectoral ones from the experimental layer.
2. **Graft (anchored mode only).** For the years covered by the departmental annex the figures of the current vintage are taken, for the open years the recomputed ones; then it is checked that no frozen cell changed.
3. **Split by universe.** Each product is distributed according to a declarative specification:
    - the **census** universe receives the full levels;
    - the **GEIH** universe receives the represented ones, their derived rates and the coverage status of each department-month;
    - the national GEIH labor figure is the one published by DANE, with the sum of represented departments as a diagnostic;
    - the cities are the same series in both universes.
4. **Manifest and verification.** The manifest, the 52-check verification and the recompute report are written in a dated folder (Bogotá time) that names the cutoff and the mode (`<stamp>_cutoff-YYYY-MM_<anchored|total>`).
5. **Promotion.** The eight products become the current vintage (`datos/2_procesamiento/vigente/`), which the next anchored recompute takes as the reference for the frozen years.
6. **Simple files.** Cut from the verified delivery: only date, year, month, territory and the variables of each domain, in CSV and XLSX, without traceability columns (`<delivery>_simple`).

| Product | Comes from | Census universe | GEIH universe |
| --- | --- | --- | --- |
| Labor national | Quality + labor reconstruction | Full ICML | Published by DANE |
| Labor departments | Reconciliation + quality | Full levels | Represented and derived rates |
| Labor cities | Integration + quality | Urban signal | Same |
| Informality (3 levels) | H9 closure + splice | Full | Represented universe |
| Sectoral (national and departmental) | H16 predictor + H17 layer | Full | Represented proxy |

## 7. General compliance conditions

- **Order:** the processes run in the sequence of section 2; no stage consumes the outputs of a stage that did not finish correctly.
- **Immutability:** the ingestion and the frozen parameters are not modified during a run; every run writes to new folders and never overwrites a delivery.
- **Conservation:** the 33 departments add to the national total; the identities PET = PEA + inactive, PEA = employed + unemployed and employed = informal + formal hold.
- **Coverage:** every product has the 33 territories and every month from 1993-01 to the cutoff; the only gaps allowed are those of territories without representation in the GEIH universe.
- **Traceability:** every delivery file has its hash in the manifest, and the manifest records version, inputs and active methods.
- **Change control:** a change that alters published figures of closed years is methodological. It requires a new version, a methodological note, a changelog entry, a total recompute and a refreeze of the reference vintage. A change in the frozen parameters blocks the anchored mode.
- **Reproducibility:** with the same ingestion, the same parameters and the same configuration, the products are identical byte for byte.

**Completed-run criterion.** A run is considered correctly completed when all of these hold:

1. The plan was `RUN` without blockers.
2. The nine extractors and every stage passed their gates.
3. The recompute ended in an audited state (or audited with splices, provided a splice is active), the cross audit passed and, at the frozen cutoff, the eight products reproduce the reference.
4. In anchored mode, no frozen cell changed.
5. The delivery passed the 52 checks, with full coverage in its 16 files.
6. The manifest was written and the products were promoted to current.
