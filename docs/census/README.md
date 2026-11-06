# Census bridge: full territory vs GEIH-represented universe (milestone 2.2.11)

Condensed from `HITO_CNPV2018_PUENTE_UNIVERSOS_2_2_11.md` (in git history).

**Why.** The labor bases describe the whole territory (CNPV 2018 population); the GEIH represents only part of it, and in nine territories (Arauca, Casanare, Putumayo, San Andrés, Amazonas, Guainía, Guaviare, Vaupés, Vichada) only their capital from 2014 and nobody before. Informality is observed in the GEIH universe, so every department needs a bridge between the two.

**What it does** (`icml.census.bridge`, stage `census_bridge` after `quality`): anchors the nine capitals to the CNPV 2018 adjusted-coverage population (`01_ancla_cnpv_2018_nueve.csv`), builds the monthly panel of both universes for the 33 territories (`02_puente_dos_universos_33_territorios.csv`), the national comparison (`03_*`), a direction benchmark (`04_*`, which universe should be closed first: the other margin deviates ~0.2 pp either way) and quality gates (`05_*`). The bridge is a **frozen parameter**: its levels are refreshed from the current labor product at closure time, its factors are not re-estimated; since 2.4.0 the nine partial territories take the labor product's straight-segment GEIH factors, so labor and informality describe one and the same universe.

**Status:** reproducible stage and audit; the resulting departmental candidates are non-canonical.
