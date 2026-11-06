# Monthly updates without rewriting history

Implemented in `icml.pipeline.vintage`; verified by
`tests/regression/test_incremental_update.py`.

## Revision states

Each cell carries a state that depends only on dates: the vintage's last
month, the last year with a published departmental annex, and the
12-month window.

| State | Meaning | Changes in an ordinary update |
|---|---|---|
| `definitivo` | Its year has a published anchor and no future window touches it | No |
| `sujeto_a_ancla` | Window closed, anchor not yet published | When the anchor arrives |
| `provisional` | Inside the open rolling window | Every month |

A vintage published with last month *M* can still revise months from
*M − 10* on, because the next window (ending *M + 1*) covers them. Months
up to *M − 11* appear only in already published windows.

Project decisions (configurable): the open window's months are revised
each month and marked provisional, rather than frozen on first
publication; freezing a month that the next window contradicts would
leave an error that is never corrected. Published vintages are kept.

## Why a graft is needed

Two consecutive vintages were produced from the same annex, one cut at
2026-05 (54 windows) and the current one (57 windows). Recomputing the
whole chain changes **16,932 final cells**, by up to 2 % in unemployed:
every new window re-identifies the latent months of 2021 onward.

`apply_update` keeps final rows whole from the published vintage and
takes the rest whole from the recomputation. Whole rows, not cells, so
each row comes from one computation and keeps its identities, its
factors and its national closure.

After the graft: 0 final cells changed, 1,353 provisional cells changed
(up to 19 % in unemployed in small territories), 99 new rows (3 months x
33 territories), identities exact to 1e-9 persons and, from 2001, the
factor-weighted sum matches each vintage's national exactly.

## Operation

| Event | Frequency | Effect |
|---|---|---|
| New national month and new windows | Monthly | New month; months in the open window revised |
| Departmental annex | Annual | Its year is reconciled against the anchors and becomes final |
| Source or method change (GEIH redesign, new projections) | Occasional | Full reprocessing, new version; earlier vintages stay available |

An ordinary update is refused when any final cell changes
(`assert_accepted`), naming the offending cells.

## Limits

* The states are derived from dates, not from the data: a DANE revision
  of past official figures is a source change, not an ordinary update.
* The test uses the same annex truncated to simulate the earlier
  vintage. Replaying a real past annex would also exercise changes in
  published figures themselves.
