"""Sectoral H10: genuine DANE calendar-month estimates, no rolling-window conversion.

A 3-month moving window is NOT a monthly observation and is rejected as a
month-specific anchor.  The original CIIU4 monthly source has 13 reported groups
(plus `No informa`), with mining and utilities combined.  It MUST NOT be
relabelled a full 14-branch observation without separately observed evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from icml.domain.cutoff import (
    ACTIVE_CUTOFF,
    SECTORAL_MONTHS,
    SECTORAL_FIRST_MONTH,
    expected_month_count,
    month_periods,
)

# Explicit row layout of the original DANE Aug-2026 annex, sheet
# "Ocupados TN_T13_rama", beginning at source row 18.
MONTHLY_GROUPS = (
    'A', 'B_D_E_COMBINED', 'C', 'F', 'G', 'I', 'H', 'J', 'K', 'L',
    'M_N', 'O_P_Q', 'R_S_T_U',
)
REQUIRED_FINAL_14 = (
    'A', 'B', 'C', 'D_E', 'F', 'G', 'H', 'I', 'J', 'K', 'L',
    'M_N', 'O_P_Q', 'R_S_T_U',
)
WINDOWS = {'monthly_direct': 1, 'moving_quarter': 3, 'annual': 12}
MONTHS_ES = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago',
             'Sep', 'Oct', 'Nov', 'Dic')


def ensure_direct_monthly(source_kind: str, window_months: int) -> None:
    """Prevent false promotion of moving windows/annual data to monthly facts."""
    if source_kind != 'monthly_direct' or window_months != 1:
        raise ValueError('BLOQUEADO: no es una observación mensual directa; '
                         'un trimestre móvil o anual solo puede ser restricción '+
                         'de su ventana, no el valor de un mes')


def ingest_dane_workbook(workbook: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Extract 2015-01..2026-08 with artifact_tool (optional source ingestion tool).

    The runtime/model itself uses only the normalized versioned CSV, not Excel.
    """
    try:
        from artifact_tool import Blob, SpreadsheetFile
    except ImportError as exc:
        raise RuntimeError('Source extraction requires artifact_tool; use the '+
                           'versioned normalized CSV for subsequent runs') from exc
    ensure_direct_monthly('monthly_direct', 1)
    wb = SpreadsheetFile.import_xlsx(Blob.load(str(workbook)))
    sheet = wb.worksheets.get_item('Ocupados TN_T13_rama')
    rows = sheet.get_range('A13:EK30').values
    if len(rows) != 18 or len(rows[0]) != 141:
        raise ValueError('DANE monthly sheet shape changed; inspect source version')
    source = hashlib.sha256(workbook.read_bytes()).hexdigest()
    records, controls = [], []
    for i in range(SECTORAL_MONTHS):
        idx = i + 1
        year, month = 2015 + i // 12, i % 12 + 1
        if str(rows[1][idx]).strip().title() != MONTHS_ES[month - 1]:
            raise ValueError(f'DANE calendar-month header mismatch at {year}-{month:02}')
        if month == 1 and int(rows[0][idx]) != year:
            raise ValueError(f'DANE calendar-year header mismatch at {year}')
        period = f'{year}-{month:02}'
        total, no_info = float(rows[3][idx])*1000, float(rows[4][idx])*1000
        reported = []
        for j, code in enumerate(MONTHLY_GROUPS):
            value = float(rows[5 + j][idx]) * 1000
            if not np.isfinite(value) or value < 0:
                raise ValueError(f'Invalid official monthly count: {period} {code}')
            reported.append(value)
            records.append(dict(period=period, sector_code=code,
                sector_name=rows[5 + j][0], employed_persons=value,
                domain='total_nacional_GEIH', temporal_support='calendar_month',
                window_months=1, observation_status='DANE_PUBLISHED_MONTHLY_ESTIMATE',
                classification='CIIU_Rev4_AC', source_sha256=source,
                source_sheet='Ocupados TN_T13_rama',
                original_unit='thousands_of_persons',
                missing_final_14_split=code == 'B_D_E_COMBINED'))
        residual = total - no_info - sum(reported)
        if abs(residual) > 10:
            raise ValueError(f'Official monthly sum fails at {period}: {residual} people')
        controls.append(dict(period=period, domain='total_nacional_GEIH',
             occupied_official_persons=total, no_informa_persons=no_info,
             sum_13_groups_persons=sum(reported), rounding_residual_persons=residual,
             window_months=1, temporal_support='calendar_month',
             branch_status='13_GROUPS_B_D_E_COMBINED__NOT_14', source_sha256=source))
    return pd.DataFrame(records), pd.DataFrame(controls), {
        'sha256':source,'source_file':workbook.name,'sheet':'Ocupados TN_T13_rama',
        'direct_months':expected_month_count(SECTORAL_FIRST_MONTH),'reported_sector_groups':13,'final_required_groups':14,
        'first_month':SECTORAL_FIRST_MONTH,'last_month':ACTIVE_CUTOFF,
        'mining_and_utilities':'B_D_E_COMBINED',
        'no_informa':'separately published, NOT a 14th sector',
        'unit':'published in thousands; converted to persons',
        'window_months':1,'source_domain':'DANE GEIH total nacional',
        'not_a_monthly_split':'B and D_E cannot be independently extracted from this sheet',
        'provenance':'official DANE monthly annex, not rolling 3-month rows',
    }


