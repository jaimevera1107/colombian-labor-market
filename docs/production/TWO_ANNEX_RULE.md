# ICML — Mandatory synchronization rule of the DANE sources

Originally written 2 November 2026 (2.2.24, fix H22b); command names updated.

## Indispensable condition

ICML **can only run a full monthly update** when it receives, for the same target month `M`, the **two official DANE publications**:

- **Gran Encuesta Integrada de Hogares (GEIH), Labor Market:** monthly annex whose reference period is **M**.
- **Informal Employment and Social Security:** moving-quarter annex whose **last month is M**. The quarter must span exactly `M−2`, `M−1` and `M`.

Hence:

`GEIH_month = last_month_of_the_informality_moving_quarter = ICML_update_month`.

**Example:** September 2026 requires **GEIH September 2026** together with **Informal Employment and Social Security July–September 2026**. The June–August 2026 edition **cannot be used** to update September, even if it is the latest one published at that moment.

## Update gate (mandatory)

If either annex is not published, has not been obtained, could not be verified, or its reference period does not match:

1. **BLOCK** every new monthly ICML estimate (national, urban, departmental, informality and sectoral), including the reconciliations and final products.
2. **DO NOT** carry forward the last available informality/Social Security rate, impute a missing annex as if observed, or combine annexes of different months.
3. **DO NOT** generate or promote a new vintage of results or change the last frozen cutoff.
4. Allow only an **isolated reception and audit** of the sources that do exist, marked as `staging` and without publishing results.

If both sources are available, additionally verify their content, origin and declared period inside the XLSX files, SHA-256, revisions and statistical gates. Their mere existence on disk and the agreement of names **are not enough** to authorize the update.

## Implementation

`detect_cutoff` (used by `icml status`, `rebuild` and `update`) sets the cutoff at the last month with both annexes; a month with one annex stays pending. `icml operations check-monthly-sources` checks presence and coherence of the **declared periods**; its reports never enable publication on their own. The content of the Social Security source has to be verified in a later official intake stage, before any full run. `icml operations intake-geih` allows inspecting the GEIH annex in advance, but reports that the full update stays blocked until its synchronized pair exists.

This requirement is a **non-negotiable methodological dependency** of the production pipeline, not an optional recommendation.
