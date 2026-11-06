# Excel file names and the cutoff of a run

## Principle

**Everything is computed as far as the annexes go, and no further.** The cutoff is never typed by hand: it is the **last month for which both monthly annexes exist** (labor market and informality). And a file name never decides anything: it only classifies. The period that counts is the one the workbook declares **inside**, and it has to agree with the name.

## Folders and canonical names

```
datos/1_ingesta/
  geih_mercado_laboral/   geih_mercado_laboral_YYYY-MM.xlsx    monthly annex
  geih_informalidad/      geih_informalidad_YYYY-MM.xlsx       moving quarter ending in YYYY-MM
  geih_departamentos/     geih_departamentos_YYYY.xlsx         annual; YYYY = last year covered
  excel_originales/       references that do not change monthly (population, GDP, ENH, ...)
  censo_original/
```

Lower case, underscores, no accents or spaces, and the period as `YYYY-MM`. Binary `.xls` files are historical and **never** decide the cutoff. The folder names are deliberately unchanged (they are recorded in versioned manifests).

## Accepted names

Any of these works; renaming what comes from DANE is not required:

| Name | Read as |
|---|---|
| `geih_mercado_laboral_2026-09.xlsx` | labor market, September 2026 |
| `Anexo GEIH Septiembre 2026.xlsx` | labor market, September 2026 |
| `anex-GEIH-sep2026.xlsx` | labor market, September 2026 |
| `Anexo GEIH Informalidad Septiembre 2026.xlsx` | informality, September 2026 |
| `geih_departamentos_2026.xlsx` | annual departmental, 2026 |

## What happens when the month changes

1. Drop the new annex in `datos/1_ingesta/` (in its folder, or even loose: it is found by name anywhere in the tree).
2. `icml update --dry-run` (or `icml recalc --root . --dry-run`) shows the detected cutoff.

| Situation | Result |
|---|---|
| Only the September labor annex arrives | The cutoff stays at August; September is **pending**. Nothing extra is computed. |
| The complete September pair arrives | The cutoff moves to September (the frozen parameters are carried forward, see below). |
| The name says September but the workbook declares July | **Blocked**: "the name says 2026-09 but the workbook declares 2026-07". |
| Two different files claim the same month | **Ambiguity error**; identical copies count as one. |
| The annex of the run's month is missing | **Blocked**: "The annexes of YYYY-MM are missing". |

A name cannot break the computation: either it is read correctly, or the system says exactly which file and why.

## Months after the frozen vintage

A month **later than the frozen vintage** (August 2026) is processed since 2.6.0: the H9 **MLP priors**, the **census bridge** and the national sectoral composition are frozen parameters with one row per month through August, and for later months they are carried forward with explicit, tagged rules (same month of the previous year for the priors and the composition, last month for the bridge). See `EXTENSION_BEYOND_FROZEN_CUTOFF.md`. An **earlier** month is rebuilt by cutting the frozen panels (`rebuild --through`).

## Closing the 2020-2021 residual

Between 2020 and 2021 there were methodological changes, and since 2021 every new window re-identifies the latent months, so the departmental sum of the census bridge and the national employment **do not coincide exactly**. That does not block:

1. If the bridge levels differ from the current labor product by more than 1e-3 persons, they are **refreshed** from the labor product and the GEIH universe is rebuilt hierarchically with the frozen factors (the identities PEA = employed + unemployed and PET = PEA + inactive hold).
2. The remaining residual is **recorded** (`employed_total_residual_people`) and absorbed by the national rate.
3. The run stops only on a gross mismatch (more than 1 % of national employment), which would indicate inputs from different vintages and not a methodological gap.

With the frozen cutoff (August) nothing changes: there are no stale rows.
