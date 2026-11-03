# Representativeness factors (candidate design)

Decision: the ICML national total covers every department and is
therefore larger than DANE's; each territory carries, per month and
quantity, a factor such that the factor-weighted sum of the 33
territories equals the DANE national total. Implemented in
`icml.reconciliation.representativeness`; products
`product.departmental_factors` and `product.national_icml` (RC1 products
are unchanged).

## Evidence on what the GEIH national total represents

1. DANE's GEIH "Acerca de" (2024): national coverage excludes, in
   Amazonía/Orinoquía, municipal heads other than capitals, populated
   centers and dispersed rural areas, and Providencia and rural San Andrés.
   DANE bulletins: the capitals of these departments and San Andrés are in
   the national total from 2014. (DANE's 2022 redesign release says the
   national total "includes the population" of these departments without
   specifying which part; the figures below show it is the capitals.)
2. Official-only reconciliation, 2021–2025 (national monthly GEIH,
   departmental annex, 12-month city windows ending in December): national
   population = 23 departments + Bogotá + 9 capitals within 0.013–0.018 %
   (2022–2025; −0.026 % in 2021). Working age within 0.02 %.
3. Municipal projections by area (DANE, post-COVID update): GEIH capital
   populations equal the capital's municipal head (ratio 0.92–1.14), not the
   municipality (0.34–0.87) or the department.
4. 2007–2013: national − 23 − Bogotá leaves 20–60 thousand people versus
   ~380 thousand in the capitals; from 2014 it equals the capitals.
5. The departmental projections used are the post-COVID update (2025
   national total identical to the person: 53,110,609).

## Rest of territory for the nine partially represented departments

Department = capital urban signal + rest. Rest population = departmental
projection − capital population; rest labor ratios validated on the 22
anchored non-synthetic departments, where the rest is observable (annual
means; monthly differences of two reconstructions can be negative):

| Rest ratios from | Rates (pp) | TD | TO | TGP |
|---|---|---|---|---|
| capital participation + mean TD of others | 2.41 | 1.42 | 2.88 | 2.95 |
| **mean of other departments' rest (adopted)** | 2.48 | 1.39 | 2.96 | 3.08 |
| pooled rest of other departments | 2.51 | 1.41 | 3.01 | 3.10 |
| own capital | 2.72 | 2.45 | 2.78 | 2.95 |
| most similar department | 2.96 | 1.97 | 3.32 | 3.60 |

The first three are statistically equal (e.g. mean − pooled −0.03 pp, CI
−0.09 to 0.03). The mean is adopted: one rule for all ratios, and it does
not use the capitals' participation, which for Leticia, Inírida and Mitú
rests on ill-conditioned latent months. Errors grow as the capital's
population share falls (La Guajira 0.15, Nariño 0.18, Chocó 0.19: 4.5–7.4
pp); among the nine, Putumayo (0.11) and Vichada (0.13) are in that
regime. Donors' rest is Andean/Caribbean rural; no survey represents the
Amazonian rest.

Note on the transfer evaluation: hiding a represented department lets the
closure recover it from the national residual. The rest of the nine
territories is not in the national total, so that advantage does not
apply to them; this validation is the right analogue for them.

## Construction

Represented parts (23 anchored departments, Bogotá's urban domain, the
nine capitals from 2014) are reconciled with the joint smoother: national
monthly totals exact, 437 annual anchors exact (0 persons). Anchored
departments and Bogotá have factor 1 by construction; the nine
territories' factor is the capital's share (0 before 2014). ICML national
population exceeds DANE's by 2.06–2.98 % (2001–2026).

Example factors, December 2025 (population / employed / unemployed):
Putumayo 0.11/0.11/0.21, Vichada 0.13/0.14/0.19, Vaupés 0.25/0.27/0.19,
Arauca 0.28/0.29/0.43, Casanare 0.33/0.39/0.37, Guaviare 0.42/0.51/0.51,
Guainía 0.42/0.41/0.36, Amazonas 0.47/0.47/0.24, San Andrés 0.71/0.75/0.82.

## Open issues

* **Before 2001** the national population belongs to another universe
  (closing it would move Bogotá by −17 % in 1993); months before 2001 are
  not reconciled. The 1993–2006 universe (ENH–GEIH splice) must be
  verified.
* **Annual non-additivity falls on Bogotá.** 2022–2025: unemployed −2.4 to
  −4.7 % against its urban domain, consistent with the official-only
  reconciliation. 2014–2020: inactive +3 to +11 %, employed down to −6 %
  (2020). Hypothesis to verify: different working-age definitions between
  DANE series before the 2021 redesign.
* The 23 departments' 2026 months still come from the model panel; the
  departmental model is otherwise no longer used by this design.
