# Deviation from official figures (headline accuracy)

Product `product.official_deviation`: one row per territory, year and
quantity, comparing the published figure with the official figure it
should match. 2,320 rows from 2001 on.

| Reference | Rows | What it compares |
|---|---|---|
| `ancla_anual_departamental` | 1,748 | The 23 anchored departments against the annual departmental annex |
| `geih_capital_ventanas` | 468 | The nine capitals against their published 12-month windows |
| `geih_dominio_urbano` | 104 | Bogotá against its GEIH urban domain |

## Results

| Quantity | Median | 95th percentile | Maximum |
|---|---|---|---|
| Population | 0.04 % | 0.14 % | 0.33 % |
| Employed | 0.26 % | 0.98 % | 1.22 % |
| Inactive | 0.30 % | 1.66 % | 1.66 % |
| Unemployed | 0.43 % | 1.86 % | 1.89 % |

By reference type the medians are alike (0.2–0.3 % in employed, 0.3–0.5 %
in unemployed), so no group of territories carries the burden.

## How to report it

This is the deviation of the **whole method** — sources, denominators,
disaggregation, latent months, closure — not of the predictive model.
Two components, both in the table:

1. **The sources do not add up.** DANE's domains miss the national total
   by 0.3–1.9 % in unemployed and 0.014 % in population
   (`docs/evaluation/05_RESIDUAL_ALLOCATION.md`). Every territory takes a
   share in proportion to its size, published as
   `absorbed_residual_persons`, so this part is separable.
2. **The project's own construction**: whatever the deviation shows
   beyond that share.

Reporting the total as "the model's error" would be wrong in substance,
since part of it is the sources'; the honest headline is "deviation from
official figures", with the decomposition available.

Maxima concentrate in 2020 and 2021 (the pandemic and the change of
sampling frame). Outside those years every deviation stays below 0.8 %.
