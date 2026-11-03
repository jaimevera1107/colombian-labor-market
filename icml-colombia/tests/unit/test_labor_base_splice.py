"""Labor base splice: only the PET share is spliced; levels follow, rates stay."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from icml.pipeline.labor_base_splice import (
    LEVELS,
    REPRESENTED,
    LaborBaseSplice,
    splice_frames,
    splice_labor_products,
)

CUT = "2001-01"
PERIODS = [f"{y}-{m:02d}" for y in range(1993, 2004) for m in range(1, 13)]
ENABLED = LaborBaseSplice(enabled=True)


def _levels(population, share, tgp, to):
    wa = population * share
    lf, e = wa * tgp, wa * to
    return {"population": population, "working_age": wa, "labor_force": lf, "employed": e,
            "unemployed": lf - e, "inactive": wa - lf}


def _series(base_share, jump, seed, rows=PERIODS):
    rng = np.random.default_rng(seed)
    cut = rows.index(CUT)
    return [base_share + 0.0006 * k + (jump if k >= cut else 0.0) + rng.normal(0, 0.0015) for k in range(len(rows))]


def _products(tmp_path, jumps=(0.016, 0.012, 0.020), city_jump=0.010, reference_jump=0.014):
    folder = tmp_path / "labor" / "quality" / "products"
    folder.mkdir(parents=True)
    dep_rows, summed = [], {}
    for i, (code, jump) in enumerate(zip(("5", "8", "11"), jumps, strict=True)):
        population = 4_000_000.0 * (i + 1)
        for k, (period, share) in enumerate(zip(PERIODS, _series(0.62, jump, i), strict=True)):
            levels = _levels(population * (1 + 0.0015 * k), share, 0.66 + 0.04 * i + 0.0002 * (k % 12), 0.54 + 0.03 * i)
            factor = 1.0 if period < CUT else 0.9
            row = {"period": period, "dep_code": code, **levels}
            row |= {f"{c}_represented": levels[c] * factor for c in LEVELS}
            row |= {"population_represented": levels["population"] * factor, "factor_employed": factor,
                    "unemployment_rate": levels["unemployed"] / levels["labor_force"],
                    "employment_rate": levels["employed"] / levels["working_age"],
                    "participation_rate": levels["labor_force"] / levels["working_age"], "source": "S"}
            dep_rows.append(row)
            acc = summed.setdefault(period, dict.fromkeys((*LEVELS, "population"), 0.0))
            for c in acc:
                acc[c] += levels[c]
    city_rows = []
    for i, code in enumerate(("11", "5", "25")):
        for k, (period, share) in enumerate(zip(PERIODS, _series(0.63, city_jump, 10 + i), strict=True)):
            levels = _levels(1_000_000.0 * (i + 1) * (1 + 0.0015 * k), share, 0.72, 0.62)
            city_rows.append({"city_code": code, "period": period, **levels, "source_status": "R"})
    nat_rows = []
    for period, share in zip(PERIODS, _series(0.64, reference_jump, 20), strict=True):
        ref = _levels(summed[period]["population"] * 0.98, share, 0.71, 0.61)
        for kind, lv in (("DANE_REFERENCIA", ref), ("ICML_COMPLETO", summed[period])):
            nat_rows.append({"period": period, "national_type": kind, **lv, "factor_employed": 1.0,
                             "unemployment_rate": lv["unemployed"] / lv["labor_force"],
                             "employment_rate": lv["employed"] / lv["working_age"],
                             "participation_rate": lv["labor_force"] / lv["working_age"]})
    for name, rows in (("departamentos", dep_rows), ("ciudades", city_rows), ("nacionales", nat_rows)):
        pd.DataFrame(rows).to_csv(folder / f"{name}.csv", index=False, lineterminator="\n")
    return folder


def _text(folder):
    return {n: pd.read_csv(folder / f"{n}.csv", dtype=str, keep_default_na=False) for n in ("departamentos", "ciudades", "nacionales")}


def _num(frame, columns):
    return frame[list(columns)].apply(pd.to_numeric)


def test_from_the_break_on_the_files_are_byte_identical_and_before_only_the_levels_change(tmp_path):
    folder = _products(tmp_path)
    before = _text(folder)
    splice_labor_products(folder, ENABLED)
    after = _text(folder)
    changeable = set(LEVELS) | set(REPRESENTED)
    for name in before:
        kept = before[name].period >= CUT
        pd.testing.assert_frame_equal(before[name][kept], after[name][kept])  # untouched, as text
        rates = {"unemployment_rate", "employment_rate", "participation_rate"}
        # No other column moves, even before the break. The only exception: the
        # national ICML rates, implied by the corrected departments.
        untouched = [c for c in before[name].columns if c not in changeable and not (name == "nacionales" and c in rates)]
        pd.testing.assert_frame_equal(before[name][untouched], after[name][untouched])
        if name == "nacionales":
            ref = before[name].national_type == "DANE_REFERENCIA"
            pd.testing.assert_frame_equal(before[name].loc[ref, sorted(rates)], after[name].loc[ref, sorted(rates)])
        moved = [c for c in changeable & set(before[name].columns)]
        assert any((before[name].loc[~kept, c] != after[name].loc[~kept, c]).any() for c in moved)


def test_rates_and_identities_do_not_move(tmp_path):
    folder = _products(tmp_path)
    before = _text(folder)
    splice_labor_products(folder, ENABLED)
    after = _text(folder)
    for name in ("departamentos", "ciudades"):
        old, new = _num(before[name], LEVELS), _num(after[name], LEVELS)
        for top, bottom in (("unemployed", "labor_force"), ("employed", "working_age"), ("labor_force", "working_age")):
            assert np.allclose(old[top] / old[bottom], new[top] / new[bottom], rtol=0, atol=1e-12)
        assert np.allclose(new.labor_force, new.employed + new.unemployed, rtol=1e-12)
        assert np.allclose(new.working_age, new.labor_force + new.inactive, rtol=1e-12)


def test_levels_scale_by_the_share_ratio_and_population_is_unchanged(tmp_path):
    folder = _products(tmp_path)
    old = _num(_text(folder)["departamentos"], (*LEVELS, "population"))
    report = splice_labor_products(folder, ENABLED)
    new = _num(_text(folder)["departamentos"], (*LEVELS, "population"))
    pre = _text(folder)["departamentos"].period < CUT
    assert np.array_equal(old.population, new.population)
    ratio = new.employed[pre] / old.employed[pre]
    assert np.allclose(ratio, new.working_age[pre] / old.working_age[pre], rtol=1e-12)  # one k for all levels
    assert (ratio > 1).all() and ratio.max() < 1.06
    assert report["scale_factor"]["departments"][0] > 1


def test_the_pet_share_break_is_recovered_per_department_and_the_seam_closes(tmp_path):
    folder = _products(tmp_path, jumps=(0.016, 0.012, 0.020))
    report = splice_labor_products(folder, ENABLED)
    found = {c: v["delta_pp"] / 100 for c, v in report["departments"].items()}
    for code, truth in zip(("5", "8", "11"), (0.016, 0.012, 0.020), strict=True):
        assert found[code] == pytest.approx(truth, abs=0.004)
    dep = _text(folder)["departamentos"]
    share = (pd.to_numeric(dep.working_age) / pd.to_numeric(dep.population)).groupby(dep.dep_code)
    for code, series in share:
        s = series.reset_index(drop=True)
        assert abs(s[PERIODS.index(CUT)] - s[PERIODS.index(CUT) - 1]) < 0.007  # was ~0.016 + trend


def test_national_icml_is_the_sum_of_the_corrected_departments(tmp_path):
    folder = _products(tmp_path)
    splice_labor_products(folder, ENABLED)
    text = _text(folder)
    dep = text["departamentos"].assign(**{c: lambda d, c=c: pd.to_numeric(d[c]) for c in LEVELS})
    summed = dep.groupby("period")[list(LEVELS)].sum()
    nat = text["nacionales"]
    icml = nat[nat.national_type == "ICML_COMPLETO"].set_index("period")
    for level in LEVELS:
        assert np.allclose(pd.to_numeric(icml[level]), summed[level].reindex(icml.index), rtol=0, atol=1e-6)


def test_the_reference_national_has_its_own_break_and_population_is_never_touched(tmp_path):
    folder = _products(tmp_path, reference_jump=0.014)
    before = _text(folder)["nacionales"]
    report = splice_labor_products(folder, ENABLED)
    after = _text(folder)["nacionales"]
    assert report["national_reference"]["delta_pp"] / 100 == pytest.approx(0.014, abs=0.004)
    ref = after.national_type == "DANE_REFERENCIA"
    assert (before.loc[ref, "population"] == after.loc[ref, "population"]).all()
    assert (before.loc[ref & (after.period < CUT), "employed"] != after.loc[ref & (after.period < CUT), "employed"]).all()


def test_cities_use_one_common_break_unless_asked_for_their_own(tmp_path):
    folder = _products(tmp_path, city_jump=0.010)
    pooled = splice_labor_products(folder, ENABLED)
    cities = _text(folder)["ciudades"]
    share = pd.to_numeric(cities.working_age) / pd.to_numeric(cities.population)
    assert pooled["cities"]["mode"] == "pooled"
    assert pooled["cities"]["pooled_delta_pp"] / 100 == pytest.approx(0.010, abs=0.004)
    folder2 = _products(tmp_path / "b", city_jump=0.010)
    own = splice_labor_products(folder2, LaborBaseSplice(enabled=True, city_break="own"))
    assert own["cities"]["mode"] == "own" and len(own["cities"]["own_delta_pp"]) == 3
    assert share.notna().all()


def test_the_report_is_written_beside_the_products(tmp_path):
    folder = _products(tmp_path)
    splice_labor_products(folder, ENABLED)
    saved = json.loads((folder.parent / "labor_base_splice.json").read_text("utf-8"))
    assert saved["break_month"] == CUT and saved["rates_max_change"] < 1e-9 and saved["months_shifted"] == 96


def test_a_share_pushed_above_one_is_refused(tmp_path):
    folder = _products(tmp_path)
    dep = pd.read_csv(folder / "departamentos.csv", dtype={"dep_code": str})
    cities, national = pd.read_csv(folder / "ciudades.csv"), pd.read_csv(folder / "nacionales.csv")
    # A falling pre-break share that starts near 1 and ends far below the
    # post-break one: a positive shift would push its early months above 1.
    own = dep.dep_code == "5"
    values = np.concatenate([np.linspace(0.995, 0.60, 96), np.full(len(PERIODS) - 96, 0.80)])
    pet = values * dep.loc[own, "population"].to_numpy()
    dep.loc[own, "working_age"] = pet
    dep.loc[own, "labor_force"] = pet * 0.7
    dep.loc[own, "employed"] = pet * 0.6
    dep.loc[own, "unemployed"] = pet * 0.1
    dep.loc[own, "inactive"] = pet * 0.3
    with pytest.raises(ValueError, match=r"outside \(0, 1\]"):
        splice_frames(dep, cities, national, ENABLED)


def test_disabled_and_incomplete_inputs_are_refused(tmp_path):
    folder = _products(tmp_path)
    dep, cit, nat = (pd.read_csv(folder / f"{n}.csv") for n in ("departamentos", "ciudades", "nacionales"))
    with pytest.raises(ValueError, match="disabled"):
        splice_frames(dep, cit, nat, LaborBaseSplice())
    with pytest.raises(ValueError, match="lacks columns"):
        splice_frames(dep.drop(columns="inactive"), cit, nat, ENABLED)


def test_configuration_defaults_to_off_and_validates(tmp_path):
    assert LaborBaseSplice.from_toml(tmp_path / "missing.toml") == LaborBaseSplice(enabled=False)
    path = tmp_path / "labor.toml"
    path.write_text('[labor_base_splice]\nenabled = true\ncity_break = "own"\nwindow_months = 18\n')
    assert LaborBaseSplice.from_toml(path) == LaborBaseSplice(enabled=True, window_months=18, city_break="own")
    path.write_text("[labor_base_splice]\nenabled = true\nfoo = 1\n")
    with pytest.raises(ValueError, match="Unknown"):
        LaborBaseSplice.from_toml(path)
    with pytest.raises(ValueError, match="city_break"):
        LaborBaseSplice(city_break="median")
    with pytest.raises(ValueError, match="YYYY-MM"):
        LaborBaseSplice(break_month="2001")


def test_national_icml_rates_follow_its_levels_and_the_reference_rates_do_not_move(tmp_path):
    folder = _products(tmp_path)
    before = _text(folder)["nacionales"]
    report = splice_labor_products(folder, ENABLED)
    after = _text(folder)["nacionales"]
    pre = after.period < CUT
    icml = after.national_type == "ICML_COMPLETO"
    lv = after[icml].apply(lambda col: pd.to_numeric(col, errors="coerce"))
    for column, (top, bottom) in (("unemployment_rate", ("unemployed", "labor_force")),
                                  ("employment_rate", ("employed", "working_age")),
                                  ("participation_rate", ("labor_force", "working_age"))):
        assert np.allclose(lv[column], lv[top] / lv[bottom], rtol=0, atol=1e-12)  # columns equal level ratios
    moved = pd.to_numeric(after.loc[icml & pre, "unemployment_rate"]) - pd.to_numeric(before.loc[icml & pre, "unemployment_rate"])
    assert 0 < moved.abs().max() <= 5e-4 and report["national_icml_rates_max_change"] == pytest.approx(moved.abs().max(), abs=5e-4)
    ref = after.national_type == "DANE_REFERENCIA"
    assert (before.loc[ref, "unemployment_rate"] == after.loc[ref, "unemployment_rate"]).all()  # exactly the same text
