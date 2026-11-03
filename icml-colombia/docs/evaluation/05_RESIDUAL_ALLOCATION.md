# Who absorbs the sources' non-additivity

DANE's domains do not add up exactly. With fully official figures
(monthly national GEIH, departmental annex, published 12-month windows),
the 23 anchored departments plus Bogotá plus the nine capitals miss the
national total by:

| Year | Employed | Unemployed | Inactive | Population |
|---|---|---|---|---|
| 2021 | +0.41 % | −1.90 % | −0.18 % | −0.026 % |
| 2022 | −0.10 % | −0.30 % | +0.27 % | +0.018 % |
| 2023 | −0.07 % | −0.66 % | +0.30 % | +0.013 % |
| 2024 | +0.06 % | −0.70 % | +0.09 % | +0.014 % |
| 2025 | −0.04 % | −0.28 % | +0.16 % | +0.014 % |

Population is essentially additive; unemployed is not. 2021 is the year
the sampling frame changed. Someone has to absorb the gap, and
`residual_allocation` decides who.

## The two rules, measured

| Measure | `non_anchored` | `proportional` (adopted) |
|---|---|---|
| Annual anchor deviation, employed | 0.00 % | 0.98 % |
| Annual anchor deviation, unemployed | 0.00 % | **1.86 %** |
| Annual anchor deviation, inactive | 0.00 % | 1.66 % |
| Annual anchor deviation, population | 0.00 % | 0.14 % |
| Bogotá vs its official GEIH | **9.08 %** | 1.86 % |
| A capital vs its official windows, max | 12.10 % | 2.80 % |
| Capitals, 90th percentile | 3.50 % | 0.80 % |

`non_anchored` keeps anchors exact by deforming other official figures
by 9–12 %. `proportional` — the rule the project used in its earlier
consolidation (`consolidar_candidato.py`: `value = trend + weight /
sum(weights) x national residual`) — keeps every official figure within
1.9 %.

Adopted: `proportional`. A 0.3–1.9 % inconsistency between sources
should produce deviations of that order spread around, not 9–12 %
concentrated on the territories without an anchor. `non_anchored`
remains available in configuration.

## What the deviation looks like

Annual anchor deviation by year (maximum across departments):

| Year | Employed | Unemployed | Inactive | Population |
|---|---|---|---|---|
| 2007 | 0.30 | 0.26 | 0.30 | 0.05 |
| 2019 | 0.38 | 0.63 | 0.73 | 0.06 |
| 2020 | 0.98 | 0.27 | 1.66 | 0.05 |
| 2021 | 0.41 | **1.86** | 0.18 | 0.03 |
| 2023 | 0.07 | 0.66 | 0.30 | 0.01 |
| 2025 | 0.04 | 0.28 | 0.16 | 0.01 |

Outside 2020–2021 every deviation is below 0.8 %. Monthly: median 0.3 %
in employed and 0.5 % in unemployed; 95th percentile 0.8 % and 2.5 %.

Each territory publishes `<quantity>_residual_share`: the persons it
absorbed, so a user can reconstruct the official figure it started from.
This is the two-layer approach of the earlier consolidation
(`residuo_pet_conciliacion_nacional`), applied to every quantity.

## Cost accepted

Annual departmental anchors are no longer reproduced exactly — a
guarantee the project had kept since RC1. The bound is declared and
tested (`tests/regression/test_representativeness.py`), and the residual
share makes the difference traceable cell by cell.
