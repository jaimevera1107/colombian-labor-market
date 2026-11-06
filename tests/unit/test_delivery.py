"""Two-universe deliverables: lossless split, naming and manifest."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from icml.delivery.builder import (
    MODES,
    build_delivery,
    read_text_table,
    run_stamp,
)
from icml.delivery.spec import SPECS, SPECS_BY_ID, UNIVERSES

# Header of every internal product, as written by the H36 engine.
EXPECTED_COLUMNS: dict[str, list[str]] = {
    "labor.departamentos": (
        "period,dep_code,employed,unemployed,inactive,labor_force,working_age,"
        "population,employed_represented,unemployed_represented,"
        "inactive_represented,population_represented,source,"
        "employed_residual_share,unemployed_residual_share,"
        "inactive_residual_share,population_residual_share,"
        "factor_reference_status,labor_force_represented,"
        "working_age_represented,factor_employed,factor_unemployed,"
        "factor_inactive,factor_labor_force,factor_working_age,"
        "factor_population,year,unemployment_rate,employment_rate,"
        "participation_rate,territory_id,territory_name,territory_level,"
        "is_additive_member,factor_is_assumed,factor_employed_demographic,"
        "factor_unemployed_demographic,factor_inactive_demographic,"
        "factor_labor_force_demographic,factor_working_age_demographic,"
        "factor_population_demographic"
    ).split(","),
    "informalidad.departamentos": (
        "period,dep_code,geographic_employed,geih_domain_status,population,"
        "working_age,labor_force,employed,unemployed,inactive,geih_population,"
        "geih_working_age,geih_labor_force,geih_employed,geih_unemployed,"
        "geih_inactive,factor_geih_population,factor_geih_working_age,"
        "factor_geih_labor_force,factor_geih_employed,factor_geih_unemployed,"
        "factor_geih_inactive,prior_rate,prior_provenance,national_employed,"
        "national_target_rate,provenance,uncertainty_class,informality_rate,"
        "informal_full,formal_full,informal_geih,formal_geih,"
        "outside_geih_population,outside_geih_working_age,"
        "outside_geih_labor_force,outside_geih_employed,"
        "outside_geih_unemployed,outside_geih_inactive,outside_geih_informal,"
        "outside_geih_formal,geih_rate_derived,"
        "informality_complement_rate_assumed_equal,is_official_monthly_rate,"
        "estimation_status,universe_modelled"
    ).split(","),
    "sectorial.departamental": (
        "period,dep_code,sector_code,sector_share,employed_full_sector,"
        "employed_represented_sector_proxy,territorial_prior_status,"
        "national_source_status,annual_anchor_status"
    ).split(","),
    "sectorial.nacional": (
        "period,sector_code,occupied_full,occupied_represented_department_proxy,"
        "share_full,share_represented_department_proxy,source_status,"
        "publication_status"
    ).split(","),
    "labor.nacionales": (
        "period,dep_code,territory_id,territory_name,territory_level,"
        "national_type,is_additive_member,reference_status,"
        "is_official_observation,employed,factor_employed,unemployed,"
        "factor_unemployed,inactive,factor_inactive,labor_force,"
        "factor_labor_force,working_age,factor_working_age,population,"
        "factor_population,unemployment_rate,employment_rate,"
        "participation_rate,factor_reference_status,factor_is_assumed"
    ).split(","),
    "informalidad.nacionales": (
        "period,population,working_age,labor_force,employed,unemployed,"
        "inactive,informal,formal,informality_rate,national_type,"
        "official_geih_national_observation,is_additive_member,"
        "reference_quality,provenance,uncertainty_class,"
        "informality_rate_estimated,difference_to_reconstructed_national_rate_pp,"
        "publication_status"
    ).split(","),
    "labor.ciudades": (
        "city_code,city_name,period,origin,employed,unemployed,inactive,"
        "labor_force,working_age,population,unit_type,dep_code,territory_id,"
        "territory_name,territory_level,is_additive_member,source_status"
    ).split(","),
    "informalidad.ciudades": (
        "city_code,city_name,period,employed_frozen,informality_rate,"
        "informal_estimated,formal_estimated,informality_source_stage,"
        "has_DANE_individual_windows,monthly_observed_DANE,status,"
        "population_signal,employed_signal_labour,source_status,"
        "is_additive_member,population_cnpv_geographic_signal,"
        "employed_cnpv_geographic_signal,informal_cnpv_geographic_signal,"
        "formal_cnpv_geographic_signal,non_additive_urban_signal,"
        "is_official_monthly_rate,is_census_adjusted_capital,publication_status"
    ).split(","),
}

PERIODS = ("2026-07", "2026-08")
CODES = {"dep_code": ("05", "08"), "city_code": ("05", "08")}
SECTORS = ("A", "C")
BOGOTA_MOMENT = datetime(2026, 11, 2, 21, 30, 45, tzinfo=UTC)


def _synthetic(product_id: str) -> pd.DataFrame:
    """Build a small, text-only table with the product's real header."""
    spec = SPECS_BY_ID[product_id]
    columns = EXPECTED_COLUMNS[product_id]
    rows = []
    territories = CODES["dep_code"]
    for period in PERIODS:
        for index, code in enumerate(territories):
            for sector in SECTORS if "sector_code" in columns else ("",):
                rows.append((period, code, sector, len(rows)))
    if spec.split == "rows":
        values = list(spec.row_values.values())
        rows = [(p, "", "", i) for i, p in enumerate(PERIODS * len(values))]
    data = []
    for position, (period, code, sector, n) in enumerate(rows):
        row = {}
        for column in columns:
            if column == "period":
                row[column] = period
            elif column in ("dep_code", "city_code"):
                row[column] = code
            elif column == "sector_code":
                row[column] = sector
            elif column == "national_type":
                values = list(spec.row_values.values())
                row[column] = values[position // len(PERIODS)]
            elif column in ("city_name", "territory_name"):
                row[column] = f"Name {code}"
            else:
                row[column] = f"{100 + n + len(column) / 10:.4f}"
        data.append(row)
    return pd.DataFrame(data, columns=columns)


@pytest.fixture
def products(tmp_path: Path) -> dict[str, Path]:
    folder = tmp_path / "products"
    folder.mkdir()
    out = {}
    for product_id in EXPECTED_COLUMNS:
        path = folder / f"{product_id}.csv"
        _synthetic(product_id).to_csv(path, index=False)
        out[product_id] = path
    return out


def _build(products, tmp_path, **kwargs):
    return build_delivery(
        products,
        tmp_path / "salida",
        cutoff="2026-08",
        mode="delivery",
        now=BOGOTA_MOMENT,
        check_shapes=False,
        **kwargs,
    )


def test_every_product_has_a_header_in_the_test_table():
    assert {s.product_id for s in SPECS} == set(EXPECTED_COLUMNS)


@pytest.mark.parametrize(
    "spec", [s for s in SPECS if s.split == "columns"], ids=lambda s: s.product_id
)
def test_each_original_column_is_assigned_exactly_once(spec):
    assigned = spec.assigned_columns()
    assert len(assigned) == len(set(assigned))
    assert set(assigned) == set(EXPECTED_COLUMNS[spec.product_id])


def test_run_stamp_uses_bogota_time():
    # 21:30:45 UTC is 16:30:45 in Bogota (UTC-5, no daylight saving).
    assert run_stamp(BOGOTA_MOMENT) == "2026-11-02_163045"


def test_folder_name_and_manifest_identify_the_run(products, tmp_path):
    manifest = _build(products, tmp_path, software_version="9.9")
    assert manifest["run_id"] == "2026-11-02_163045_cutoff-2026-08_delivery"
    assert manifest["created_at_bogota"] == "2026-11-02T16:30:45-05:00"
    assert manifest["created_at_utc"] == "2026-11-02T21:30:45+00:00"
    assert manifest["publication_authorized"] is False
    folder = tmp_path / "salida" / manifest["run_id"]
    assert json.loads((folder / "MANIFEST.json").read_text("utf-8")) == manifest


def test_layout_has_both_universes_and_three_domains(products, tmp_path):
    manifest = _build(products, tmp_path)
    folder = tmp_path / "salida" / manifest["run_id"]
    for universe in UNIVERSES:
        for domain in ("labor", "informality", "sectoral"):
            assert any((folder / f"universe_{universe}" / domain).glob("*.csv"))
    assert len(manifest["outputs"]) == 2 * len(SPECS)
    for entry in manifest["outputs"]:
        assert "2026-11-02_163045" in entry["path"]
        assert entry["path"].startswith(f"universe_{entry['universe']}/")


def test_column_split_is_lossless_and_text_exact(products, tmp_path):
    manifest = _build(products, tmp_path)
    folder = tmp_path / "salida" / manifest["run_id"]
    for spec in (s for s in SPECS if s.split == "columns"):
        source = read_text_table(products[spec.product_id])
        for universe in UNIVERSES:
            entry = next(
                e
                for e in manifest["outputs"]
                if e["source_product"] == spec.product_id
                and e["universe"] == universe
            )
            delivered = read_text_table(folder / entry["path"])
            for original, new in entry["original_to_delivered_columns"].items():
                assert delivered[new].tolist() == source[original].tolist(), (
                    spec.product_id,
                    universe,
                    original,
                )


def test_row_split_keeps_each_universe_rows_untouched(products, tmp_path):
    manifest = _build(products, tmp_path)
    folder = tmp_path / "salida" / manifest["run_id"]
    for spec in (s for s in SPECS if s.split == "rows"):
        source = read_text_table(products[spec.product_id])
        for universe, value in spec.row_values.items():
            entry = next(
                e
                for e in manifest["outputs"]
                if e["source_product"] == spec.product_id
                and e["universe"] == universe
            )
            delivered = read_text_table(folder / entry["path"])
            expected = source[source["national_type"] == value]
            assert set(delivered["national_type"]) == {value}
            for column in source.columns:
                assert delivered[column].tolist() == expected[column].tolist()


def test_cities_are_identical_in_both_universes(products, tmp_path):
    manifest = _build(products, tmp_path)
    for product in ("labor.ciudades", "informalidad.ciudades"):
        hashes = {
            e["universe"]: e["sha256"]
            for e in manifest["outputs"]
            if e["source_product"] == product
        }
        # The ``universe`` column differs, so compare without it.
        folder = tmp_path / "salida" / manifest["run_id"]
        frames = {
            e["universe"]: read_text_table(folder / e["path"]).drop(columns="universe")
            for e in manifest["outputs"]
            if e["source_product"] == product
        }
        assert frames["census"].equals(frames["geih"])
        assert set(hashes) == {"census", "geih"}


def test_geih_labor_rates_are_derived_from_represented_counts(products, tmp_path):
    manifest = _build(products, tmp_path)
    folder = tmp_path / "salida" / manifest["run_id"]
    entry = next(
        e
        for e in manifest["outputs"]
        if e["source_product"] == "labor.departamentos" and e["universe"] == "geih"
    )
    assert entry["derived_columns"] == [
        "unemployment_rate",
        "employment_rate",
        "participation_rate",
        "cobertura_geih",
    ]
    frame = pd.read_csv(folder / entry["path"], dtype={"dep_code": str})
    assert (frame.unemployed / frame.labor_force - frame.unemployment_rate).abs().max() < 1e-12
    assert (frame.employed / frame.working_age - frame.employment_rate).abs().max() < 1e-12
    assert (frame.labor_force / frame.working_age - frame.participation_rate).abs().max() < 1e-12


def test_geih_national_reports_gap_against_represented_sum(products, tmp_path):
    manifest = _build(products, tmp_path)
    folder = tmp_path / "salida" / manifest["run_id"]
    national = next(
        e
        for e in manifest["outputs"]
        if e["source_product"] == "labor.nacionales" and e["universe"] == "geih"
    )
    frame = pd.read_csv(folder / national["path"], dtype={"period": str})
    source = pd.read_csv(products["labor.departamentos"], dtype={"period": str})
    expected = source.groupby("period")["employed_represented"].sum()
    for _, row in frame.iterrows():
        total = expected[row["period"]]
        assert row["represented_sum_employed"] == pytest.approx(total)
        assert row["gap_published_minus_sum_employed"] == pytest.approx(
            row["employed"] - total
        )


def test_geih_sector_share_adds_to_one_within_each_department(products, tmp_path):
    manifest = _build(products, tmp_path)
    folder = tmp_path / "salida" / manifest["run_id"]
    entry = next(
        e
        for e in manifest["outputs"]
        if e["source_product"] == "sectorial.departamental" and e["universe"] == "geih"
    )
    frame = pd.read_csv(folder / entry["path"], dtype={"dep_code": str})
    sums = frame.groupby(["period", "dep_code"])["sector_share"].sum()
    assert (sums - 1).abs().max() < 1e-12


def test_never_overwrites_a_delivery(products, tmp_path):
    _build(products, tmp_path)
    with pytest.raises(FileExistsError):
        _build(products, tmp_path)


def test_rejects_unknown_mode_missing_product_and_changed_columns(
    products, tmp_path
):
    with pytest.raises(ValueError, match="mode"):
        build_delivery(
            products, tmp_path / "s1", cutoff="2026-08", mode="otro",
            check_shapes=False,
        )
    partial = {k: v for k, v in products.items() if k != "labor.ciudades"}
    with pytest.raises(ValueError, match="Missing products"):
        _build(partial, tmp_path)
    broken = pd.read_csv(products["sectorial.nacional"], dtype=str)
    broken["surprise"] = "x"
    broken.to_csv(products["sectorial.nacional"], index=False)
    with pytest.raises(ValueError, match="unassigned"):
        _build(products, tmp_path)


def test_rejects_unexpected_row_counts_by_default(products, tmp_path):
    with pytest.raises(ValueError, match="rows, expected"):
        build_delivery(
            products, tmp_path / "salida", cutoff="2026-08", mode="delivery",
            now=BOGOTA_MOMENT,
        )


def test_excel_keeps_codes_as_text_and_numbers_numeric(products, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    manifest = _build(products, tmp_path, excel=True)
    folder = tmp_path / "salida" / manifest["run_id"]
    entry = next(
        e
        for e in manifest["outputs"]
        if e["path"].endswith(".xlsx")
        and e["source_product"] == "labor.departamentos"
        and e["universe"] == "census"
    )
    sheet = openpyxl.load_workbook(folder / entry["path"], read_only=True)["datos"]
    rows = list(sheet.iter_rows(values_only=True))
    header, first = rows[0], rows[1]
    assert first[header.index("dep_code")] == "05"
    assert isinstance(first[header.index("employed")], float)
    assert first[header.index("period")] == "2026-07"


def test_modes_are_the_documented_ones():
    assert MODES == {"delivery", "anchored", "total", "verification"}


def _frame(rows):
    return pd.DataFrame(rows, dtype=str).fillna("")


def test_coverage_report_accepts_a_complete_table_and_flags_gaps():
    from icml.delivery.verify import coverage_report

    months = ["2026-01", "2026-02"]
    full = _frame([{"dep_code": str(d), "period": m, "x": "1"} for d in range(33) for m in months])
    assert coverage_report(full, level="departments", months=months)["complete"]
    short = full[full.dep_code != "7"]
    report = coverage_report(short, level="departments", months=months)
    assert not report["complete"] and report["missing_keys"] == 2 and report["territories"] == 32
    shifted = full.assign(period=full.period.replace({"2026-02": "2026-03"}))
    assert not coverage_report(shifted, level="departments", months=months)["complete"]
    duplicated = _frame([*full.to_dict("records"), full.iloc[0].to_dict()])
    assert coverage_report(duplicated, level="departments", months=months)["duplicated_keys"] == 1


def test_a_blank_is_only_valid_where_the_geih_does_not_represent_the_territory():
    from icml.delivery.verify import coverage_report

    months = ["2026-01"]
    rows = [{"dep_code": str(d), "period": "2026-01", "rate": "0.1", "cobertura_geih": "COMPLETA"} for d in range(33)]
    ok = _frame(rows)
    ok.loc[0, ["rate", "cobertura_geih"]] = ["", "SIN_REPRESENTACION"]
    report = coverage_report(ok, level="departments", months=months)
    assert report["complete"] and report["blank_rows_explained_by_no_representation"] == 1
    bad = _frame(rows)
    bad.loc[0, "rate"] = ""  # blank although the GEIH says it represents the territory
    report = coverage_report(bad, level="departments", months=months)
    assert not report["complete"] and report["blank_rows_unexplained"] == 1


def test_sectoral_and_national_coverage_expectations():
    from icml.delivery.verify import coverage_report

    months = ["2026-01", "2026-02"]
    national = _frame([{"period": m, "x": "1"} for m in months])
    assert coverage_report(national, level="national", months=months)["complete"]
    sectoral = _frame([{"sector_code": f"S{s}", "period": m, "x": "1"} for s in range(15) for m in months])
    assert coverage_report(sectoral, level="national", months=months, sectors=15)["complete"]
    assert not coverage_report(sectoral.iloc[:-1], level="national", months=months, sectors=15)["complete"]


# ----------------------------------------------------------- simple files


def _simple(products, tmp_path, **kwargs):
    from icml.delivery.simple import build_simple

    manifest = _build(products, tmp_path)
    folder = tmp_path / "salida" / manifest["run_id"]
    result = build_simple(folder, **kwargs)
    return manifest, folder, result


def _simple_file(result, universe, domain, level, suffix=".csv"):
    entry = next(
        e for e in result["files"]
        if (e["universe"], e["domain"], e["level"]) == (universe, domain, level)
    )
    path = next(f for f in entry["files"] if f.endswith(suffix))
    return Path(result["folder"]) / path, entry


def test_delivery_and_file_names_use_a_single_underscore(products, tmp_path):
    manifest, folder, result = _simple(products, tmp_path, excel=False)
    assert "__" not in manifest["run_id"]
    for entry in manifest["outputs"]:
        assert "__" not in Path(entry["path"]).name
    for entry in result["files"]:
        assert all("__" not in Path(f).name for f in entry["files"])
    assert "__" not in Path(result["folder"]).name


def test_simple_laboral_departments_have_only_the_labor_columns(products, tmp_path):
    _, _, result = _simple(products, tmp_path, excel=False)
    path, entry = _simple_file(result, "census", "labor", "departments")
    assert entry["columns"] == [
        "Date", "Year", "Month", "Department", "Code", "Employed", "Unemployed", "Inactive",
        "LaborForce", "WorkingAge", "Population", "UnemploymentRate", "EmploymentRate", "ParticipationRate",
    ]
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    assert list(frame.columns) == entry["columns"]
    assert set(frame.Code) == {"05", "08"}  # two-digit codes, leading zero kept
    assert set(frame.Department) == {"Antioquia", "Atlántico"}
    assert len(frame) == 4 and frame.Date.tolist()[:2] == ["2026-07-01", "2026-08-01"]  # by code, then date
    assert frame["Year"].tolist()[:2] == ["2026", "2026"] and frame["Month"].tolist()[:2] == ["7", "8"]


def test_simple_files_match_the_full_delivery_value_for_value(products, tmp_path):
    manifest, folder, result = _simple(products, tmp_path, excel=False)
    for universe in ("census", "geih"):
        full_entry = next(
            e for e in manifest["outputs"]
            if (e["universe"], e["source_product"]) == (universe, "labor.departamentos") and e["path"].endswith(".csv")
        )
        full = read_text_table(folder / full_entry["path"])
        path, _ = _simple_file(result, universe, "labor", "departments")
        simple = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        merged = simple.merge(
            full.assign(Code=full.dep_code.str.zfill(2), Date=full.period + "-01"),
            on=["Code", "Date"],
        )
        assert len(merged) == len(full)
        for new, old in (("Employed", "employed"), ("LaborForce", "labor_force"), ("UnemploymentRate", "unemployment_rate")):
            assert merged[new].tolist() == merged[old].tolist()


def test_simple_city_labor_gets_its_rates_and_informality_its_own_columns(products, tmp_path):
    _, _, result = _simple(products, tmp_path, excel=False)
    path, entry = _simple_file(result, "geih", "labor", "cities")
    assert entry["columns"][:5] == ["Date", "Year", "Month", "City", "Code"] and entry["columns"][-3:] == ["UnemploymentRate", "EmploymentRate", "ParticipationRate"]
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype={"Code": str})
    assert (frame.Unemployed / frame.LaborForce - frame.UnemploymentRate).abs().max() < 1e-12
    _, inf = _simple_file(result, "census", "informality", "cities")
    assert inf["columns"] == ["Date", "Year", "Month", "City", "Code", "Employed", "Informal", "Formal", "InformalityRate"]
    _, nat = _simple_file(result, "census", "informality", "national")
    assert nat["columns"] == ["Date", "Year", "Month", "Population", "WorkingAge", "LaborForce", "Employed", "Unemployed", "Inactive", "Informal", "Formal", "InformalityRate"]


def test_simple_sectorial_and_national_columns(products, tmp_path):
    _, _, result = _simple(products, tmp_path, excel=False)
    _, dept = _simple_file(result, "geih", "sectoral", "departments")
    assert dept["columns"] == ["Date", "Year", "Month", "Department", "Code", "Sector", "Employed", "Share"]
    _, nat = _simple_file(result, "census", "sectoral", "national")
    assert nat["columns"] == ["Date", "Year", "Month", "Sector", "Employed", "Share"]
    _, labor = _simple_file(result, "census", "labor", "national")
    assert labor["columns"][:3] == ["Date", "Year", "Month"] and "Department" not in labor["columns"] and "Code" not in labor["columns"]


def test_simple_files_have_no_traceability_columns(products, tmp_path):
    _, _, result = _simple(products, tmp_path, excel=False)
    forbidden = {"universe", "source", "provenance", "cobertura_geih", "national_type", "factor_employed"}
    for entry in result["files"]:
        assert not forbidden & set(entry["columns"]), entry["columns"]


def test_simple_excel_has_a_real_date_year_and_month_as_numbers_and_codes_as_text(products, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    _, _, result = _simple(products, tmp_path, excel=True)
    path, _ = _simple_file(result, "census", "labor", "departments", ".xlsx")
    rows = list(openpyxl.load_workbook(path, read_only=True)["datos"].iter_rows(values_only=True))
    header, first = rows[0], rows[1]
    import datetime

    assert first[header.index("Code")] == "05"
    assert first[header.index("Date")] == datetime.datetime(2026, 7, 1)  # a real Excel date
    assert first[header.index("Year")] == 2026 and first[header.index("Month")] == 7
    assert isinstance(first[header.index("Employed")], float)


def test_simple_never_overwrites(products, tmp_path):
    from icml.delivery.simple import build_simple

    manifest, folder, _ = _simple(products, tmp_path, excel=False)
    with pytest.raises(FileExistsError):
        build_simple(folder)


# ------------------------------------------------------------------ verify_delivery on a synthetic delivery


def test_verify_delivery_runs_its_checks_on_a_synthetic_delivery_and_detects_tampering(products, tmp_path):
    from icml.delivery.verify import verify_delivery

    manifest = _build(products, tmp_path)
    folder = tmp_path / "salida" / manifest["run_id"]
    report = verify_delivery(folder)
    assert report["status"] in {"PASS", "FAIL"} and len(report["checks"]) >= 36
    assert (folder / "VERIFICATION.json").is_file()
    hash_checks = [c for c in report["checks"] if "hash" in c["check"].lower() or "sha" in c["check"].lower()]
    assert hash_checks and all(c["passed"] for c in hash_checks)
    # Tamper with one delivered file: the hash gate must fail and the status must not be PASS.
    target = next(p for p in folder.rglob("*.csv"))
    target.write_bytes(target.read_bytes() + b"x")
    tampered = verify_delivery(folder)
    assert tampered["status"] != "PASS"
    assert any(not c["passed"] for c in tampered["checks"])
