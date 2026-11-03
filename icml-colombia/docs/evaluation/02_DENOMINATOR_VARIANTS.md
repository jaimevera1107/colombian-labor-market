# Closure variants for the denominator contract

Same protocol as `01_TRANSFER_BASELINE.md` (22 hidden departments, 418
department-years, candidates Ward, hybrid and urban signal). Variants are
implemented in `icml.evaluation.closures`; the published closure is `rc1`.

| Variant | Departments add to | Anchors | Universe gap absorbed by |
|---|---|---|---|
| `rc1` | National GEIH, six quantities | exact | unanchored territories |
| A `uniform_raking` | National GEIH | move by a common factor | all 33, proportionally |
| B `demographic_universe` | National GEIH scaled to the sum of demographic projections | exact | nobody (national rates applied to the wider universe) |
| C `components_only` | National GEIH for employed, unemployed, inactive; population not reconciled | exact | unanchored territories, components only |

## Why the universes differ (verified)

DANE's GEIH national total excludes, in the Amazonía and Orinoquía
departments, the municipal heads that are not capitals and the populated
centers and dispersed rural areas, and it includes the eight capitals and
San Andrés only since 2014. In the 2.0.0 data, the gap between the sum of
departmental demographic projections and the national GEIH population is
2.81–2.88 % in 2007–2013, matching the population share of the nine
Amazonía/Orinoquía/San Andrés territories (2.77–2.89 %), and drops to
2.12 % in 2014, when their capitals entered the national total. The gap is
survey coverage, not estimation error.

All nine partially covered territories are unanchored, so `rc1` forces
the coverage gap onto them and onto Bogotá (fully covered), whose labor
population ends 18.1 % away from its demographic projection.

## Results (mean absolute error; rates in pp, levels in %)

| Closure | Candidate | Rates | TD | TO | TGP | Unemployed | Working age | Population |
|---|---|---|---|---|---|---|---|---|
| model (none) | Ward | 2.34 | 1.52 | 2.63 | 2.88 | 17.1 | 5.17 | 0.59 |
| rc1 | hybrid | 2.21 | 1.43 | 2.52 | 2.67 | 16.1 | 5.27 | 2.67 |
| rc1 | Ward | 2.90 | 1.42 | 3.43 | 3.86 | 17.8 | 5.27 | 2.67 |
| A | Ward | 2.28 | 1.47 | 2.53 | 2.82 | 16.6 | 4.94 | 2.26 |
| A | hybrid | 2.30 | 1.47 | 2.60 | 2.83 | 16.3 | 4.94 | 2.26 |
| B | hybrid | **2.15** | 1.45 | 2.45 | 2.55 | 17.0 | 4.97 | 0.58 |
| B | urban signal | 2.18 | 1.54 | 2.54 | 2.47 | 19.5 | 4.87 | 0.58 |
| B | Ward | 2.66 | 1.44 | 3.07 | 3.47 | 19.2 | 4.97 | 0.58 |
| C | hybrid | 2.21 | 1.43 | 2.52 | 2.67 | 16.1 | 5.27 | 0.59 |
| C | Ward | 2.90 | 1.42 | 3.43 | 3.86 | 17.8 | 5.27 | 0.59 |

Paired differences by department (mean of the three rates, 95 %
bootstrap interval, departments where the first is worse):

| Comparison | Mean (pp) | Interval | Worse in |
|---|---|---|---|
| B − rc1, hybrid | −0.06 | −0.16 to 0.05 | 7/22 |
| B − rc1, Ward | −0.24 | −0.31 to −0.17 | 3/22 |
| A − rc1, Ward | −0.63 | −0.98 to −0.24 | 5/22 |
| B hybrid − A Ward | −0.13 | −0.30 to 0.03 | 7/22 |
| B hybrid − B urban | −0.04 | −0.18 to 0.09 | 13/22 |
| B Ward − B hybrid | +0.51 | 0.17 to 0.84 | 15/22 |
| Population error, B − rc1, hybrid | −2.08 % | −2.90 to −1.42 | 0/22 |
| Unemployed level error, B − rc1, hybrid | +0.90 % | 0.17 to 1.65 | 15/22 |

Structural costs on the production panel (nothing hidden):

| Variant | Max anchor deviation | 33-territory sum vs national GEIH | Bogotá labor vs demographic population |
|---|---|---|---|
| rc1 | 0 | exact | 18.1 % |
| A | employed 3.1 %, population 7.1 % | exact | 4.8 % |
| B | 0 | +1.1 to +5.0 % (coverage gap) | 1.7 % |
| C | 0 | exact for components; population +1.8 to +4.5 % | 0 % |

## Reading

* **A is rejected**: it is the only variant that rescues Ward, but it
  moves official anchors by up to 3 % (components) and 7 % (population).
* **C fixes population at no cost to rates**, but keeps the
  inconsistency: working age is forced into the national (narrower)
  universe while population follows the demographic (wider) one.
* **B fixes population (better in 22 of 22 departments), keeps anchors
  exact, is internally consistent and gives the best rates with the
  hybrid**, although its advantage over `rc1` on rates is not significant
  for the hybrid and it slightly worsens the unemployed level (+0.9 %).
  Its cost is explicit: the departmental product adds up to a universe
  1–5 % larger than the published national total, which must be
  documented as coverage.
* In every variant, Ward is worse than the hybrid after the closure, and
  the hybrid is statistically equal to the urban signal.
* B applies national rates to the uncovered population (rural
  Amazonía/Orinoquía). Regional rates for that part are a candidate
  refinement.
