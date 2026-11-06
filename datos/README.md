# Data

Three stages, in the order the system uses them. The folder names are part of the versioned manifests and catalogs, so they are not renamed.

| Folder | Holds | Edited by hand? |
|---|---|---|
| `1_ingesta/` | DANE annexes and Excel references, as downloaded (see `1_ingesta/LEEME.md`) | Yes: new annexes are added |
| `2_procesamiento/` | Everything the system needs besides the ingestion | No |
| `3_salida/` | Dated deliveries per universe (full and simple); generated locally, ignored by Git | No |

`2_procesamiento/` contains:

| Subfolder | Content |
|---|---|
| `catalogos/` | Source catalog and register of original Excel files with their hashes |
| `fuentes_preparadas/` | Tables derived from the Excel files (urban, informality, DANE anchors, historical signals) |
| `parametros_congelados/` | Parameters that are not retrained: CNPV 2018 census bridge, informality model priors, H5/H6 reference sequence, 2020 scenarios |
| `productos_congelados/` | The frozen August 2026 vintage (equivalence reference and test fixture) |
| `sectorial_h11/`, `sectorial_h16/` | Inputs, model and references of the sectoral component |
| `auditoria_historica_h30/` | Lineage evidence of the urban donors and historical annexes |
| `vigente/` | The latest promoted delivery: what the next anchored recalculation freezes (generated, ignored by Git) |
| `_corridas/` | Scratch space of each recalculation (empty; its content is not versioned) |
