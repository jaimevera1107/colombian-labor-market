"""H22 GEIH source intake with portable, read-only XLSX cached-cell extraction.

Never re-estimates models, changes frozen input, or publishes a new vintage.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from icml.domain.cutoff import FROZEN_CUTOFF, next_month, trailing_window_label

ROW_MAP = {
    "participation_rate_pct": 15,
    "employment_rate_pct": 16,
    "unemployment_rate_pct": 17,
    "population_thousands": 23,
    "working_age_thousands": 24,
    "labor_force_thousands": 25,
    "employed_thousands": 26,
    "unemployed_thousands": 27,
    "inactive_thousands": 28,
}
DOMAINS = {"DANE_NACIONAL": "Total nacional", "DANE_13_CIUDADES": "Total 13 ciudades A.M."}
SEPTEMBER_OFFICIAL = {
    "DANE_NACIONAL": {"participation_rate_pct": 63.8, "employment_rate_pct": 58.7, "unemployment_rate_pct": 8.0},
    "DANE_13_CIUDADES": {"participation_rate_pct": 66.1, "employment_rate_pct": 60.6, "unemployment_rate_pct": 8.3},
}
SOURCE_URL = "https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIH-sep2026.xlsx"
SOURCE_WEBPAGE = "https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo"
LAST_FROZEN = FROZEN_CUTOFF


def _digest(file: Path) -> str:
    h=hashlib.sha256()
    with file.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def excel_column(number: int) -> str:
    """Excel 1-based column number -> letters."""
    if number < 1:
        raise ValueError("Column must be positive")
    s = ""
    while number:
        number, r = divmod(number-1,26)
        s = chr(65+r)+s
    return s


def monthly_column(period: str) -> str:
    year,month=map(int,period.split("-"))
    if not (2001 <= year <= 2100 and 1<=month<=12):
        raise ValueError("GEIH annex monthly-series period must be >= 2001")
    return excel_column(2+(year-2001)*12+(month-1))


def validate_observation(values: dict, domain: str, period: str) -> list[str]:
    """Source amounts in thousands and rates in percent, with published rounding."""
    warnings=[]
    for field in ROW_MAP:
        v=values.get(field)
        if not isinstance(v,(int,float)) or not (float('-inf') < v < float('inf')):
            raise ValueError(f"{domain} {period}: missing/non-finite {field}")
        if v < 0:
            raise ValueError(f"{domain} {period}: negative {field}")
    for field in ["participation_rate_pct", "employment_rate_pct", "unemployment_rate_pct"]:
        if values[field] > 100:
            raise ValueError(f"{domain}: invalid rate {field}")
    def diff(a,b,c):
        return abs(values[a]-values[b]-values[c])
    if diff("labor_force_thousands","employed_thousands","unemployed_thousands") > .006:
        raise ValueError(f"{domain}: labor-force identity in thousands broken")
    if diff("working_age_thousands","labor_force_thousands","inactive_thousands") > .006:
        raise ValueError(f"{domain}: working-age identity in thousands broken")
    checks={
        "participation_rate_pct":100*values["labor_force_thousands"]/values["working_age_thousands"],
        "employment_rate_pct":100*values["employed_thousands"]/values["working_age_thousands"],
        "unemployment_rate_pct":100*values["unemployed_thousands"]/values["labor_force_thousands"],
    }
    for field,actual in checks.items():
        if abs(values[field]-actual)>.02:
            raise ValueError(f"{domain}: {field} inconsistent with levels")
    if period == "2026-09":
        for field, official in SEPTEMBER_OFFICIAL[domain].items():
            if abs(values[field]-official)>.15:
                raise ValueError(f"{domain}: {field} does not agree with published September bulletin")
    return warnings


def _read_xlsx_cells(path: Path, sheet_names: list[str], cell_names: set[str]) -> dict[str,dict[str,object]]:
    """Read *cached scalar values* from named sheets using only Python stdlib.

    This restricted parser intentionally rejects absent/formula-only cells. It
    does not recalculate spreadsheets, follow external links, or alter workbooks.
    """
    import posixpath
    import xml.etree.ElementTree as ET
    from zipfile import ZipFile, BadZipFile

    MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    PACK = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    if path.stat().st_size > 60_000_000:
        raise ValueError("Unusually large XLSX; refuse without manual audit")
    with ZipFile(path) as z:
        names=set(z.namelist())
        for f in ("xl/workbook.xml","xl/_rels/workbook.xml.rels"):
            if f not in names: raise ValueError(f"Invalid XLSX: missing {f}")
        wb=ET.fromstring(z.read("xl/workbook.xml"))
        relations=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        lookup={r.get('Id'):r.get('Target') for r in relations.findall(PACK+'Relationship')}
        sheets={s.get('name'): s.get(REL+'id') for s in wb.findall('.//'+MAIN+'sheet')}
        shared=[]
        if 'xl/sharedStrings.xml' in names:
            raw=z.read('xl/sharedStrings.xml')
            if len(raw)>40_000_000: raise ValueError('Shared strings too large')
            tree=ET.fromstring(raw)
            for si in tree.findall(MAIN+'si'):
                shared.append(''.join(x.text or '' for x in si.iter(MAIN+'t')))
        out={}
        for sheet in sheet_names:
            rid=sheets.get(sheet)
            if not rid: raise ValueError(f"Missing official sheet {sheet}")
            target=lookup.get(rid)
            if not target: raise ValueError(f"No relationship for {sheet}")
            member=posixpath.normpath(target.lstrip('/') if target.startswith('/')
                                    else posixpath.join('xl',target))
            if not member.startswith('xl/worksheets/') or member not in names:
                raise ValueError(f"Unsafe/unexpected sheet target {member}")
            content=z.read(member)
            if len(content)>100_000_000:
                raise ValueError('Worksheet exceeds safe inspection size')
            tree=ET.fromstring(content)
            found={}
            for cell in tree.iter(MAIN+'c'):
                ref=cell.get('r')
                if ref not in cell_names: continue
                typ=cell.get('t')
                value=cell.find(MAIN+'v')
                if typ=='inlineStr':
                    found[ref]=''.join(el.text or '' for el in cell.iter(MAIN+'t'))
                elif value is None or value.text is None:
                    raise ValueError(f"Cached cell value missing: {sheet}!{ref}")
                elif typ=='s':
                    found[ref]=shared[int(value.text)]
                elif typ in ('str','e'):
                    if typ=='e': raise ValueError(f"Cell formula error: {sheet}!{ref}")
                    found[ref]=value.text
                else:
                    found[ref]=float(value.text)
            out[sheet]=found
        return out


def inspect_annex(path: Path, periods: list[str]) -> list[dict]:
    """Read DANE 2001+ monthly-series cached values; fail closed on drift."""
    expected_months=['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
    columns={period:monthly_column(period) for period in periods}
    needed={f"{col}{row}" for col in columns.values() for row in [13,*ROW_MAP.values()]}
    extracted=_read_xlsx_cells(path,list(DOMAINS.values()),needed)
    observations=[]
    for domain,sheet in DOMAINS.items():
        cells=extracted[sheet]
        for period,col in columns.items():
            exp=expected_months[int(period[5:])-1]
            seen=cells.get(f"{col}13")
            if str(seen).strip()!=exp:
                raise ValueError(f"{sheet} {period}: month header expected {exp}, observed {seen}")
            values={field:cells.get(f"{col}{row}") for field,row in ROW_MAP.items()}
            if any(v is None for v in values.values()):
                raise ValueError(f"{sheet} {period}: missing expected cached monthly values")
            values={k:float(v) for k,v in values.items()}
            validate_observation(values,domain,period)
            observations.append({"period":period,"domain":domain,"source_sheet":sheet,**values})
    return observations

def prepare_intake(root: Path, output: Path, period: str, labor_annex: Path | None,
                   previous_annex: Path | None = None) -> dict:
    """Create immutable, auditable source-only staging; NEVER rewrite ICML products."""
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    frozen=root / "datos/2_procesamiento/productos_congelados/pruebas_calidad/nacionales.csv"
    if not frozen.is_file():
        raise FileNotFoundError("ICML H21 frozen national product missing")
    baseline_hash=_digest(frozen)
    from datetime import date
    try:
        check=date.fromisoformat(period+'-01')
    except ValueError as exc:
        raise ValueError(f"Invalid monthly period: {period}") from exc
    registered = next_month(FROZEN_CUTOFF)
    if period not in (FROZEN_CUTOFF, registered):
        raise ValueError(
            f"H22 registered period is {registered}; "
            f"{FROZEN_CUTOFF} only for regression diagnostics")
    report={
        "stage":"H22_OFFICIAL_SOURCE_INTAKE", "target_period":period,
        "frozen_last_period":LAST_FROZEN,
        "input_official_page":SOURCE_WEBPAGE, "official_annex_url":SOURCE_URL,
        "official_geih_release_date":"2026-10-30", "informality_reference_latest":trailing_window_label(FROZEN_CUTOFF),
        "frozen_nationals_sha256":baseline_hash,
        "mode":"READ_ONLY_STAGE_NEVER_PUBLISH", "canonical_updated":False,
        "monthly_update_requires_both_sources": True,
        "source_pair_rule":"GEIH month == ending month of 3-month Informal Employment and Social Security annex",
        "social_security_required_window":trailing_window_label(period),
        "matching_social_security_annex_verified": False,
        "full_monthly_update_eligible": False,
        "new_vintage_publication_permitted": False,
        "full_update_blockers":["MISSING_VERIFIED_SAME_MONTH_SOCIAL_SECURITY_ANNEX"],
        "geih_labor_annex_received":False,"labor_domains_available":[],
        "monthly_model_updated":False,"full_icml_pipeline_ran":False,
        "unavailable_inputs":[],"revision_alerts":[],
        "source_sha256":None,"reference_rows":0,
        "generated_utc":datetime.now(timezone.utc).isoformat(),
    }
    rows=[]
    revision_rows=[]
    if labor_annex is None or not labor_annex.is_file():
        report["status"]="BLOCKED_OFFICIAL_XLSX_NOT_AVAILABLE_LOCALLY"
        report["unavailable_inputs"].append("GEIH September 2026 XLSX source bytes")
    else:
        try:
            if not labor_annex.name.lower().endswith('.xlsx'):
                raise ValueError("GEIH source must be .xlsx")
            # No workbook content is copied into the frozen root.
            rows=inspect_annex(labor_annex,[period])
            report["geih_labor_annex_received"]=True
            report["source_sha256"]=_digest(labor_annex)
            report["labor_domains_available"]=list(DOMAINS)
            report["reference_rows"]=len(rows)
            if previous_annex is not None:
                comparison_periods=["2025-09","2026-01","2026-02","2026-03","2026-04",
                                    "2026-05","2026-06","2026-07","2026-08"]
                original=inspect_annex(previous_annex,comparison_periods)
                current=inspect_annex(labor_annex,comparison_periods)
                before={(r['period'],r['domain']):r for r in original}
                for newer in current:
                    older=before[newer['period'],newer['domain']]
                    for field in ROW_MAP:
                        delta=newer[field]-older[field]
                        threshold=1e-6 if field.endswith('_pct') else .001
                        if abs(delta)>threshold:
                            revision_rows.append({"period":newer['period'],"domain":newer['domain'],
                                "field":field,"previous":older[field],"new":newer[field],"delta":delta,
                                "disposition":"REQUIRES_SEPARATE_OFFICIAL_REVISION_APPROVAL"})
                report["previous_annex_sha256"]=_digest(previous_annex)
            report["revision_alerts"]=revision_rows[:20]
            report["revision_count"]=len(revision_rows)
            report["status"]="STAGED_GEIH_ONLY_FULL_UPDATE_BLOCKED_PENDING_MATCHING_SOCIAL_SECURITY"
            report["unavailable_inputs"].append("33-department candidate, cities and national complete-universe model output")
            report["unavailable_inputs"].append("2026-07/2026-09 informal employment annex")
        except Exception as exc:
            report["status"]="BLOCKED_SOURCE_VALIDATION_ERROR"
            report["validation_error"]="{}: {}".format(type(exc).__name__,str(exc))
            report["unavailable_inputs"].append("source not validated; no rows staged")
            rows=[]
            revision_rows=[]
    output.mkdir(parents=True,exist_ok=False)
    def dump_csv(path: Path, entries:list, columns:list):
        with path.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=columns)
            writer.writeheader();writer.writerows(entries)
    dump_csv(output/'22_observaciones_laborales_geih.csv',rows,
             ['period','domain','source_sheet']+list(ROW_MAP))
    dump_csv(output/'22_revision_official_overlap.csv',revision_rows,
             ['period','domain','field','previous','new','delta','disposition'])
    report['frozen_nationals_sha256_unchanged']=(_digest(frozen)==baseline_hash)
    (output/'22_fuentes_y_puerta.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
    return report
