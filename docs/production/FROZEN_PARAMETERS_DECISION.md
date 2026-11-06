# Decision: frozen parameters when a new month is added

**Status:** adopted by the project owner on 2 November 2026. **Scope:** ordinary monthly updates after the August 2026 vintage. Updated in 2.6.0 with the extension rule actually implemented.

## Rule

An ordinary update **reuses without retraining**:

* the CNPV 2018 census bridge (`parametros_congelados/puente_censal_cnpv2018`);
* the H9 departmental MLP *priors* (`parametros_congelados/priors_mlp_h9`);
* the frozen H16 sectoral features (`sectorial_h16/inputs`).

Only the observations of the new month are added and the results that legitimately depend on them are updated, according to the status policy `definitivo` / `sujeto_a_ancla` / `provisional` (`docs/evaluation/04_UPDATE_POLICY.md`). For a month later than the frozen cutoff the frozen panels are carried forward with explicit, tagged rules (`EXTENSION_BEYOND_FROZEN_CUTOFF.md`).

## Reasons

1. **Comparability**: retraining every month would change the history for reasons unrelated to the new data.
2. **Coherence with H36**, which already keeps these parameters frozen.
3. **Cost and traceability**: an ordinary update must not require training models or depend on the `torch` version.

## When the rule does not apply

A change of source or method (GEIH redesign, new population projections, a new census, a change of definition) is **not** an ordinary update: it requires full reprocessing and a new version, keeping the earlier vintages.

## Known risks and review conditions

* The frozen parameters may become inadequate if the new data drift away from what they assumed. The rule does not yet include a numeric drift criterion; **it must be defined** (for instance, the error of the new month's prediction against its observed reference).
* The `torch` version the original *priors* were trained with is not recorded; the rule avoids depending on it, but does not recover it.
* If the independent scientific validation of H9 (phase 4 of the roadmap) finds substantive problems in the *priors*, this decision is reviewed.
* The modeling stage of the labor chain depends on the xgboost minor version (see `REFERENCE_VINTAGE.md`); the frozen parameters above are not affected, the ten modelled territories are.