def compare_monthly_domains(totals: pd.DataFrame, national: Path) -> pd.DataFrame:
    """Diagnostics only; never silently force monthly DANE to frozen ICML."""
    df = pd.read_csv(national, encoding='utf-8-sig')
    if not {'period','national_type','employed'} <= set(df.columns):
        raise ValueError('Frozen national base is missing required columns')
    frame = totals.merge(df[['period','national_type','employed']],on='period', how='left',validate='one_to_many')
    frame['diff_official_minus_icml_persons'] = frame['occupied_official_persons'] - frame['employed']
    frame['diff_percent'] = 100*frame['diff_official_minus_icml_persons']/frame['employed']
    frame['comment'] = ('DIAGNOSTIC_ONLY: confirm universe, version, source and month; '
        'official national GEIH is not by definition ICML census complete')
    return frame.sort_values(['period','national_type']).reset_index(drop=True)


def reconcile_sector_matrix(prior: np.ndarray, occupied_rows: np.ndarray,
                            sector_columns: np.ndarray, *, tolerance=1e-8,
                            max_iterations=10000) -> np.ndarray:
    """Constrained nonnegative RAS in persons with compatible margins.

    Unlike the old implementation, no final branch overwrite is permitted.
    Not for monthly source ingestion; only a future department-sector estimate.
    """
    p = np.asarray(prior, dtype=float)
    rows = np.asarray(occupied_rows, dtype=float)
    cols = np.asarray(sector_columns, dtype=float)
    if p.ndim != 2 or rows.shape != (p.shape[0],) or cols.shape != (p.shape[1],):
        raise ValueError('Incompatible sector matrix and margin dimensions')
    if (not np.all(np.isfinite(p)) or not np.all(np.isfinite(rows)) or
        not np.all(np.isfinite(cols)) or np.any(p < 0) or np.any(rows < 0) or np.any(cols < 0)):
        raise ValueError('Margins and matrix must be finite and nonnegative')
    scale = max(1, float(rows.sum()), float(cols.sum()))
    if abs(rows.sum() - cols.sum()) > tolerance*scale:
        raise ValueError('MARGENES_INCOMPATIBLES: row totals and column totals differ')
    if not np.any(rows) and not np.any(cols):
        return np.zeros_like(p)
    if np.any((rows > 0) & ~(p > 0).any(axis=1)) or np.any((cols > 0) & ~(p > 0).any(axis=0)):
        raise ValueError('STRUCTURAL_ZERO: positive margin with no supporting cells')
    out = p.copy()
    # Remove structurally zero margins from active support; never add fictitious persons.
    out[rows == 0,:] = 0
    out[:,cols == 0] = 0
    for _ in range(max_iterations):
        rsum = out.sum(axis=1)
        if np.any((rows > 0) & (rsum == 0)):
            raise ValueError('STRUCTURAL_ZERO: infeasible row')
        out *= np.divide(rows, rsum, out=np.zeros_like(rows), where=rsum>0)[:,None]
        csum=out.sum(axis=0)
        if np.any((cols > 0) & (csum == 0)):
            raise ValueError('STRUCTURAL_ZERO: infeasible column')
        out *= np.divide(cols,csum,out=np.zeros_like(cols),where=csum>0)[None,:]
        if (np.max(np.abs(out.sum(axis=1)-rows)) <= tolerance*scale and
            np.max(np.abs(out.sum(axis=0)-cols)) <= tolerance*scale):
            return out
    raise ValueError('RAS_DID_NOT_CONVERGE: incompatible support or too many iterations')


def audit_legacy_moving_windows(totals: pd.DataFrame, legacy_path: Path) -> pd.DataFrame:
    """Expose period mismatch; three-month averages are NEVER monthly observations."""
    old = pd.read_csv(legacy_path)
    if not {'date','total_persons'} <= set(old.columns):
        raise ValueError('Unexpected legacy moving-window audit format')
    old['period'] = old['date'].astype(str).str[:7]
    base = totals[['period','occupied_official_persons']].copy()
    # Rolling operation ONLY in an explicit audit of the old THREE-MONTH definition.
    # Do not use this value for monthly estimation or as a monthly anchor.
    base['check_only_rolling_3m_of_true_monthly_persons'] = base.occupied_official_persons.rolling(3).mean()
    out = old[['period','total_persons']].merge(base, on='period', validate='one_to_one')
    out['incorrect_month_end_comparison_pct'] = 100*(out.total_persons-out.occupied_official_persons)/out.occupied_official_persons
    out['correct_window_validation_difference_persons'] = out.total_persons-out.check_only_rolling_3m_of_true_monthly_persons
    out['legacy_window_months'] = 3
    out['allowed_as_direct_monthly_anchor'] = False
    return out


