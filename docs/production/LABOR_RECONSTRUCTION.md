# Labor reconstruction 1993-2000: linear PET and components (version 2.4.0)

Restores two properties of the historical reconstruction that were lost when the stages were migrated, following the author's original national estimation (`1 - Estimación Nacional.ipynb`, sections 2.7 and 2.8). It is a **methodological** change, not part of the equivalence refactor: it rewrites the history before 2001-01 of the three bases, of informality and of the sectoral component. From 2001-01 **the national series do not change**; departments and cities only change in their PET, population and inactive (see "After 2001").

## What was lost

| Property | Before (2.3.0) | Now (2.4.0) |
|---|---|---|
| **PET 1993-2000** | Minimum-curvature curve that keeps the eight ENH annual means (ADR-006): it deviates up to 3.65 % (827 thousand persons) from a straight line and changes direction 6 times in the national series | Exact straight line, from its initial level to the official 2001-01 value. Deviation 0, no change of direction, in the national series, the 33 departments and the 33 cities |
| **Components of the 1993-1999 rates** | Six times less seasonality and five times less volatility than the GEIH stage (unemployment: monthly Δ 0.59 pp vs 1.28 pp; seasonal pattern 1.85 pp vs 3.2 pp) | Dynamics of the GEIH stage (unemployment of the national reference: monthly Δ 1.30 pp, seasonal pattern 3.43 pp; the notebook gave 1.25 and 3.41) |

The PET is a demographic projection: it cannot go up and down. ADR-006 forced it to respect the ENH annual means, which are not collinear (the ENH jumps 9 % in 1996 because of its redesign), and the ups and downs came from there.

## What it does

For every series (the national reference, each department and each city), with its own official months:

1. **Linear PET.** From the median of its first year to its value in 2001-01, with a single slope through the splice.
2. **Levels on the linear PET**, keeping the TO and TD rates: `employed = TO × PET`, `PEA = employed / (1 − TD)`.
3. **Templates.** STL of the irregular component of the official TO and TD (2001 onwards).
4. **Deterministic noise** in TO and TD, at scale `scaling_factor = 0.45` of the official irregular. The seed is `base_seed + MD5("YYYY-MM")` (the territory adds its code so draws are not shared): a month always receives the same noise, whatever the order.
5. **Replacement of the seasonal component** of employed and unemployed by the 2001-2018 pattern of that series, scaled by `previous_mean / reference_mean`, keeping its STL trend and irregular.
6. **Exact accounting closure:** `PEA = employed + unemployed` and `inactive = PET − PEA`.
7. **Linear population** before 2001, in the national series, the departments and the cities (as in the notebook).

The ICML national is the sum of the departments. The files only rewrite the cells that change.

## After 2001: PET and population of the territories

After 2001-01 the national series are official and are not touched, but the **departmental PET is saw-toothed** (median of 153 changes of direction in 308 months, jumps of up to 24 % from one month to the next) while the national one is smooth (none), and so is the cities' (92). The territorial population is smoother but breaks every January. A demographic projection does not behave like that. With `smooth_territories`:

* **Departments:** each one's **share** of the national total is smoothed with a minimum-curvature curve that keeps its annual mean. It is a linear operator that maps a constant to itself, so the 33 shares still add to 1 and the departments still add exactly to the ICML national. It is multiplied back by the total.
* **Cities:** their own level is smoothed with the same operator (they add to nothing).
* **Employed, unemployed and labor force do not change**; the inactive absorb the PET (`inactive = PET − PEA`), and the employment and participation rates are recomputed on the new PET. The unemployment rate does not change.
* **GEIH universe.** The territories the GEIH represents completely take the smoothed value (their factor is still exactly 1, so they do not change coverage class); the partially represented ones absorb their own change, and the unrepresented ones stay at zero. While every territory is at least partially represented (from 2014-01) the sum of the represented part is still the GEIH national, exactly (2e-8 persons). Before 2014, when nine territories are outside the GEIH, that (informative) sum can move by up to 11 thousand persons.
* **The saw-tooth is in nine territories.** Arauca, Casanare, Putumayo, San Andrés, Amazonas, Guainía, Guaviare, Vaupés and Vichada absorb almost all the noise of the reconciliation (their total has 184 changes of direction; the group of the other 24 has 2). That is why the split between both groups is smoothed first and then each group inside.
* The smoothing goes **first**: the pre-2001 straight line ends at the smoothed 2001-01 value, not at the original saw-tooth.

It is not a literal straight line: a single line from 2001 to 2026 can neither keep the annual means nor add to the official national total, which is not straight either. It is the straightest curve that satisfies both conditions (2 changes of direction instead of 153).

## Where it departs from the notebook (and why)

