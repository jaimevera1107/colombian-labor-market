# Data

Generated artifacts are never committed. Only the minimal source files
listed in `configs/golden/rc1_catalog.toml` with `role = "source"` may be
versioned under `data/sources/`, and only after their redistribution terms
are confirmed.

Sources are classified by `source_class`:

| Class | Meaning |
|---|---|
| `dane_raw` | File published by DANE, unmodified. |
| `dane_compiled` | DANE figures compiled into a table by the project. |
| `legacy_derived` | Produced by the original ICML notebooks; cannot be regenerated from raw sources with the current code. |
| `frozen_decision` | Methodological decision frozen as data (donor catalogs, configuration). |

Large artifacts (RC1 golden set, final products) are distributed as
GitHub Release assets or Zenodo records, verified by SHA-256.
