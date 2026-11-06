# Cutoff 2026-08: inventory, state of the refactor and plan for a new month

Working document written after H36, kept as the record of how the frozen cutoff was taken out of the code. Facts measured then are separated from decisions that were pending; a closing section says what 2.5.0/2.6.0 resolved.

## 1. What was changed (pure refactor)

The August 2026 cutoff was embedded in the code in two ways:

* **Dates**: the literal `2026-08` in 24 modules (51 lines).
* **Panel shapes derived from the calendar**: `404` months, `13332` (33 x 404), `808` (2 x 404) and `199980` (13332 x 15), in 16 modules (72 occurrences). A first version of this inventory counted only the dates and underestimated the problem; the shapes do not show up when searching for `2026-08`.

Everything now lives in `icml.domain.cutoff`: `FIRST_MONTH`, `FROZEN_CUTOFF`, `INFORMALITY_NEW_FIRST_MONTH`, `SECTORAL_FIRST_MONTH`, calendar helpers (`month_periods`, `month_labels`, `month_starts`, `expected_month_count`, `next_month`, `trailing_window_label`) and the shapes `N_MONTHS`, `ROWS_33`, `ROWS_NATIONAL`. The defaults are those of the frozen vintage, so the behaviour does not change. Of the 72 shapes, 65 were in code and were migrated; 7 were inside text messages and were left.

Evidence that nothing changed (same machine, same pinned environment):

* `run-integral --mode recompute` before and after: same state, cross audit `PASS`, and the 8 products byte-identical (SHA-256).
* `tests/unit/test_cutoff.py`: the helpers and constants reproduce the original expressions and literals.
* `tests/unit/test_no_cutoff_literals.py`: a ratchet that stops dates or panel shapes from reappearing outside this module; shapes are detected by *tokens*, not by text, and it was checked that it fails on a new `404` in code and ignores one inside a message.

Limit: byte identity was measured between runs on the same machine. It does not prove reproducibility across operating systems or CPUs. (2.6.0 measured it across dependency versions: see `REFERENCE_VINTAGE.md`.)

## 2. Dates that remain (justified)

| Category | Where | Occurrences |
|---|---|---|
| Definition of the constant and its documentation | `domain/cutoff.py` | 3 |
| Docstrings | `operations/integral.py`, `sectoral/monthly.py`, `operations/excel_historical_sources.py` | 3 |
| Identity of frozen source files or roles | `operations/prepared_sources.py`, `operations/excel_historical_sources.py`, `operations/excel_sources.py` | 6 |
| Explicit months compared when checking revisions | `operations/geih_intake.py` | 1 |

## 3. What was NOT resolved then

Centralizing the value is not the same as parameterizing it. The helpers and shapes are constants of the frozen vintage, evaluated at import time. They should become `cutoff` parameters received from the vintage policy. Calendars fixed that way:

* `informality/urban_backcast.py`: `MONTHS`, `NEW_MONTHS`.
* `informality/finalize_block.py`: `MONTHS`.
* `informality/postclosure_evaluation.py`: `PERIODS`.
* `informality/quality_gate.py`: `CALENDAR`, `PERIOD_START`, `PERIOD_END`.
* `operations/integral.py`: `PERIOD_END`; `operations/geih_intake.py`: `LAST_FROZEN`.

There are also rules that are methodological, not calendar, and were therefore not touched:

* `operations/excel_historical_sources.extract_window_proxies`: "frozen at 2026-08" contract (for 2026 it uses the windows available through August).
* Years of the sectoral annual anchors: `range(2015, 2026)` in `sectoral/predictive_benchmark.py` and `operations/excel_sources.py`.
* Policy on frozen parameters (CNPV bridge, H9 MLP priors, sectoral features) when a new month is added.

## 4. State of the stages against a new month (as measured then)

| Component | State measured |
|---|---|
| Labor (national → quality) | Parameterized by configuration (`last_month`, `n_windows`); vintages and graft implemented and tested (`pipeline/vintage.py`, `test_incremental_update.py`) |
| Informality H5/H6/H9 | Calendar fixed by module constants (section 3) |
| Sectoral H16 | Window contracts and anchor years fixed (section 3) |
| Source reception (`geih_intake`, `monthly_cycle`) | Implemented; declares `SOURCE_INTAKE_ONLY` and blocks the computation |

## 5. Data block for September 2026

The two-annex rule (`TWO_ANNEX_RULE.md`) requires, for target month `M`, the GEIH of `M` **and** the Informal Employment and Social Security annex whose moving quarter ends in `M`. For September, the second (July–September) was pending, with publication expected around mid-November 2026 (indicative, not verified). Until then a real new month cannot be processed without violating the rule.

## 6. Plan proposed then, and what happened

1. Convert the constants of section 3 into `cutoff` parameters from the vintage policy, with the frozen value as default. — **Partly:** the CLI relaunches the process with `ICML_CUTOFF` for another month and the vintage root prepares the data for it; the module constants still read the environment at import time.
2. Rehearsal with July 2026 (GEIH July and Social Security May–July are in the ingestion). — **Done:** the July vintage is rebuilt by `rebuild --through 2026-07` and the update to August leaves the frozen years untouched (`MONTHLY_UPDATE.md`).
3. Policy on frozen parameters. — **Decided and implemented:** `FROZEN_PARAMETERS_DECISION.md`, `EXTENSION_BEYOND_FROZEN_CUTOFF.md`.
4. With the September pair published, run the first real update and record its evidence. — **Pending:** it is the end-to-end test of the extension.
