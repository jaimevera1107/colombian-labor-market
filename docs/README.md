# ICML 2.0 documentation

Everything is in English. The milestone write-ups of the informality, sectoral, census and research work (2.2.x, Spanish) were condensed into one README per folder; the originals remain in the git history.

## Start here

| Document | Purpose |
|---|---|
| [../README.md](../README.md) | What ICML is, quick start, commands, monthly update, scope and limits |
| [../TESTING.md](../TESTING.md) | Guided exercise: rebuild through July, update with August, draw and publish |
| [production/ARCHITECTURE.md](production/ARCHITECTURE.md) | Package layout, command groups, data flow of a recalculation |
| [production/MONTHLY_UPDATE.md](production/MONTHLY_UPDATE.md) | The three routines end to end, expected figures and warnings |
| [production/PLOTS.md](production/PLOTS.md) | Optional figures of a delivery |
| [production/PUBLISHING.md](production/PUBLISHING.md) | Checksums, monthly backup, CI |
| [production/REFERENCE_VINTAGE.md](production/REFERENCE_VINTAGE.md) | The frozen products: what they are for and how to refreeze them |
| [production/EXTENSION_BEYOND_FROZEN_CUTOFF.md](production/EXTENSION_BEYOND_FROZEN_CUTOFF.md) | How months after the frozen vintage are processed |
| [PROCESSING_FRAMEWORK.md](PROCESSING_FRAMEWORK.md) | Processing methodology: processes, rules, gates, delivery |
| [TRACEABILITY_REPORT.md](TRACEABILITY_REPORT.md) | Traceability matrix, gaps, risks and recommendations, with their 2.6.0 status |

## Operation and current decisions

| Document | Topic |
|---|---|
| [production/FILE_NAMES_AND_CUTOFF.md](production/FILE_NAMES_AND_CUTOFF.md) | How to name the Excel files, how the cutoff is detected, the 2021 residual |
| [production/LABOR_RECONSTRUCTION.md](production/LABOR_RECONSTRUCTION.md) | Linear PET and 1993-2000 components (method adopted in 2.4.0) |
| [production/SPLICES_2001.md](production/SPLICES_2001.md) | Splices of the 2001-01 seam (2.3.0; the labor one was replaced in 2.4.0) |
| [production/FROZEN_PARAMETERS_DECISION.md](production/FROZEN_PARAMETERS_DECISION.md) | Which parameters are not retrained and why |
| [production/CUTOFF_INVENTORY_AND_MONTHLY_PLAN.md](production/CUTOFF_INVENTORY_AND_MONTHLY_PLAN.md) | Single source of the cutoff and the monthly update plan |
| [production/TWO_ANNEX_RULE.md](production/TWO_ANNEX_RULE.md) | A new month requires both annexes of the same month |
| [METHODOLOGY_BACKLOG.md](METHODOLOGY_BACKLOG.md) | Methodological backlog |

## Methodology by component

| Folder | Content |
|---|---|
| [quality/](quality/) | Quality gate and the three bases (cities, departments, nationals) |
| [evaluation/](evaluation/) | Transfer evaluation, representativeness factors, update policy |
| [census/](census/) | CNPV 2018 census bridge between the two universes |
| [informality/](informality/) | How the informality bases are built: sources, chain, evidence, limits |
| [sectoral/](sectoral/) | How the experimental sectoral product is built: support, chain, evidence |
| [research/](research/) | Donor choice for the nine cities without GEIH history |
| [migration/](migration/) | RC1 lineage and the migration plan of the equivalence refactor |
