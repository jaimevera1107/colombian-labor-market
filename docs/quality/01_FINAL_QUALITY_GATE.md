> **Historical file (2.1.1.dev0).** Describes the earlier design of the single panel `territorial_unified.csv` and null national factors before 2001. It is not the current contract. Since 2.1.2.dev0 the delivery uses three separate bases, without `00` in cities/departments, and historical factors equal to 1. See `THREE_BASES.md`. Status names are the 2.6.0 ones.

# ICML — Final labor quality gate (2.1.1.dev0)

## Scope and verdict

It runs **after** `reconciliation`, consuming without modification the six products of `icml-colombia 2.1.0`. **It does not re-estimate** PET, population, employed, unemployed or rates. The main output is a panel of 34 rows per month (`00` national + 33 territories).

**Result on the delivered products:**

- **Accounting integrity and representativeness: passed.** No hard failure.
- **Methodological publication: pending.** `REQUIRES_METHODOLOGICAL_REVIEW`; the linearity alerts must be resolved or justified with their provenance.
- **It must not be labelled a certified labor version nor passed automatically to informality.** It can be used as an inspection base.

### Verified counts

| Control | Result | Treatment |
|---|---:|---|
| Single-panel records | 13,736 | 34 x 404; `00` non-additive |
| Identities | 0 hard failures | Tolerance of 1e-5 persons |
| Representativeness 2001–2026 | 0 failures | Residuals up to 1 person from GEIH rounding |
| Comparisons against the official reference | 2,320 | Maximum deviation 1.8924 % (unemployed) |
| Extreme variation by factor 3 (monthly or annual) | 18 | All urban, unemployed, YoY comparison |
| Sustained rate shifts | 496 | Exploratory; not 496 genuine breaks |
| Monthly population/PET variations >1 % | 2,033 | Mix of steps, real effects and anomalies |
| Series-years with exactly flat population | 506 | All in the unified territorial panel |
| Series-years exceeding 2 % deviation from the annual line | 36 | All PET: 23 territorial, 13 urban |

The largest PET deviation is Chocó (27), year 2020: **13.2119 %** of the annual average. It is a case for source and reconciliation inspection, not an authorization to impose a straight line by manual edit.

The national population `00` is constant within each year 1993–2000, with January steps between years. The nine partially represented territories (81, 85, 86, 88, 91, 94, 95, 97 and 99) show stepped annual population beyond 2000. This contradicts the expectation of a strict linear monthly interpolation. It is not corrected in this gate so as not to alter the delivered labor estimates without rebuilding their dependencies. (Both were addressed in 2.4.0: `LABOR_RECONSTRUCTION.md`.)

## Unified product `quality/products/territorial_unified.csv`

- Key: (`dep_code`, `period`), where `dep_code` **is two-digit text**: `00`, `05`, `08`, ... `99`. When importing the CSV in pandas use `pd.read_csv(..., dtype={'dep_code': 'string'})`.
- Unambiguous alternative key: `territory_id` (`CO-00`, `CO-05`, ...).
- `territory_level=NACIONAL_ICML` and `is_aggregate=true` for `00`.
- `is_additive_member=false` for `00`; **never** add the 34 rows to obtain the national. The correct sum uses only the 33 rows with `is_additive_member=true`.
- `employed`, `unemployed`, `inactive`, `labor_force`, `working_age`, `population`: magnitudes of the **complete ICML universe**, also for `00`.
- `*_represented`: magnitudes assigned to the national reference domain. In `00` from January 2001 they equal the GEIH reference used by the project; before 2001 they are a **reconstructed reference**, **not** an observed DANE national figure.
- `factor_*`: for each magnitude, `*_represented / full level`; in 2001+ the sum `factor_* × level` over 33 departments reproduces the reference. **The factors of `00` are null in 1993–2000:** there is no official national GEIH constraint for those months.
- `coverage_gap_*`: full level minus represented. Before 2001 it must not be read as population excluded by an official GEIH.
- `source`, `reference_status`, `territory_name`, `year` and three computed rates are part of the public contract.
- Per-unit comparisons come from `reconciliation/products/official_deviation.csv`, kept unchanged.

## Audits and limits

- `identities_territories.csv`: per-record closure of the 34 units; `identities_urban.csv`: closure of the 33 urban signals.
- `reference_alignment.csv`: monthly comparison between the 33, `00` and the national reference. **The equality requirement of the represented domain starts in 2001-01**. Before that it is diagnostic only, without recalibrating history.
- `official_deviation_check.csv`, `official_accuracy_summary.csv`: 2,320 official lines and their formulas are reviewed; no input value is rounded to force closure.
- `extreme_changes.csv`: increases `>=200 %` or symmetric decreases (reduced to at least a third), plus zero transitions. MoM and YoY are computed. The percentage change and the rule appear separately. No division by zero.
- `structural_breaks.csv`: search with contiguous 12-month windows over rates. Thresholds: unemployment 5 pp; employment 4 pp; participation 4 pp. Consolidation of nearby episodes. Contextual labels for 2001, the 2020 pandemic, the 2021 frame and the 2014 expansion. **No causal statistical test of structural change nor automatic accusation of error.**
- `demographic_jumps.csv`: alert when PET or population changes more than 1 % between months, distinguishing the typical steps of old annual projections.
- `annual_linearity.csv`: separate OLS fit per territory-year-variable and maximum relative deviation from the line. It also detects completely flat years that generate December-to-January jumps.
- `audit/summary.json`: status, tolerances, counts and blocking failures.

## Criteria to close the gate

1. Accounting failures, duplicates, missing months, rates outside [0,1] or an unexplained difference with the references **block technically**.
2. Alerts on linearity or important breaks **block the methodological certification** until they have a documented review and decision. A pandemic jump can be admitted with evidence; an annual-projection step must be explained or corrected upstream.
3. If a denominator or method changes at the source, generate a **new vintage**, revalidate its models/dependencies and run G0–G6 again. The 2.1.0 product and its references are not modified.
4. The unified output can be consumed as an **inspection candidate**. For productive consumption by informality, require an explicit approval manifest from the authorized owner and verification of the vintage.

## Execution

```bash
icml quality run \
  --config configs/rc1/quality.toml \
  --reconciliation-run runs/<id>/reconciliation \
  --runs-dir runs \
  --run-id final-gate-001
```

SHA-256 and the stage `manifest.json` are generated through `ArtifactStore`; the previous stage is not modified. `icml run` includes this seventh stage after `reconciliation`. The `run.json` of a **new** run includes `quality_gate.certified_for_publication` and the hash of the summary.

### Delivered reproduction

The gate was run in that environment with the 13 files of the 2.1.0 products ZIP verified byte by byte. 162 unit tests passed (including 6 new ones). The full 2.1.0 regression suite required the frozen Python 3.12 environment (numpy 2.4.4, scipy 1.17.1, xgboost 3.1.3, tempdisagg 0.6.3) and its golden artifacts. That delivery **did not claim** to reproduce those 288 trials under the then-current execution environment.
