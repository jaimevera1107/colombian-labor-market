# Rebuild, update and plot: the three routines and what to expect

The commands (`icml status`, `rebuild`, `update`, `plots`, `verify`) are described in the root README. This note records what was **checked end to end** on a clean copy of the project, with an environment created by the installer (without `torch`), so whoever replicates the use knows which figures and warnings are normal.

## The three tests, as they were run

| # | Command | Result |
|---|---|---|
| 1 | `icml rebuild --through 2026-07 --yes` | July base: 1993-01 to 2026-07 (806 national rows, 13,299 departmental). Audit 52 of 52. Simple files created. July becomes the published base |
| 2 | `icml update` | `UPDATE ONLY through 2026-08`: detects the two August annexes as new, computes and publishes. Audit 52 of 52 |
| 3 | `icml plots` | 87 figures and `INDICE.html` |

Approximate times: test 1, 10 to 15 minutes (it builds a working copy cut at July and recomputes everything); test 2, 8 to 10; test 3, about 90 seconds.

## What the update was checked for

Comparing the August delivery (anchored) with the July one:

* **Frozen years (through 2025): 0 different cells** in labor, informality and sectoral, in both universes.
* **Open year (2026):** changes, because a month enters and it is re-estimated. January to July 2026, departments: employment changes with median 0.09 %, 99th percentile 1.25 % and maximum 1.56 %; PET, maximum 0.49 %.
* **What is added:** 33 rows per departmental product and 1 per national one.
* **Equivalent to recomputing everything:** the open year of the update is **identical (0.0000 %)** to that of a total August recalculation.
* **A small step at the 2025 → 2026 seam.** Because the frozen part stays as the previous base left it, the smoothed PET has in January 2026 a curvature of up to 0.23 % of the level (0.06 % in a total recalculation). Expected, not an error.

## Annexes of other months

The input fingerprint of a delivery includes only the annexes **through its cutoff**. That is why one can rebuild through July with the August annex already copied: August then shows up as a new input of `update` (otherwise the update would see "no changes"). Annexes after August 2026 still cannot be processed (see the README).

## Warnings that are normal

* `MultipleOptimaWarning: The rho criterion has competing local optima…` in the departmental stage: emitted by the temporal disaggregation library. The deliveries pass the 52 checks.
* `FutureWarning … incompatible dtype … bool` when grafting the frozen years (`graft.py`): from pandas; the frozen figures came out identical (0 different cells).

## Common messages

| Situation | Answer |
|---|---|
| `rebuild` with a base already published | Asks for confirmation (or `--yes`) and suggests `update` to add a month |
| `update` without a published base | Asks for `rebuild` |
| `update --through` a month before the base | "does not go back"; offers `rebuild --through` |
| `--through 2026-13` | Asks for the YYYY-MM format |
| A month without both annexes | "Both annexes of YYYY-MM are not available" and names the last complete one |
| Wrong folder | "Project folder not found" |
| `plots` when the figures exist | Offers `--force` |

## Before pushing to GitHub after the tests

The tests **change the project**: they add deliveries in `datos/3_salida/` and change the published base (`datos/2_procesamiento/vigente/`). Both are ignored by Git; `git clean -fd datos/3_salida datos/2_procesamiento/vigente` returns to the state of the checkout. To publish a change, regenerate `SHA256SUMS` with `icml checksums --write`.
