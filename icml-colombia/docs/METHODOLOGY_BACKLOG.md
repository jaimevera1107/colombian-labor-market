# Methodological backlog (after 2.0.0)

Version 2.0.0 reproduces RC1 on purpose, including its known weaknesses.
These items were identified during the migration and are candidates for
2.x releases, each with its own regression baseline.

| Item | Evidence from the migration | Why it matters |
|---|---|---|
| Denominator contracts (working age and population linear before estimation) | Working-age seams in 2001 required the ADR-006 post-hoc linearization. **Universe gap explained** (`docs/evaluation/02_DENOMINATOR_VARIANTS.md`): GEIH national coverage excludes most of Amazonía/Orinoquía; variant B (demographic universe) removes the population distortion with anchors exact | Fixing denominators first avoids correcting them afterwards |
| Bogotá anchored to its urban GEIH series | Bogotá is one of the ten predicted territories | It is the largest territory and has direct survey data |
| As-of (vintage) validation | Features and labels use the 2026-08 vintage; CV is retrospective | Current CV errors are not prospective errors |
| Re-evaluation after the hierarchical closure | **Measured** (`docs/evaluation/01_TRANSFER_BASELINE.md`): after closure Ward is 0.70 pp worse than the hybrid; the hybrid equals the urban signal | The published model is not the best post-closure candidate |
| Latent urban months in small cities | Leticia/Inírida optimum moves 5e-4 persons for 2e-13 input changes | Months there depend on regularization choices, not data |
| Ward vs hybrid | Pre-closure hito 4 and post-closure transfer both favor the hybrid; Ward's tail advantage does not survive the closure | ADR-006 should be revisited |
| Classification of the 2,104 RC1 alerts | Inherited, not reviewed during the refactor | Separate real issues from expected warnings |
| Representativeness factors (candidate) | `docs/evaluation/03_REPRESENTATIVENESS_FACTORS.md`: GEIH national = 23 departments + Bogotá + 9 capitals (0.014 %); factor product built and tested | Open: 1993–2000 universe, pre-2021 inactive non-additivity on Bogotá |
| Monthly updates without rewriting history | **Done** (`docs/evaluation/04_UPDATE_POLICY.md`): revision states, graft and two-vintage test; full recomputation would rewrite 16,932 final cells, the graft 0 | Critique 8 |
| Who absorbs the sources' non-additivity | **Decided** (`docs/evaluation/05_RESIDUAL_ALLOCATION.md`): proportional sharing; anchors deviate up to 1.9 % instead of 9–12 % on Bogotá and the capitals | Anchors are no longer exact; residual share published |
| Headline accuracy | **Published** (`docs/evaluation/06_OFFICIAL_DEVIATION.md`): deviation from official figures, median 0.04–0.43 %, maximum 1.89 % | Reported with its decomposition, not as model error |
