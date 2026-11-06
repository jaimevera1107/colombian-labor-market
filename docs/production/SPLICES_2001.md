> **Update (2.4.0):** the labor PET splice described here was **replaced** by the restoration of the linear PET and of the components (`LABOR_RECONSTRUCTION.md`). The informality splice stays in force. This note describes what 2.3.0 did and is kept to reproduce it.

# Splices of the 2001-01 seam

**Version:** 2.3.0.dev0. **Status:** adopted. **Type:** methodological change (not part of the equivalence refactor).

## Problem

In 2001-01 the measurement regime changes. Through 2000-12 the values are reconstructions (ENH for labor, backcast without an official anchor for informality); from 2001-01 they are anchored to DANE. The two parts do not meet, and the step is not a change in reality:

* Informality: the national rate jumps +2.78 pp in one month (3 times the 99th percentile of monthly changes), in the 33 cities and in 29 of 33 departments.
* Labor: the employed jump +5.19 %. Decomposed, the real break is in the PET/population share (+1.64 pp in one month; its normal monthly variation has a p99 of 0.06 pp). Population has no break of its own (+0.3 % ± 0.3 %), and the TGP, TO and TD rates have one-month jumps within the normal range.

## Method

**Break.** Regression with a jump and a common slope over 24-month windows on each side: `series = a + b*k + delta*after`. A difference of annual averages mixes the break with a year of drift, and that of a single month amplifies its noise. The estimator is stable with windows of 18 to 36 months (informality 2.46 to 2.55 pp; PET 1.46 to 1.61 pp); with short windows it rises because the backcast stretch of 2000 brings a fall that is not information. The autocorrelation-adjusted standard error is reported.

**Informality** (`icml.informality.regime_splice`). The stretch before the break is shifted by a constant, with the monthly dynamics intact: the national target, every city and the priors of every department (which are then recalibrated to the national target, so they keep adding up).

**Labor** (`icml.pipeline.labor_base_splice`). Only the PET/population share is spliced; the levels are rebuilt with the rates intact:

    PET' = (share + break) x population      PEA' = TGP x PET'      employed' = TO x PET'
    unemployed' = PEA' - employed'            inactive' = PET' - PEA'

Every level except population is multiplied by `k = (share + break) / share`, so all identities and rates are preserved. Departments with their own break (27 of 33 individually significant); the ICML national is the sum of the corrected departments; the pre-2001 DANE reference has its own; the cities use a common break (median) because their 1993-2000 stretch is a backcast of the national series and the individual estimates are noisy (8 of 33 significant).

**Why the labor rates are not spliced.** Around 2000-2001 unemployment turns with the cycle; a break estimator cannot tell a turn from a break (it gave −4.6 pp for TD against −1.0 pp of the monthly jump).

## Scope

* Changes 1993-01 to 2000-12 in labor, informality and sectoral. **From 2001-01 everything is identical.**
* Population, the labor rates of departments, cities and the DANE reference (2e-16) and the frozen parameters do not change. The ICML national rates are recomputed from their levels (they change at most 6.3e-5).
* Since closed history changes, the vintage is recomputed in total mode (`icml recalc --mode total --confirm-total`).
* The census bridge remains a frozen parameter: its departmental levels are refreshed from the current labor product when they differ, and its GEIH universe is rebuilt with the frozen factors.

## Results

| | Before | After |
|---|---|---|
| PET/population break, ICML national | +1.56 pp | +0.01 pp |
| PET/population break, departments | median +1.58 pp | 0.00 pp in all 33 |
| Cities with a step larger than their normal variation | 27 of 33 | 0 of 33 |
| Employed jump 2000-12 to 2001-01, ICML national | +5.19 % | +2.80 % |
| Informal jump, national | +9.55 % | +3.28 % |
| One-month step of the informality rate, national | +2.78 pp | +0.32 pp |

## Limitations

* The PET share is estimated with an error of about 0.9 pp, about 1.4 % in the 1993-2000 levels.
* In 8 small cities the window estimator shows a residual above 0.5 pp (individual estimate not significant); their one-month step is closed anyway.
* The employment jump left at 2001-01 (+2.8 %) is within the normal monthly variation (median 1.4 %; p99 5.2 %).

## To revert

`enabled = false` in `configs/rc1/regime_splice.toml` and `configs/rc1/labor_base_splice.toml`, and recompute. It reproduces the frozen August 2026 vintage byte for byte (as it stood in 2.3.0).
