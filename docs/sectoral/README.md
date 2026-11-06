# Sectoral employment: how the experimental product is built (milestones 10 to 17)

Condensed from the milestone write-ups of 2.2.14–2.2.18 (kept in git history). The sectoral product is **experimental and non-canonical**: it never replaces the labor bases.

## Observed support

| Period | Source | What exists |
|---|---|---|
| 2015–cutoff | DANE GEIH monthly annex | 13 published activity groups per calendar month, national only; the B / D_E split is an assumption (microdata needed, not in the repo) |
| 2007–2014 | DANE historical annexes (CIIU Rev. 3), moving quarters | Inventory and normalized observations; no monthly 14-branch observations |
| 2001–2015 | Bridge CIIU3 → CIIU4 on the 2015 overlap (three traceable scenarios) | National shares only |
| 1993–2001 | ENH, four broad groups, September | Homologation to 15 categories, exploratory |
| 2015–2025 | DANE annual sectoral shares, 23 departments (+ Bogotá external reference) | Annual anchors, soft priors |

Rules that hold everywhere: a moving quarter or an annual figure constrains its window, it is never promoted to a month (`sectoral/monthly.py`, `ensure_direct_monthly`); observed DANE data are never rewritten.

## Chain

1. **National monthly composition** (`sectoral/monthly.py`, `monthly_backcast.py`, `vintage_bridge.py`, `historical_homologation.py`): one share per sector and month, 1993–cutoff, with `source_status` saying what is observed and what is reconstructed (`12_composicion_nacional_unificada_1993_2026.csv`).
2. **Departmental priors** (`sectoral/departmental_prior.py`): non-canonical composition priors from population, GDP groups and the national composition.
3. **Territorial predictor** (`sectoral/predictive_*.py`): 38 original labor features + lagged GDP; ensemble 50 % ridge / 50 % XGBoost (14 branches), selected on LOGO 2015–2024 with a predefined weight grid, 2025 held out. Bogotá never trains; the annual anchors are soft priors in the historical reconstruction.
4. **Reconciliation** (`sectoral/reconciliation.py`, `integral.py`): monthly IPF so that departments add to the national sector margins and each department keeps its own employment; represented universe by the same shares on the represented employed.

## Evidence (bundle refrozen in 2.6.0 on the current labor base)

| Metric | Value |
|---|---|
| Ensemble MAE, LOGO 2015–2024 / 2025 held out | 1.160 / 1.268 pp per cell (ridge baseline 1.236 / 1.370) |
| GEIH annual anchors, MAE after reconciliation | 0.203 pp |
| Bogotá, pre-anchor external MAE / after | 1.866 / 0.092 pp (the second is fit, not prediction) |
| Largest monthly reconciliation adjustment vs prior | 5.7 pp (2020) |
| Backcast sensitivity 2015 → 1993 (no attenuation vs 12-year half-life) | up to 23.0 pp in one cell |

## What is not claimed

Departmental sector labels are never observed; the territorial structure before 2015 is an assumption with a declared half-life. `16_puerta_calidad.json` lists the critical limitations with every run. For months after the frozen cutoff the national composition is carried forward until the H10 extraction of the new annex is wired (see `../production/EXTENSION_BEYOND_FROZEN_CUTOFF.md`).

## Reproduce

`icml sectoral --help` lists the tools; the production path retrains the predictor inside `icml rebuild` / `update` with the current labor base (`sectorial_h16/` holds the frozen inputs and the reference outputs).