| Notebook | Here | Reason |
|---|---|---|
| Noise in TO, TGP and TD separately; seasonal replacement of PEA and inactive separately | Noise in TO and TD; PEA is the sum and inactive the remainder; TGP stays implicit | The notebook left `PEA − (employed + unemployed)` off by up to **357 thousand persons**. The quality gate requires 1e-5 |
| Population also straight | Same, before 2001 (`linearize_population = true`); after 2001 it is smoothed in the territories | Requested that way |
| Series from 1991-11 | From 1993-01 | The project starts in 1993 |
| PET flat for one month in 2000-12 → 2001-01 | Single slope through the splice | Avoids a one-month kink |
| National series only | The same method in every department and city | Every territory gets its real seasonality. Propagating the national change to the territories attenuated the ICML to 70 % |

## It replaces the PET splice (2.3.0)

The straight line anchored to the official 2001-01 value already closes the jump of the PET/population share that `labor_base_splice` estimated (+1.6 points in one month). Running both would move the level the line starts from, so they are **mutually exclusive**: the run fails if both are active. `labor_base_splice.toml` stays at `enabled = false` and is kept to reproduce 2.3.0. The informality splice (`regime_splice`) stays in force.

## Measured result (August 2026 vintage)

| Measure | Before | After |
|---|---|---|
| Deviation of the PET from a straight line, 1993-1999 (national) | 827 thousand (3.65 %) | 0 |
| Unemployment, monthly Δ 1993-1999, ICML | 0.26 pp | 1.21 pp (2001-2010: 1.26 pp) |
| Unemployment, monthly Δ 1993-1999, national reference | 0.65 pp | 1.28 pp |
| PET jump 2000-12 → 2001-01 | +2.25 % | +0.28 % (one month of slope) |
| Maximum accounting residual | — | below 4e-9 persons |
| Sum of departments vs ICML | exact | exact |
| National informality jump at 2001-01 | +0.32 pp | +0.32 pp (unchanged) |
| Departmental PET after 2001, changes of direction (median of 33) | 153 | 2 |
| PET of the nine territories outside full coverage, changes of direction | 155 to 191 | 0 to 18 |
| Departmental population after 2001, changes of direction (median) | 6 | 2 |
| Departmental PET and population before 2001, changes of direction | 15 and 14 | 0 and 0 |
| Sum of departments vs ICML after 2001 | exact | exact (error of 3e-8 persons) |
| Annual mean of the departmental PET after smoothing | — | changes at most 0.017 % |
| GEIH coverage classes (complete, partial, unrepresented) | 7,392 / 1,368 / 1,404 cells | equal (0 cells change class) |

Employed levels change between −2.3 % and +2.1 % depending on the year relative to 2.3.0 (the PET change carries to the levels because the rates are kept). Sectoral shares do not change (1e-12); employed by sector add exactly to labor employed.

## Limits

* **Smoothing the territories moves figures of the official period.** The median change of the departmental PET is 0.18 % and the 99th percentile 2 %; the maximum, 12.7 %, occurs in six cells of Chocó in 2020, where the original had a spike. Population changes up to 3.2 %; in the cities 4.1 % and 3.3 %. Annual means barely change (0.017 %) and national totals do not change.
* **Indirect effect on the sectoral component.** The sectoral integration (H16) uses the departmental PET and inactive as margins, so after 2001 the departmental sectoral shares move little: median 0.003 points, 99th percentile 0.15 points, maximum 0.40 points (Vichada, agriculture, 2021-07). The national ones do not change (1e-12).
* **Rounding.** In informality and sectoral, columns that do not change (employed, unemployed, informal) differ in the last digit of the text (up to 1e-6 persons): they are re-derived with another order of operations. The figure is the same.
* **The 1993-2000 ENH annual means are no longer anchors.** The PET stops respecting them by design and the annual levels of employed and unemployed vary by up to a couple of percentage points; the ENH rates are kept.
* **The noise and the seasonality are generated**, not observed. They give the history the dynamics of the GEIH stage, but they do not inform what happened month by month in 1993-1999: they are a continuity device, not evidence.
* **The ICML has less employment noise than the reference** (monthly Δ of TO 0.84 pp vs 1.26 pp): the noise of the 33 departments is independent and diversifies when summed. It is the natural difference between an aggregate of small samples and a national figure.
* **Informality 1993-1999 gains no monthly dynamics of its own** (monthly Δ of the rate 0.13 pp): its rate is still the backcast one and only the counts change, which are rate × employed.
* The notebook's original national run uses its own monthly disaggregation; here the input is the already reconciled national series of the national stage, so the levels differ from the notebook's Excel between −8 % and +7 % depending on the variable and year, while the shape (straight PET, volatility, seasonality) coincides.

## Parameters

`configs/rc1/labor_reconstruction.toml`: `linearize_population = true`, `smooth_territories = true`, `scaling_factor = 0.45` (the notebook's), `base_seed = 42`, STL of period 12 with seasonal window 13 and robust, reference pattern 2001-2018, safety floor of 5 % per level (never applied in the August run).

## To revert

1. Set `enabled = false` in `labor_reconstruction.toml` (and, for the 2.3.0 splice, `enabled = true` in `labor_base_splice.toml`).
2. Recompute in total mode: `python -m icml recalc --root . --mode total --confirm-total`.

With the restoration off and the PET splice on, the vintage coincides byte for byte with the 2.3.0 one (as measured in 2.4.0).
