# Informality: how the three bases are built (milestones 5 to 9)

Condensed from the milestone write-ups of 2.2.0–2.2.13 (kept in git history). Every number here is a research estimate; the independent scientific validation of H9 is not approved and the system never authorizes publication.

## Sources, and why they cannot be spliced naively

| Period | Source | Use |
|---|---|---|
| 1993–2000 | No informality observations; ENH-based labor reconstruction | Backcast of the national rate (no anchor) |
| 2001–2006 | DANE ECH, 13 areas aggregated, "up to 5 workers" criterion, April–June windows | Six aggregate anchors (T5) |
| 2007–Mar 2021 | DANE GEIH, 23 cities + 13 areas, T5 criterion, 3-month moving windows | Regularized inversion of rates |
| 2021–cutoff | DANE GEIH new definition, 23 cities + 13 areas + national, 3-month windows | Exact inversion of counts (least squares) |

The 2021 change of definition is a break: the series are joined with a documented bridge (2.46 pp national break, `regime_splice`), never by assuming the definitions are equal.

## Chain (what `run-integral --mode recompute` does for informality)

1. **H5 national** (`informality/national.py`, `historical.py`): latent monthly national series from the windows; the 2020 gap is filled with one of three scenarios (`interpolated` chosen; `seasonal_2019` and `urban_shock` kept as sensitivity, 12 months of alternatives in the product).
2. **H6 urban** (`informality/sequential.py`, `urban_backcast.py`): 13 areas → national → 23 cities with DANE windows → 33 signals (ten cities without GEIH history use donors from the Pareto study; Cundinamarca is a synthetic signal). Signals are non-additive.
3. **H7/H8 features and priors** (`feature_consolidation.py`, `mlp*.py`, `census_transfer_experiment.py`): 38 labor features per department-month, clusters shared with the labor stage; one residual MLP trained on the 23 cities' latent rates (2007–2025 excluding 2020, 4,968 rows) gives departmental priors; the CNPV-2018 bridge transfers them between the full and the GEIH universes. The priors are **frozen** (`parametros_congelados/priors_mlp_h9`); the MLP is not retrained in production.
4. **H9 closure** (`informality/finalize_block.py`): every month the departmental priors are calibrated (KL) to the national target so informal + formal = employed in both universes; cities and nationals derived; the 2001-01 splice applied. Output: the three informality products.

## Evidence that matters

| What | Value |
|---|---|
| MLP residual, held-out MAE (T5 2007–2019 / GEIH 2023–2025) | 5.5 / 11.4 pp (ridge 9.5 / 10.7; mean of training cities 8.7 / 9.6) |
| Calibration intervention on the chosen candidate (weighted mean / max) | 8.1 / 13.6 pp (19-feature MLP); 12.1 / 15.0 pp (direct urban signal) |
| Alternative calibrators (KL, L2, L2-variance, L2-temporal) | same mean intervention within 0.001 pp; KL kept |
| Closure direction (`FULL_FIRST` vs `GEIH_FIRST`) | the other margin deviates 0.19–0.21 pp either way; `FULL_FIRST` adopted |
| 2020 scenarios, max range across departments | reported in `13_2020_alternativas_33_departamentos.csv` |
| National break at 2001-01 after the splice | +0.32 pp (was +2.78) |

## What is not claimed

No departmental informality is observed; the priors transfer an urban model to departments, and the quality gate (`quality_gate.py`) says so in every run (`G6`, `G7`: BLOCK by design). The 13- and 23-city views are diagnostics of one simultaneous candidate, not a certified sequential run.

## Reproduce

`icml informality --help` lists the experiments; the production path is `icml rebuild` / `update` (H5/H6 regenerated from the annexes, H9 closed with the frozen priors). `reference/` keeps the original MLP configuration and an audit-only copy of its code.
