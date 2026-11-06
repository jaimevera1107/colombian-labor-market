# Research notes behind the urban decisions (RC2)

Condensed from `rc2_urban_decisions/` (the studies are kept in git history; the data files `catalogo_pareto_nueve_propuesto.csv`, `evaluacion_207_alternativas.csv` and `MANIFEST_RC2.json` stay here).

Nine cities have no GEIH urban history before 2021 and are reconstructed from **donor** cities. The donor choice was made with a multi-criteria (Pareto) study over 207 alternatives, validated retrospectively on the 23 cities with known history (leave-one-out: the rule picks a donor whose error is within tolerance of the best possible one), with aggregate donors as a documented fallback. Cundinamarca has no urban domain at all and uses a synthetic signal (Bogotá-based, rectified and audited). The frozen choice lives in `datos/2_procesamiento/fuentes_preparadas/urbano/` and is never re-estimated in production.
