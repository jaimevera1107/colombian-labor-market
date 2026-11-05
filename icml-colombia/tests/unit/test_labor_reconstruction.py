"""Restoration of the 1993-2000 labor reconstruction: linear PET and generated components."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from icml.informality.regime_splice import RegimeSplice
from icml.pipeline import labor_reconstruction as lr
from icml.pipeline.labor_base_splice import LaborBaseSplice

PROJECT = Path(__file__).resolve().parents[2]
CONFIGS = PROJECT / "configs" / "rc1"
CONFIG = lr.LaborReconstruction(enabled=True)
FULL = lr.LaborReconstruction(enabled=True, linearize_population=True, smooth_territories=True)
MONTHS = [f"{y}-{m:02d}" for y in range(1993, 2005) for m in range(1, 13)]
CUT = "2001-01"


def _series(scale: float, seed: int, bumps: bool = True, pet_factor: np.ndarray | None = None) -> pd.DataFrame:
    """A labor series with a bumpy PET and smooth history, seasonal and noisy official months."""
    rng = np.random.default_rng(seed)
    t = np.arange(len(MONTHS))
    pet = scale * (20.0 + 0.08 * t)
    if bumps:
        pet = pet + scale * np.where(t >= 40, 0.9, 0.0) - scale * np.where(t >= 75, 0.5, 0.0)  # steps, like the old survey
    official = np.array(MONTHS) >= CUT
    population = pet / 0.72
    if pet_factor is not None:
        pet = pet * pet_factor  # a territory's PET zig-zags
    month = np.array([int(p[5:]) for p in MONTHS])
    seasonal = np.where(official, 0.025 * np.cos(2 * np.pi * (month - 1) / 12), 0.002 * np.cos(2 * np.pi * (month - 1) / 12))
    to = 0.55 + 0.0004 * t + seasonal + np.where(official, rng.normal(0, 0.006, len(t)), 0.0)
    td = 0.14 - 0.0003 * t - 0.8 * seasonal + np.where(official, rng.normal(0, 0.004, len(t)), 0.0)
    employed = to * pet
    pea = employed / (1 - td)
    return pd.DataFrame(
        {"employed": employed, "unemployed": pea - employed, "labor_force": pea, "inactive": pet - pea, "working_age": pet, "population": population},
        index=pd.Index(MONTHS, name="period"),
    )


def _long(frame: pd.DataFrame, **keys) -> pd.DataFrame:
    out = frame.reset_index()
    for key, value in keys.items():
        out.insert(1, key, value)
    return out


def make_products() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    deps, cities = {}, {}
    rng = np.random.default_rng(99)
    official = np.array(MONTHS) >= CUT
    scales = {"05": 5.0, "08": 2.0, "99": 0.05}
    base = {code: _series(scale, 10 + k, bumps=True).working_age.to_numpy() for k, (code, scale) in enumerate(scales.items())}
    noise = {code: 1 + 0.01 * np.where(official, rng.normal(0, 1, len(MONTHS)), 0.0) for code in scales}
    total = sum(base.values())
    norm = total / sum(base[c] * noise[c] for c in scales)  # the zig-zag cancels between departments, as in the real data
    for k, (code, scale) in enumerate(scales.items()):
        deps[code] = _series(scale, 10 + k, pet_factor=noise[code] * norm)
    for k, (code, scale) in enumerate((("11001", 6.0), ("05001", 2.0))):
        cities[code] = _series(scale, 20 + k, pet_factor=1 + 0.01 * np.where(official, rng.normal(0, 1, len(MONTHS)), 0.0))
    departments = pd.concat([_long(f, dep_code=c) for c, f in deps.items()], ignore_index=True)
    for level in lr.LEVELS:
        departments[f"factor_{level}"] = 1.0
        departments[f"{level}_represented"] = departments[level]
    departments["factor_population"] = 1.0
    departments["population_represented"] = departments["population"]
    # department 99 is outside the GEIH before 2003 and half inside it after; the others are fully represented
    partial = (departments.dep_code == "99") & (departments.period >= CUT)
    factor = np.where(departments.loc[partial, "period"] < "2003-01", 0.0, 0.5)
    for level in (*lr.LEVELS, "population"):
        departments.loc[partial, f"factor_{level}"] = factor
        departments.loc[partial, f"{level}_represented"] = factor * departments.loc[partial, level]
    for column, (top, bottom) in lr.RATE_COLUMNS.items():
        departments[column] = departments[top] / departments[bottom]
    total = sum(deps.values())
    reference = _series(7.0, 30)
    national = pd.concat([_long(total, national_type="ICML_COMPLETO"), _long(reference, national_type=lr.REFERENCE)], ignore_index=True)
    for column, (top, bottom) in lr.RATE_COLUMNS.items():
        national[column] = national[top] / national[bottom]
    cit = pd.concat([_long(f, city_code=c) for c, f in cities.items()], ignore_index=True)
    return departments, cit, national


@pytest.fixture(scope="module")
def products():
    return make_products()


@pytest.fixture(scope="module")
def result(products):
    return lr.reconstruct_frames(*products, CONFIG)


def _max_line_deviation(values: np.ndarray) -> float:
    x = np.arange(len(values))
    return float(np.abs(values - np.polyval(np.polyfit(x, values, 1), x)).max())


# ------------------------------------------------------------------ building blocks


def test_the_line_runs_from_the_start_and_leaves_the_anchor_for_the_next_month():
    line = lr.linear_path(10.0, 18.0, 8)
    assert line[0] == 10.0 and np.allclose(np.diff(line), 1.0) and line[-1] == 17.0  # 18 is the official month


def test_the_noise_of_a_month_does_not_depend_on_order_or_on_the_other_months():
    template = lr.Template("td", 0.01, 0.02, 0.1, 100)
    forward = [lr.period_noise(p, template, CONFIG) for p in MONTHS]
    backward = [lr.period_noise(p, template, CONFIG) for p in reversed(MONTHS)][::-1]
    assert forward == backward
    assert lr.period_noise("1997-04", template, CONFIG, "dep:05") != lr.period_noise("1997-04", template, CONFIG, "dep:08")
    assert max(abs(v) for v in forward) <= 2.5 * 0.02 * CONFIG.scaling_factor + 1e-12
    off = lr.LaborReconstruction(enabled=True, scaling_factor=0.0)
    assert all(lr.period_noise(p, template, off) == 0.0 for p in MONTHS)


def test_templates_describe_the_official_irregular_and_refuse_short_series():
    official = _series(5.0, 1).loc[CUT:]
    templates = lr.fit_templates(official, CONFIG)
    assert set(templates) == {"to", "td", "tgp"} and all(t.irregularity_std > 0 for t in templates.values())
    with pytest.raises(lr.ReconstructionError, match="too short"):
        lr.fit_templates(official.iloc[:10], CONFIG)


def test_the_seasonal_swap_gives_a_smooth_segment_the_reference_pattern():
    frame = _series(5.0, 2, bumps=False)
    pre = frame.loc[: "2000-12", "employed"]
    reference = frame.loc[CUT:, "employed"]
    swapped = lr.swap_seasonal(pre, reference, CONFIG)
    months = pre.index.str[5:7]
    pattern_new = (swapped - swapped.rolling(13, center=True, min_periods=1).mean()).groupby(months).mean()
    pattern_ref = (reference - reference.rolling(13, center=True, min_periods=1).mean()).groupby(reference.index.str[5:7]).mean()
    assert np.corrcoef(pattern_new.to_numpy(), pattern_ref.to_numpy())[0, 1] > 0.9
    assert abs(swapped.mean() / pre.mean() - 1) < 0.01  # the level is kept
    with pytest.raises(lr.ReconstructionError):
        lr.swap_seasonal(pre.iloc[:12], reference, CONFIG)


# ------------------------------------------------------------------ one series


def test_the_pet_of_a_series_is_an_exact_line_through_the_official_anchor():
    frame = _series(5.0, 3)
    levels, details = lr.reconstruct_series(frame, CONFIG)
    assert _max_line_deviation(frame["working_age"].loc[:"2000-12"].to_numpy()) > 1.0  # the input has steps
    assert _max_line_deviation(levels["working_age"].to_numpy()) < 1e-6
    anchor = frame.loc[CUT, "working_age"]
    assert levels["working_age"].iloc[-1] + details["monthly_slope"] == pytest.approx(anchor)  # one slope across the seam
    assert levels["working_age"].iloc[0] == pytest.approx(frame["working_age"].iloc[:12].median())
    assert list(levels.index) == [p for p in MONTHS if p < CUT]


def test_every_accounting_identity_holds_exactly_and_the_levels_are_valid():
    levels, _ = lr.reconstruct_series(_series(5.0, 4), CONFIG)
    assert np.abs(levels["labor_force"] - levels["employed"] - levels["unemployed"]).max() < 1e-6
    assert np.abs(levels["working_age"] - levels["labor_force"] - levels["inactive"]).max() < 1e-6
    assert (levels > 0).all().all()


def test_the_components_come_back_with_the_dynamics_of_the_official_months():
    frame = _series(5.0, 5)
    levels, _ = lr.reconstruct_series(frame, CONFIG)
    before = (frame["unemployed"] / frame["labor_force"]).loc[:"2000-12"].diff().std()
    after = (levels["unemployed"] / levels["labor_force"]).diff().std()
    official = (frame["unemployed"] / frame["labor_force"]).loc[CUT:].diff().std()
    assert after > 3 * before and 0.4 * official < after < 2.5 * official


def test_the_series_is_reproducible_and_a_salt_changes_only_the_noise():
    frame = _series(5.0, 6)
    a, _ = lr.reconstruct_series(frame, CONFIG)
    b, _ = lr.reconstruct_series(frame.iloc[::-1].sort_index(), CONFIG)  # same data, different arrival order
    pd.testing.assert_frame_equal(a, b)
    c, _ = lr.reconstruct_series(frame, CONFIG, salt="dep:05")
    assert np.array_equal(a["working_age"], c["working_age"]) and not np.allclose(a["employed"], c["employed"])


def test_a_series_whose_labor_force_would_exceed_its_population_is_refused():
    frame = _series(5.0, 7)
    frame.loc[:"2000-12", "employed"] = frame.loc[:"2000-12", "working_age"] * 0.97
    frame.loc[:"2000-12", "unemployed"] = frame.loc[:"2000-12", "employed"] * 0.05
    frame["labor_force"] = frame["employed"] + frame["unemployed"]
    frame["inactive"] = frame["working_age"] - frame["labor_force"]
    with pytest.raises(lr.ReconstructionError, match="exceed"):
        lr.reconstruct_series(frame, CONFIG)


def test_a_missing_splice_month_or_a_short_history_is_refused():
    with pytest.raises(lr.ReconstructionError, match="not in the series"):
        lr.reconstruct_series(_series(5.0, 8).loc[: "2000-12"], CONFIG)
    with pytest.raises(lr.ReconstructionError, match="too short"):
        lr.reconstruct_series(_series(5.0, 9).loc["1999-06":], CONFIG)


# ------------------------------------------------------------------ the three products


def test_every_territory_gets_its_own_linear_pet(result):
    dep, cit, nat, _ = result
    for frame, key in ((dep, "dep_code"), (cit, "city_code")):
        for code, group in frame.groupby(key):
            pet = group.set_index("period").sort_index().loc[:"2000-12", "working_age"].to_numpy()
            assert _max_line_deviation(pet) < 1e-6, code
    icml = nat[nat.national_type == "ICML_COMPLETO"].set_index("period").sort_index().loc[:"2000-12", "working_age"]
    assert _max_line_deviation(icml.to_numpy()) < 1e-6  # a sum of lines is a line


def test_icml_is_the_sum_of_the_departments_and_the_reference_gets_the_national_result(products, result):
    dep, _, nat, _ = result
    pre = dep[dep.period < CUT]
    sums = pre.groupby("period")[list(lr.LEVELS)].sum()
    icml = nat[(nat.national_type == "ICML_COMPLETO") & (nat.period < CUT)].set_index("period").sort_index()
    for level in lr.LEVELS:
        np.testing.assert_allclose(icml[level].to_numpy(), sums[level].sort_index().to_numpy(), rtol=0, atol=1e-6)
    reference = products[2][products[2].national_type == lr.REFERENCE].set_index("period").sort_index()
    levels, _ = lr.reconstruct_series(reference, CONFIG)
    new = nat[(nat.national_type == lr.REFERENCE) & (nat.period < CUT)].set_index("period").sort_index()
    np.testing.assert_allclose(new["employed"].to_numpy(), levels["employed"].to_numpy(), rtol=0, atol=1e-6)


def test_the_identities_hold_in_every_product_and_the_rates_follow_the_levels(result):
    dep, cit, nat, report = result
    for frame in (dep, cit, nat):
        pre = frame[frame.period < CUT]
        assert np.abs(pre.labor_force - pre.employed - pre.unemployed).max() < 1e-6
        assert np.abs(pre.working_age - pre.labor_force - pre.inactive).max() < 1e-6
    for frame in (dep, nat):
        pre = frame[frame.period < CUT]
        np.testing.assert_allclose(pre.unemployment_rate, pre.unemployed / pre.labor_force)
        np.testing.assert_allclose(pre.participation_rate, pre.labor_force / pre.working_age)
    assert max(max(v.values()) for v in report["accounting_residual_max_persons"].values()) < 1e-6


def test_nothing_changes_from_the_first_official_month_on(products, result):
    for before, after in zip(products, result[:3], strict=True):
        official = before.period >= CUT
        pd.testing.assert_frame_equal(before[official].reset_index(drop=True), after[official].reset_index(drop=True))
        assert not before[~official].equals(after[~official])


def test_the_inputs_are_not_modified(products):
    snapshot = [frame.copy() for frame in products]
    lr.reconstruct_frames(*products, CONFIG)
    for before, after in zip(snapshot, products, strict=True):
        pd.testing.assert_frame_equal(before, after)


def test_the_represented_columns_follow_the_full_ones_before_2001(result):
    dep = result[0]
    pre = dep[dep.period < CUT]
    for level in lr.LEVELS:
        np.testing.assert_allclose(pre[f"{level}_represented"], pre[f"factor_{level}"] * pre[level])


def test_the_report_says_what_was_done(result):
    report = result[3]
    assert report["splice_month"] == CUT and report["months_rebuilt"] == 96 and report["base_seed"] == 42
    assert set(report["templates"]) == {"to", "td", "tgp"}
    after, before = report["monthly_change_std_pp"]["reference"]["after"], report["monthly_change_std_pp"]["reference"]["before"]
    assert after["td"] > before["td"] and after["to"] > before["to"]
    assert set(report["pet_lines"]) == {"departments", "cities"} and "05" in report["pet_lines"]["departments"]


def test_a_disabled_restoration_cannot_be_applied(products):
    with pytest.raises(ValueError, match="disabled"):
        lr.reconstruct_frames(*products, lr.LaborReconstruction())


def test_a_product_without_the_needed_columns_is_refused(products):
    dep, cit, nat = products
    with pytest.raises(lr.ReconstructionError, match="lacks columns"):
        lr.reconstruct_frames(dep.drop(columns=["inactive"]), cit, nat, CONFIG)


def test_the_population_is_left_alone_unless_asked_and_then_it_is_a_line(products):
    dep, cit, nat = products
    out = lr.reconstruct_frames(dep, cit, nat, CONFIG)[0]
    np.testing.assert_array_equal(out["population"], dep["population"])
    linear = lr.reconstruct_frames(dep, cit, nat, lr.LaborReconstruction(enabled=True, linearize_population=True))[0]
    pop = linear[linear.dep_code == "05"].set_index("period").sort_index().loc[:"2000-12", "population"].to_numpy()
    assert _max_line_deviation(pop) < 1e-6


# ------------------------------------------------------------------ files and configuration


def test_the_files_keep_every_untouched_cell_as_it_was_written(products, tmp_path):
    folder = tmp_path / "products"
    folder.mkdir()
    names = {"departamentos": products[0], "ciudades": products[1], "nacionales": products[2]}
    for name, frame in names.items():
        frame.to_csv(folder / f"{name}.csv", index=False, lineterminator="\n")
    before = {n: pd.read_csv(folder / f"{n}.csv", dtype=str, keep_default_na=False) for n in names}
    report = lr.reconstruct_labor_products(folder, CONFIG)
    assert json.loads((tmp_path / "labor_reconstruction.json").read_text("utf-8"))["splice_month"] == CUT
    assert report["files"] == list(lr.FILES)
    for name in names:
        after = pd.read_csv(folder / f"{name}.csv", dtype=str, keep_default_na=False)
        official = before[name].period >= CUT
        pd.testing.assert_frame_equal(before[name][official].reset_index(drop=True), after[official].reset_index(drop=True))
        assert list(after.columns) == list(before[name].columns) and len(after) == len(before[name])


def test_the_configuration_is_validated():
    assert not lr.LaborReconstruction.from_toml(Path("does-not-exist.toml")).enabled
    for bad in ({"splice_month": "2001/01"}, {"scaling_factor": 1.5}, {"stl_seasonal": 12}, {"floor_share": 0.0},
                {"reference_first_year": 2019, "reference_last_year": 2018}):
        with pytest.raises(ValueError):
            lr.LaborReconstruction(**bad)


def test_an_unknown_key_in_the_file_is_an_error(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[labor_reconstruction]\nenabled = true\nscaling = 0.4\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown"):
        lr.LaborReconstruction.from_toml(path)


def test_the_pet_base_splice_and_this_restoration_cannot_run_together():
    with pytest.raises(ValueError, match="mutually exclusive"):
        lr.require_exclusive_with_base_splice(True, CONFIG)
    lr.require_exclusive_with_base_splice(False, CONFIG)
    lr.require_exclusive_with_base_splice(True, lr.LaborReconstruction())


def test_the_repository_adopts_the_restoration_and_retires_the_splice_it_replaces():
    reconstruction = lr.LaborReconstruction.from_toml(CONFIGS / "labor_reconstruction.toml")
    base = LaborBaseSplice.from_toml(CONFIGS / "labor_base_splice.toml")
    informality = RegimeSplice.from_toml(CONFIGS / "regime_splice.toml")
    assert reconstruction.enabled and informality.enabled and not base.enabled
    assert reconstruction.splice_month == informality.break_month == "2001-01"  # one seam, one month
    lr.require_exclusive_with_base_splice(base.enabled, reconstruction)


# ------------------------------------------------------------------ the frozen August products


FROZEN = PROJECT.parent / "datos" / "2_procesamiento" / "productos_congelados" / "laboral"


@pytest.mark.skipif(not (FROZEN / "nacionales.csv").is_file(), reason="frozen labor products not in the checkout")
def test_on_the_frozen_august_products_the_pet_is_a_line_and_the_components_return(tmp_path):
    folder = tmp_path / "products"
    folder.mkdir()
    for name in lr.FILES:
        shutil.copy2(FROZEN / f"{name}.csv", folder / f"{name}.csv")
    report = lr.reconstruct_labor_products(folder, CONFIG)
    nat = pd.read_csv(folder / "nacionales.csv")
    for kind in ("DANE_REFERENCIA", "ICML_COMPLETO"):
        pet = nat[nat.national_type == kind].set_index("period").sort_index().loc["1993-01":"2000-12", "working_age"].to_numpy()
        assert _max_line_deviation(pet) < 1e-3
    dep = pd.read_csv(folder / "departamentos.csv", dtype={"dep_code": str})
    assert dep.dep_code.nunique() == 33 and report["floors_applied"] == {"national": 0, "departments": 0, "cities": 0}
    change = report["monthly_change_std_pp"]
    # The frozen products are already the reconstructed vintage: reapplying keeps the components.
    assert change["reference"]["after"]["td"] >= 0.95 * change["reference"]["before"]["td"]
    assert change["icml"]["after"]["td"] >= 0.95 * change["icml"]["before"]["td"]


# ------------------------------------------------------------------ after the first official month


@pytest.fixture(scope="module")
def full(products):
    return lr.reconstruct_frames(*products, FULL)


def _direction_changes(values: np.ndarray) -> int:
    return int((np.diff(np.sign(np.diff(values))) != 0).sum())


def test_the_smoother_keeps_every_annual_mean_and_lines_and_constants_pass_through():
    years = np.repeat(np.arange(2001, 2008), 12)[:80]  # a partial last year
    rng = np.random.default_rng(0)
    noisy = 100 + 0.5 * np.arange(80) + rng.normal(0, 3, 80)
    smooth = lr.smooth_annual_means(noisy[:, None], years)[:, 0]
    for year in np.unique(years):
        assert smooth[years == year].mean() == pytest.approx(noisy[years == year].mean(), abs=1e-9)
    assert np.abs(np.diff(smooth, 2)).max() < np.abs(np.diff(noisy, 2)).max() / 5
    line = (7 + 0.25 * np.arange(80))[:, None]
    np.testing.assert_allclose(lr.smooth_annual_means(line, years), line, atol=1e-8)
    np.testing.assert_allclose(lr.smooth_annual_means(np.full((80, 1), 3.0), years), 3.0, atol=1e-10)
    with pytest.raises(lr.ReconstructionError, match="two years"):
        lr.smooth_annual_means(np.ones((10, 1)), np.full(10, 2001))


def test_smoothing_shares_that_add_to_one_gives_shares_that_add_to_one():
    years = np.repeat(np.arange(2001, 2006), 12)
    shares = np.random.default_rng(1).dirichlet(np.ones(4) * 20, size=len(years))
    np.testing.assert_allclose(lr.smooth_annual_means(shares, years).sum(axis=1), 1.0, atol=1e-12)


def test_the_territorial_pet_and_population_become_smooth_after_the_first_official_month(products, full):
    dep, cit = full[0], full[1]
    before = products[0]
    for frame_before, frame_after, key in ((products[0], dep, "dep_code"), (products[1], cit, "city_code")):
        for code in frame_after[key].unique():
            old = frame_before[(frame_before[key] == code) & (frame_before.period >= CUT)].sort_values("period").working_age.to_numpy()
            new = frame_after[(frame_after[key] == code) & (frame_after.period >= CUT)].sort_values("period").working_age.to_numpy()
            assert _direction_changes(old) > 10 > _direction_changes(new), code
    assert not before.equals(dep)


def test_the_departments_still_add_to_the_national_figure_and_employment_is_untouched(products, full):
    dep, _, nat, report = full
    official = dep[dep.period >= CUT]
    icml = nat[(nat.national_type == "ICML_COMPLETO") & (nat.period >= CUT)].set_index("period").sort_index()
    sums = official.groupby("period")[["working_age", "population", "employed", "inactive"]].sum().sort_index()
    for column in sums.columns:
        np.testing.assert_allclose(sums[column].to_numpy(), icml[column].to_numpy(), rtol=0, atol=1e-4)
    for column in ("employed", "unemployed", "labor_force", "unemployment_rate"):
        pd.testing.assert_series_equal(products[0][products[0].period >= CUT][column].reset_index(drop=True), official[column].reset_index(drop=True))
    assert report["official_months_checks"]["departments_vs_national_max_gap_persons"] < 1e-4


def test_the_national_series_do_not_change_after_the_first_official_month(products, full):
    nat_before, nat_after = products[2], full[2]
    official = nat_before.period >= CUT
    pd.testing.assert_frame_equal(nat_before[official].reset_index(drop=True), nat_after[official].reset_index(drop=True))


def test_inactive_absorbs_the_pet_and_the_identities_hold_after_the_first_official_month(full):
    for frame in full[:2]:
        official = frame[frame.period >= CUT]
        np.testing.assert_allclose(official.inactive, official.working_age - official.labor_force, atol=1e-6)
        np.testing.assert_allclose(official.labor_force, official.employed + official.unemployed, atol=1e-6)
        assert (official.working_age <= official.population).all() and (official.inactive > 0).all()


def test_the_represented_columns_follow_the_smoothed_levels(full):
    dep = full[0]
    for level in lr.SMOOTHED:
        np.testing.assert_allclose(dep[f"{level}_represented"], dep[f"factor_{level}"] * dep[level], rtol=1e-12, atol=1e-6)


def test_the_line_before_the_first_official_month_ends_at_the_smoothed_value(full):
    dep = full[0]
    for code, group in dep.groupby("dep_code"):
        series = group.set_index("period").sort_index()
        for column in ("working_age", "population"):
            pre = series.loc[:"2000-12", column].to_numpy()
            assert _max_line_deviation(pre) < 1e-6, (code, column)
            slope = pre[-1] - pre[-2]
            assert pre[-1] + slope == pytest.approx(series.loc[CUT, column], rel=1e-9)  # one slope into the smoothed anchor


def test_the_population_is_a_line_before_2001_in_every_product_when_asked(full):
    dep, cit, nat, _ = full
    for frame, key in ((dep, "dep_code"), (cit, "city_code")):
        for code, group in frame.groupby(key):
            assert _max_line_deviation(group.set_index("period").sort_index().loc[:"2000-12", "population"].to_numpy()) < 1e-6
    for kind in (lr.REFERENCE, "ICML_COMPLETO"):
        pop = nat[nat.national_type == kind].set_index("period").sort_index().loc[:"2000-12", "population"].to_numpy()
        assert _max_line_deviation(pop) < 1e-6, kind


def test_smoothing_that_would_push_the_pet_above_the_population_is_refused(products):
    dep, cit, nat = (frame.copy() for frame in products)
    rows = dep.dep_code == "05"
    dep.loc[rows & (dep.period >= CUT), "population"] = dep.loc[rows & (dep.period >= CUT), "working_age"] * 0.999
    cit_bad = cit.copy()
    with pytest.raises(lr.ReconstructionError):
        lr.reconstruct_frames(dep, cit_bad, nat, FULL)


def test_the_files_change_only_the_allowed_columns_after_the_first_official_month(products, tmp_path):
    folder = tmp_path / "products"
    folder.mkdir()
    names = {"departamentos": products[0], "ciudades": products[1], "nacionales": products[2]}
    for name, frame in names.items():
        frame.to_csv(folder / f"{name}.csv", index=False, lineterminator="\n")
    before = {n: pd.read_csv(folder / f"{n}.csv", dtype=str, keep_default_na=False) for n in names}
    report = lr.reconstruct_labor_products(folder, FULL)
    assert "smoothing" in report and set(report["smoothing"]) == {"working_age", "population"}
    allowed = {*lr.SMOOTHED, "employment_rate", "participation_rate", *(f"{c}_represented" for c in lr.SMOOTHED), *(f"factor_{c}" for c in lr.SMOOTHED)}
    for name in names:
        after = pd.read_csv(folder / f"{name}.csv", dtype=str, keep_default_na=False)
        official = before[name].period >= CUT
        left = [c for c in before[name].columns if c not in allowed or name == "nacionales"]
        pd.testing.assert_frame_equal(before[name].loc[official, left].reset_index(drop=True), after.loc[official, left].reset_index(drop=True))
        if name != "nacionales":
            assert (before[name].loc[official, "working_age"].to_numpy() != after.loc[official, "working_age"].to_numpy()).any()


def test_the_repository_adopts_the_linear_population_and_the_territorial_smoothing():
    adopted = lr.LaborReconstruction.from_toml(CONFIGS / "labor_reconstruction.toml")
    assert adopted.linearize_population and adopted.smooth_territories


def test_the_coverage_of_every_territory_and_the_represented_sums_survive_the_smoothing(products, full):
    before, after = products[0], full[0]
    official = before.period >= CUT

    def coverage(frame):
        f = frame[frame.period >= CUT]
        return pd.Series(np.where(f.population_represented <= 0, "SIN", np.where(f.factor_population < 1 - 1e-9, "PARCIAL", "COMPLETA")), index=f.index)

    before_class, after_class = coverage(before), coverage(after)
    assert set(before_class) == {"SIN", "PARCIAL", "COMPLETA"}
    assert (before_class == after_class).all()  # no territory changes class
    complete = after.loc[after_class[after_class == "COMPLETA"].index]
    assert (complete.factor_population == 1.0).all() and (complete.factor_working_age == 1.0).all()  # exactly one
    assert (after.loc[after_class[after_class == "SIN"].index].population_represented == 0.0).all()
    for column in ("working_age_represented", "population_represented"):
        sum_before = before[official].groupby("period")[column].sum()
        sum_after = after[official].groupby("period")[column].sum()
        covered = sum_before.index >= "2003-01"  # from then on every territory is at least partly represented
        # Proportional smoothing of the partial territories: the represented sum may move a little (< 2 %).
        np.testing.assert_allclose(sum_after[covered].to_numpy(), sum_before[covered].to_numpy(), rtol=0.02)
        assert (sum_after[~covered] / sum_before[~covered] - 1).abs().max() < 0.02  # before, it may move a little
    partial = after.loc[after_class[after_class == "PARCIAL"].index]
    assert ((partial.factor_population > 0) & (partial.factor_population < 1)).all()
    assert (after.inactive_represented[after.period >= CUT] >= -1e-6).all()


def test_a_represented_level_above_the_full_one_is_refused(products):
    dep, cit, nat = (frame.copy() for frame in products)
    rows = (dep.dep_code == "05") & (dep.period >= CUT)
    dep.loc[rows, "population_represented"] = dep.loc[rows, "population"] * 1.1
    with pytest.raises(lr.ReconstructionError, match="exceeds"):
        lr.reconstruct_frames(dep, cit, nat, FULL)


def test_the_written_files_keep_the_factor_identity_for_every_level(products, tmp_path):
    folder = tmp_path / "products"
    folder.mkdir()
    for name, frame in {"departamentos": products[0], "ciudades": products[1], "nacionales": products[2]}.items():
        frame.to_csv(folder / f"{name}.csv", index=False, lineterminator="\n")
    lr.reconstruct_labor_products(folder, FULL)
    dep = pd.read_csv(folder / "departamentos.csv", dtype={"dep_code": str})
    for level in (*lr.LEVELS, "population"):
        np.testing.assert_allclose(dep[f"{level}_represented"], dep[f"factor_{level}"] * dep[level], rtol=1e-9, atol=1e-6, err_msg=level)
    partial = dep[(dep.dep_code == "99") & (dep.period >= "2003-01")]
    # Proportional smoothing: the partial territory keeps its share (the PET factor does not move).
    np.testing.assert_allclose(partial.factor_working_age, 0.5, atol=1e-9)
