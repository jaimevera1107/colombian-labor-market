# Figures of a delivery (optional tool)

`icml plots` draws a delivery that has already been computed. **It is not part of the estimation**: it only reads the results, changes no number and nothing depends on it. It needs matplotlib, which the installer brings.

```
icml plots                                   # the published delivery
icml plots --folder datos/3_salida/<delivery>
```

It writes `<delivery>_plots/` next to the delivery, with an `index.html` to open in the browser. About 90 seconds and 87 images (25 MB).

| Option | Effect |
|---|---|
| `--only national,departments,comparatives` | Only those groups |
| `--universe census` or `geih` | One universe |
| `--departments 05,11` | Only those departments (DANE codes) |
| `--format png\|pdf\|svg` | Output format |
| `--force` | Replace an existing output folder |

The standalone module `python -m icml.plots.delivery --folder … --output … --dpi N` exposes the same options plus the destination and resolution.

## What it draws

**Dashboards** (national plus one per department, in each universe: 68 images): labor rates (TD, TO, TGP), levels (PET, PEA, employed, unemployed, inactive), informality (rate and informal vs formal) and employment composition by sector.

**Comparatives** (19 images):

| File | Shows |
|---|---|
| `national_census_vs_geih` | The four national rates, census vs GEIH |
| `departments_<RATE>_census_vs_geih` | The 33 departments as small multiples, same vertical scale, national reference |
| `heatmap_<RATE>_<universe>` | Yearly average per department, ordered by the last year |
| `ranking_<RATE>` | Last month: every department, census and GEIH, with the national value |
| `departmental_dispersion_<universe>` | Min–max range, 10th–90th percentiles and departmental median around the national value |

## How to read them

* **Grey shading, 1993-2000:** reconstructed stretch, without an official anchor. The dashed line marks the 2001-01 splice.
* **Pink band (GEIH universe):** months in which the GEIH represents no inhabitant of the territory; the series is interrupted instead of showing zeros. Before 2001 the GEIH universe reconstructs the whole territory and from 2014 only the represented part, so the levels of those territories change scale; not an error.
* **Census and GEIH coincide** in most departments: the thicker census line sits behind the GEIH one. Informality is the same in both universes by the assumption that the complement has the same rate.
* **"No information" in the sectoral panel:** some months show a visible share (up to 5.8 % in 2006-07). It is a feature of the sectoral product, which keeps the residual category of the sources; the figure only makes it visible.
* Sector names are short labels of the CIIU Rev. 4 A.C. sections used by the project (`docs/sectoral/HITO10_EMPAlME_CIIU3_CIIU4_2_2_17.md`).

The figures, `index.html` and `README.md` are in English since 2.6.0.
