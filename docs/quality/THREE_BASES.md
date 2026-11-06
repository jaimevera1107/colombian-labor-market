# ICML 2.1.2.dev0 — Contract of the three labor bases

## Public products exclusive to the `quality` stage

- `quality/products/ciudades.csv`: 33 units per month. They are **32 cities or urban areas** plus the **synthetic urban signal of Cundinamarca**. The synthetic one is not presented as an official observation; never add cities to obtain the country.
- `quality/products/departamentos.csv`: 33 units per month (32 departments and Bogotá). It is the complete territorial universe; **the sum of its levels** defines the ICML national and loses no territory for lack of a reference.
- `quality/products/nacionales.csv`: **two rows per month**, `national_type=ICML_COMPLETO` and `national_type=DANE_REFERENCIA`, both with `dep_code="00"`. Key: `(national_type, period)`. Never add both rows.

Coverage of the three products: **1993-01 to the cutoff** (404 months at 2026-08). The six mandatory levels, without NA or infinities in any row: `population`, `working_age` (PET), `labor_force` (PEA), `employed`, `unemployed`, `inactive`.

## Non-equivalent nationals

`ICML_COMPLETO` = **unweighted** sum of the 33 complete territorial estimates; the ICML national is not forced to coincide with the DANE reference. `DANE_REFERENCIA` = national series delivered by `national_icml.csv` under the `dane_*` prefixes; from `2001-01` onwards, the GEIH reference used by ICML. **1993-01 to 2000-12 contains no official national GEIH observations:** the figure is a *reconstructed historical national reference*, flagged by `reference_status=HISTORICO_RECONSTRUIDO_NO_OFICIAL` and `is_official_observation=false`.

## Factor rule in the 33 departments

For **every period before 2001-01**, `factor_* = 1.0` for the six magnitudes, `*_represented = *` (full level), and `factor_reference_status=SIN_REFERENCIA_GEIH_FACTOR_IDENTIDAD`. This identity is a **conservation convention of the reconstruction**, not evidence of inclusion in the GEIH. In later years the coverage factors and the reconciliation approved in 2.1.0 are kept unchanged (made straight by segments for the nine partial territories in 2.4.0). Some territories have factor 0 until the 2014 GEIH expansion; **they are still present with their six magnitudes and still add to the ICML national**. Only the represented sum against DANE uses factors, from 2001.

In the national base, the ICML national factors are also 1 before 2001; from 2001 they are the corresponding reference/ICML ratio. The DANE_REFERENCIA national has identity factors for every date.

## Quality rules and prohibitions

1. 33 cities/signals + 33 departments, every month complete, no duplicates; two national series in the same months.
2. No null, infinite or negative labor component. `labor_force = employed + unemployed` and `working_age = labor_force + inactive` within numerical tolerance; `working_age <= population`.
3. Before 2001, every departmental and national factor equal to 1 and full representation. After 2001, the representation contract against the GEIH is preserved.
4. The ICML national is computed from the full levels (`groupby(period).sum()` of 33 departments), **never** from the represented sum.
5. Territory codes must be read as text (`dtype={'dep_code': 'string', 'city_code': 'string'}`) to keep the leading zeros. The national is found only in `nacionales.csv`, code `00`.
6. No change to the six estimated levels of 2.1.0; that change corrected the policy of the historical factors and organized the exports. The 2.1.0 package and its hash remained intact.
7. The pre-existing linearity and structural-change alerts are **not** considered resolved by the new export. The publication status stays `REQUIRES_METHODOLOGICAL_REVIEW` until their documented closure.

## Example

```python
import pandas as pd
from pathlib import Path
p = Path('quality/products')
cities = pd.read_csv(p/'ciudades.csv', dtype={'city_code':'string','dep_code':'string'})
departments = pd.read_csv(p/'departamentos.csv', dtype={'dep_code':'string'})
nationals = pd.read_csv(p/'nacionales.csv', dtype={'dep_code':'string'})
nat_icml = nationals.query("national_type == 'ICML_COMPLETO'")
nat_ref = nationals.query("national_type == 'DANE_REFERENCIA'")
```

The quality stage runs on the four canonical reconciliation inputs, writes these three products and runs the audits without changing the earlier sources. The auxiliary outputs/audits are kept in `/audit`; they are not a fourth base for analysis.