def read_normalized_monthly(observations: Path, totals_path: Path,
                            workbook: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Reaudit a frozen source CSV without an Excel parsing dependency.

    The official original workbook remains immutable, and may be verified by hash.
    """
    monthly = pd.read_csv(observations, keep_default_na=False)
    totals = pd.read_csv(totals_path, keep_default_na=False)
    if len(monthly) != SECTORAL_MONTHS*13 or len(totals) != SECTORAL_MONTHS:
        raise ValueError('Normalized source cardinality incorrect')
    if (set(monthly.sector_code) != set(MONTHLY_GROUPS) or
        set(monthly.period) != set(totals.period) or
        len(monthly[['period','sector_code']].drop_duplicates()) != len(monthly)):
        raise ValueError('Normalized source categories, months or keys inconsistent')
    expected = month_periods(SECTORAL_FIRST_MONTH).strftime('%Y-%m')
    if set(totals.period) != set(expected):
        raise ValueError(f'Not all {SECTORAL_MONTHS} source months included')
    for x in (monthly, totals):
        if not (x.window_months.astype(int) == 1).all():
            raise ValueError('Moving-window observations cannot be monthly anchors')
        if x.source_sha256.nunique() != 1:
            raise ValueError('Missing unique input workbook SHA-256')
    source_hash = str(monthly.source_sha256.iloc[0])
    if source_hash != str(totals.source_sha256.iloc[0]):
        raise ValueError('Source workbook hashes disagree')
    if workbook is not None and hashlib.sha256(Path(workbook).read_bytes()).hexdigest() != source_hash:
        raise ValueError('Input workbook has changed since normalized snapshot')
    if (monthly.employed_persons.astype(float) < 0).any():
        raise ValueError('Negative observed sector counts')
    check = (totals.occupied_official_persons.astype(float)
             - totals.no_informa_persons.astype(float)
             - monthly.groupby('period').employed_persons.sum().reindex(totals.period).to_numpy())
    if check.abs().max() > 10:
        raise ValueError('Snapshot does not reproduce official monthly totals')
    catalog = {'sha256':source_hash, 'source_file':Path(workbook).name if workbook else 'original annex',
        'sheet':'Ocupados TN_T13_rama', 'direct_months':expected_month_count(SECTORAL_FIRST_MONTH), 'reported_sector_groups':13,
        'final_required_groups':14, 'first_month':SECTORAL_FIRST_MONTH, 'last_month':ACTIVE_CUTOFF,
        'mining_and_utilities':'B_D_E_COMBINED',
        'no_informa':'separate residual, not a sector', 'unit':'persons', 'window_months':1,
        'source_domain':'DANE GEIH total nacional',
        'not_a_monthly_split':'B and D_E not separately available in this snapshot',
        'provenance':'normalized immutable DANE monthly source, original hash verified when supplied'}
    return monthly, totals, catalog


def run(workbook: Path | None, national: Path, output: Path,
        legacy_path: Path | None = None, *, observations_csv: Path | None = None,
        totals_csv: Path | None = None) -> dict:
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    if observations_csv is not None or totals_csv is not None:
        if observations_csv is None or totals_csv is None:
            raise ValueError('Provide both observations and totals normalized CSV')
        monthly, totals, catalog = read_normalized_monthly(observations_csv, totals_csv, workbook)
    elif workbook is not None:
        monthly, totals, catalog = ingest_dane_workbook(Path(workbook))
    else:
        raise ValueError('Provide --workbook or both normalized CSV source files')
    comparison = compare_monthly_domains(totals, Path(national))
    monthly.to_csv(output/'10_observaciones_oficiales_mensuales_13_grupos.csv',index=False,float_format='%.10f',lineterminator='\n')
    totals.to_csv(output/'10_totales_oficiales_mensuales.csv',index=False,float_format='%.10f',lineterminator='\n')
    comparison.to_csv(output/'10_comparacion_mensual_universos.csv',index=False,float_format='%.10f',lineterminator='\n')
    if legacy_path is not None:
        window_audit = audit_legacy_moving_windows(totals, legacy_path)
        window_audit.to_csv(output/'10_auditoria_trimestres_NO_anclas_mensuales.csv',index=False,float_format='%.10f',lineterminator='\n')
        catalog['legacy_window_comparison_records'] = len(window_audit)
        catalog['legacy_invalid_monthly_mae_pct'] = float(window_audit.incorrect_month_end_comparison_pct.abs().mean())
        catalog['legacy_correct_window_mae_persons'] = float(window_audit.correct_window_validation_difference_persons.abs().mean())
    catalog['legacy_moving_window_2015_2026']='NOT_ALLOWED_AS_SINGLE_MONTH_ANCHORS'
    catalog['h10_decision']='DIRECT_MONTHLY_FIRST; 14-branch split pending independent monthly evidence'
    (output/'10_catalogo_y_puerta.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'monthly_observations':len(monthly), 'months':len(totals),
            'max_rounding_residual_persons':float(totals.rounding_residual_persons.abs().max()),
            'unresolved_monthly_final_branches':('B','D_E')}
