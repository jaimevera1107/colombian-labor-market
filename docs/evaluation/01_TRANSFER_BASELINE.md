# Post-closure transfer evaluation — 2.0.0 baseline

Command: `icml evaluation run --config configs/rc1/evaluation.toml
--integration-run <run>/integration --departmental-run <run>/departmental
--runs-dir runs --run-id <id>` (about 30 s per hidden department).

## Design

Each of the 22 anchored, non-synthetic departments is hidden in turn and
treated as an unanchored territory: models and clusters are refitted
without it, the panel is built without its references and the
hierarchical closure runs without its anchors. Its annual means
2007–2025 are compared with its official anchors (418 department-years
per candidate), before the closure (`model`) and after it (`closed`, the
published method).

Candidates: `xgb_ward` (published, ADR-006), `hybrid` (hito 4 rule),
`xgb_none`, and two model-free seeds: `urban_analog` (urban signal rates)
and `national_rates`.

Leakage control: multiplying all labels and anchors of the hidden
department by 1.5 leaves its estimates unchanged
(`tests/regression/test_transfer_evaluation.py`). Cundinamarca is not
hidden (its synthetic signal uses its own anchors). Residual leak:
hyperparameters and architecture were chosen with all departments.

## Results (mean absolute error over department-years)

| Candidate | Stage | Mean rate error (pp) | TD (pp) | TO (pp) | TGP (pp) | Unemployed (%) | Working age (%) | Population (%) |
|---|---|---|---|---|---|---|---|---|
| hybrid | closed | 2.21 | 1.43 | 2.52 | 2.67 | 16.1 | 5.27 | 2.67 |
| urban_analog | closed | 2.23 | 1.49 | 2.63 | 2.57 | 18.7 | 5.23 | 2.67 |
| xgb_ward | closed | 2.90 | 1.42 | 3.43 | 3.86 | 17.8 | 5.27 | 2.67 |
| xgb_none | closed | 2.93 | 1.47 | 3.44 | 3.86 | 18.5 | 5.61 | 2.67 |
| national_rates | closed | 5.14 | 1.89 | 6.57 | 6.96 | 23.1 | 5.23 | 2.67 |
| xgb_ward | model | 2.34 | 1.52 | 2.63 | 2.88 | 17.1 | 5.17 | 0.59 |
| xgb_none | model | 2.34 | 1.53 | 2.63 | 2.85 | 17.4 | 5.44 | 0.59 |
| hybrid | model | 2.37 | 1.52 | 2.68 | 2.92 | 17.2 | 5.17 | 0.59 |
| urban_analog | model | 2.72 | 2.45 | 2.78 | 2.95 | 30.3 | 5.34 | 0.59 |
| national_rates | model | 3.51 | 2.01 | 4.22 | 4.29 | 22.6 | 5.34 | 0.59 |

Population before the closure is the demographic projection; after it,
the reconciled labor population.

Paired differences by department (22 departments, mean of the three
rates, 10,000 bootstrap replicates):

| Comparison | Mean (pp) | 95 % interval | Departments where positive |
|---|---|---|---|
| Ward closed − Ward model | +0.56 | 0.08 to 0.99 | 17 |
| Hybrid closed − hybrid model | −0.17 | −0.30 to −0.04 | 7 |
| Ward closed − hybrid closed | +0.70 | 0.37 to 1.02 | 18 |
| Hybrid closed − urban closed | −0.03 | −0.15 to 0.09 | 14 |
| Urban closed − national closed | −2.91 | −3.61 to −2.21 | 2 |
| Ward model − urban model | −0.38 | −0.63 to −0.11 | 6 |

## Findings

1. **The ranking reverses after the closure.** Before it, Ward is the best
   candidate; after it, Ward is 0.70 pp worse than the hybrid. The closure
   worsens Ward in 17 of 22 departments and slightly improves the hybrid.
2. **After the closure, the departmental model adds no measurable value
   over the urban signal** (hybrid − urban: −0.03 pp, interval includes
   zero). The urban signal carries most of the information (−2.9 pp
   against national rates).
3. **The closure degrades population.** The demographic projection misses
   official GEIH population by 0.59 %; the reconciled labor population by
   2.67 %, and by 7.4 % (Antioquia) and 6.8 % (Valle) when a large
   department is hidden. The national universe gap (1–5 %) is forced onto
   the unanchored subset only, which amplifies it in relative terms — the
   likely mechanism behind Bogotá's 18 % adjustment.
4. **Working age is the largest level error** (about 5 % for every
   candidate, before and after the closure), consistent with critiques 1
   and 2: the denominator, not the rates, dominates level errors.

## Limits

* Anchored departments are larger and better covered by urban signals
  than the ten real unanchored territories (Amazonía/Orinoquía capitals
  with ill-conditioned latent months, San Andrés, Bogotá). This is
  evidence of transferability, not an error estimate for those ten.
* Leave-one-out keeps the other ten unanchored; hiding several
  departments at once would be a harder test.
* Labels before 2007 are not anchored; only 2007–2025 is evaluated.
* Features use the 2026-08 vintage (no as-of reconstruction).
