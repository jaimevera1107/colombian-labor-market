# Months after the frozen vintage: how the frozen parameters are carried forward

Until 2.5.0 `icml update` refused any month later than the frozen vintage (`2026-08`) because four frozen parameter panels end there and the closure requires a row for every month of the calendar. Since 2.6.0 a later cutoff is processed like an earlier one: `build_vintage_root` prepares a working root for the cutoff, and instead of cutting the panels it **extends** them with explicit rules. Nothing is re-estimated; every forwarded row is tagged and the tag reaches the products.

| Panel | Rule | Tag | Why |
|---|---|---|---|
| `parametros_congelados/priors_mlp_h9/12_single_mlp_33_department_priors.csv` | same calendar month of the previous year | `EXTENDED_SEASONAL_PERSISTENCE` in `prior_provenance` of the departmental informality product | the priors only set the departmental pattern; the level is calibrated to the national target that comes from the new annex |
| `parametros_congelados/puente_censal_cnpv2018/02_puente_dos_universos_33_territorios.csv` | copy of the last frozen month | `EXTENDED_LAST_MONTH_PERSISTENCE` in `factor_reference_status` | its levels are refreshed from the labor product at closure time and the nine partial territories take the labor product's GEIH factors (straight segments that extrapolate the last slope); only the factors of the 24 fully covered territories are carried |
| `sectorial_h16/inputs/12_composicion_nacional_unificada_1993_2026.csv` | **from the labor annex** of the cutoff when it publishes the month (sheet `Ocupados TN_T13_rama`, 13 groups → 15 codes with the fixed 2015-03 B/D_E ratio, `NO_INFO` as remainder), else same month of the previous year | `DANE_13_PUBLISHED_PLUS_NO_INFO_REMAINDER_EXTENDED` or `EXTENDED_SEASONAL_PERSISTENCE` in `source_status` | the reading reproduces the frozen August shares to 1e-16; a month the annex does not publish is carried forward and says so |
| H5/H6 sequences (`informalidad_secuencia_h5_h6/`) | none needed | — | regenerated from the annexes in every recompute |

The delivery manifest records the extension in its methodology notes (`frozen_parameters_extension`), and `icml status`/`rebuild`/`update` print a note when the target month is later than the frozen vintage.

## What is verified and what is not

* Unit tests cover the rules (`tests/unit/test_extension.py`) and the CLI/runner paths.
* With `ICML_CUTOFF=2026-09` the extended panels pass the closure's calendar and key checks and the priors carry the tag into `prior_provenance` (smoke test, not in the suite because it needs the full data tree).
* **Not verified:** an end-to-end run with real September annexes. The repository has none, and a synthetic annex would have to reproduce the DANE sheet layouts the readers parse. The first real month after August is therefore the first full test of this path; run it with `--dry-run` first, then `update`, and read `frozen_parameters_extension` in the manifest and `prior_provenance`/`source_status` in the products before publishing.

## What to decide next

1. ~~Wire the H10 monthly sectoral extraction~~ Done in 2.6.0 (`extract_monthly_composition`, read with openpyxl).
2. **Refreeze on a new reference month.** When a later month becomes the reference vintage, run `refreeze_reference.py` on a recompute at that cutoff and change `FROZEN_CUTOFF` in `icml.domain.cutoff`; from then on the extension starts at the new cutoff.
3. Whether the departmental informality priors should be re-estimated (MLP refit, `torch`) at some cadence instead of carried forward: a methodological decision, out of scope here.
