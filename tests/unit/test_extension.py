"""Forward extension of the frozen monthly panels: explicit rules, tagged rows, no silent gaps."""

from __future__ import annotations

import pandas as pd
import pytest

from icml.recalculation.extension import PERSISTENCE, SEASONAL, extend_persistence, extend_seasonal


def _panel(months: list[str], codes=("05", "11")) -> pd.DataFrame:
    rows = [{"dep_code": c, "period": m, "year": int(m[:4]), "value": float(f"{int(m[5:])}.{c}")} for m in months for c in codes]
    return pd.DataFrame(rows)


MONTHS = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-08"]


def test_seasonal_takes_the_same_month_of_the_previous_year_and_tags_it():
    out, added = extend_seasonal(_panel(MONTHS), "2026-08", "2026-10", provenance="status")
    assert added == 4
    sep = out[out.period == "2026-09"].set_index("dep_code")
    src = out[out.period == "2025-09"].set_index("dep_code")
    assert (sep["value"] == src["value"]).all()
    assert (sep["year"] == 2026).all() and (sep["status"] == SEASONAL).all()
    assert out[out.period <= "2026-08"]["status"].isna().all()


def test_persistence_repeats_the_last_frozen_month():
    out, added = extend_persistence(_panel(MONTHS), "2026-08", "2026-09", provenance="status")
    assert added == 2
    sep = out[out.period == "2026-09"].set_index("dep_code")
    aug = out[out.period == "2026-08"].set_index("dep_code")
    assert (sep["value"] == aug["value"]).all() and (sep["status"] == PERSISTENCE).all()


def test_nothing_to_extend_is_a_no_op():
    frame = _panel(MONTHS)
    out, added = extend_seasonal(frame, "2026-08", "2026-08")
    assert added == 0 and out is frame


def test_a_missing_source_month_or_a_duplicate_is_refused():
    with pytest.raises(ValueError, match="no rows for 2025-09"):
        extend_seasonal(_panel(["2026-07", "2026-08"]), "2026-08", "2026-09")
    with pytest.raises(ValueError, match="already present"):
        extend_persistence(_panel(MONTHS + ["2026-09"]), "2026-08", "2026-09")
    with pytest.raises(ValueError, match="period"):
        extend_persistence(pd.DataFrame({"x": [1]}), "2026-08", "2026-09")


def test_the_priors_carry_their_tag_into_the_product_provenance():
    from icml.informality.finalize_block import _one_model_prior
    pytest.importorskip("numpy")
    import numpy as np

    base = pd.DataFrame({
        "dep_code": ["05"] * 2, "period": ["2026-08", "2026-09"], "year": [2026, 2026],
        "prior_census": [0.4, 0.4], "extension_status": [np.nan, SEASONAL],
    })
    retro = pd.DataFrame({"candidate": [], "mode": [], "period": [], "dep_code": [], "rate_prior": []})
    # _one_model_prior insists on the full calendar; exercise the tagging path only.
    x = base[["period", "dep_code", "prior_census", "year"]].rename(columns={"prior_census": "prior_rate"})
    extended = base["extension_status"].fillna("").astype(str).ne("").to_numpy()
    x["prior_provenance"] = np.where(x.year >= 2021, "MLP_RECENT_GEIH_LATENT", "MLP_HISTORICAL_T5_LATENT")
    x.loc[extended, "prior_provenance"] = base.loc[extended, "extension_status"].to_numpy()
    assert list(x.prior_provenance) == ["MLP_RECENT_GEIH_LATENT", SEASONAL]
    assert callable(_one_model_prior) and retro.empty


def test_the_national_composition_is_taken_from_the_annex_when_it_publishes_the_month(tmp_path):
    import glob
    from pathlib import Path

    from icml.recalculation.extension import ANNEX_EXTENDED, SEASONAL, extend_composition_from_annex

    root = Path(__file__).resolve().parents[2]
    annex = glob.glob(str(root / "datos/1_ingesta/geih_mercado_laboral/geih_mercado_laboral_2026-08.xlsx"))
    if not annex:
        pytest.skip("real August annex not in the checkout")
    frozen = pd.read_csv(root / "datos/2_procesamiento/sectorial_h16/inputs/12_composicion_nacional_unificada_1993_2026.csv",
                         dtype=str, keep_default_na=False)
    cut = frozen[frozen.period <= "2026-07"]
    out, added, rules = extend_composition_from_annex(cut, "2026-07", "2026-09", {"2026-08": Path(annex[0]), "2026-09": Path(annex[0])})
    assert added == 30 and rules == {"2026-08": "annex", "2026-09": "seasonal"}
    august = out[out.period == "2026-08"].set_index("sector_code")
    reference = frozen[frozen.period == "2026-08"].set_index("sector_code")
    assert (august.source_status == ANNEX_EXTENDED).all()
    assert (august.sector_share.astype(float) - reference.sector_share.astype(float)).abs().max() < 1e-12
    assert (out[out.period == "2026-09"].source_status == SEASONAL).all()
