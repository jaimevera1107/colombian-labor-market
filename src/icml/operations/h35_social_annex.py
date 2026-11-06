"""Audit the DANE Informal Employment and Social Security Excel for a target month.

The three distinct signals in this workbook are not interchangeable:
* published monthly employed/formal/informal (2021+),
* rolling-three-month employed/formal/informal (2021+),
* rolling-three-month social-security membership (2007+).

This validator records *observations*, NOT modeled ICML department rates. No
monthly vintage can be computed or published by this module alone.
"""
from __future__ import annotations

import hashlib
import math
import unicodedata
from datetime import date
from pathlib import Path

from openpyxl import load_workbook
from icml.operations.source_pair import _month

ABBREV = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')


def _norm(value: object) -> str:
    s = unicodedata.normalize('NFKD', str(value or '').lower())
    return ' '.join(''.join(x for x in s if not unicodedata.combining(x)).split())


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _periods_from(start: str, end: str) -> int:
    d1, d2 = _month(start), _month(end)
    count = 12 * (d2.year - d1.year) + d2.month - d1.month + 1
    if count < 1:
        raise ValueError('Source period predates the observation series')
    return count


def _month_label(period: str) -> str:
    return ABBREV[_month(period).month - 1]


def _rolling_label(end: str) -> tuple[str, str]:
    dt = _month(end)
    index = dt.year * 12 + dt.month - 1
    first = index - 2
    return ABBREV[first % 12], ABBREV[index % 12]


def _assert_header(actual: object, end: str, kind: str) -> None:
    s = _norm(actual)
    if kind == 'month':
        if s != _month_label(end):
            raise ValueError(f'Unexpected monthly column label for {end}: {actual!r}')
    else:
        beg, last = _rolling_label(end)
        # Older workbooks sometimes spell the last window "Jun - Ago".
        if beg not in s or last not in s or s.index(beg) > s.index(last):
            raise ValueError(f'Unexpected moving-quarter label for {end}: {actual!r}')


def _window_start(target: str) -> str:
    dt = _month(target)
    n = dt.year * 12 + dt.month - 3
    yy, mm = divmod(n, 12)
    return f'{yy:04d}-{mm+1:02d}'


def _numeric(sheet, row: int, column: int, *, name: str) -> float:
    val = sheet.cell(row, column).value
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0:
        raise ValueError(f'Invalid {name} in {sheet.title}!{row}:{column}: {val!r}')
    return float(val)


def _triplet(sheet, col: int, r: int, domain: str, target: str, kind: str) -> dict:
    expected = ('poblacion ocupada', 'formal', 'informal')
    actual = tuple(_norm(sheet.cell(r+i, 1).value) for i in range(3))
    if actual != expected:
        raise ValueError(f'{sheet.title}: missing {expected} at row {r}: {actual}')
    occupied, formal, informal = (
        _numeric(sheet, r+i, col, name=f'{domain} {v}')
        for i, v in enumerate(('occupied', 'formal', 'informal'))
    )
    if abs(occupied - formal - informal) > max(.006, occupied * 1e-7):
        raise ValueError(f'Informality accounting identity failed: {domain} {target} {kind}')
    return {'period': target, 'domain': domain, 'reference_type': kind,
            'occupied_thousands': occupied, 'formal_thousands': formal,
            'informal_thousands': informal, 'informality_rate': informal / occupied}


def inspect_social_annex(path: Path, target: str) -> dict:
    """Verify source *cells*, time windows and accounting for a target period.

    The supplied document must actually contain a completed period *ending*
    at target: an older or more recent workbook is rejected rather than used
    as an accidental or undisclosed revision of the target release.
    """
    path = Path(path)
    _month(target)
    if path.suffix.lower() != '.xlsx' or not path.is_file():
        raise ValueError('An original .xlsx Social Security annex is required')
    if path.stat().st_size > 60_000_000:
        raise ValueError('Unexpectedly large annex; requires manual verification')
    monthly_count = _periods_from('2021-01', target)
    rolling_count = _periods_from('2021-03', target)
    social_count = _periods_from('2007-03', target)
    wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        required = {'Grandes dominios ', 'Total nacional', 'Ciudades', 'Seguridad social Tnal'}
        if not required.issubset(set(wb.sheetnames)):
            raise ValueError(f'Missing source sheets: {sorted(required - set(wb.sheetnames))}')
        monthly = wb['Grandes dominios ']
        rolling = wb['Total nacional']
        cities = wb['Ciudades']
        security = wb['Seguridad social Tnal']
        # One more column after target must be empty: prevents accepting a later
        # annex as the target vintage without explicit revision designation.
        schemas = [
            (monthly, 13, 14, 1 + monthly_count, 'month'),
            (rolling, 13, 14, 1 + rolling_count, 'rolling'),
            (cities, 12, 13, 2 + rolling_count, 'rolling'),
            (security, 13, 14, 1 + social_count, 'rolling'),
        ]
        for sh, hdr, first, col, kind in schemas:
            _assert_header(sh.cell(hdr, col).value, target, kind)
            if sh.cell(first, col+1).value is not None:
                raise ValueError(f'{sh.title}: source contains newer values than {target}; revision must be staged explicitly')
        out = [_triplet(monthly, 1+monthly_count, 14, 'national', target, 'observed_monthly'),
               _triplet(monthly, 1+monthly_count, 21, '13_cities', target, 'observed_monthly')]
        # Total nacional rows 14-16, 21-23, 28-30.
        for name, row in (('national', 14), ('urban_cabeceras', 21), ('rural', 28)):
            out.append(_triplet(rolling, 1+rolling_count, row, name, target, 'rolling_three_months'))
        if abs(out[2]['occupied_thousands'] - out[3]['occupied_thousands'] - out[4]['occupied_thousands']) > .006:
            raise ValueError('National rolling occupation != urban + rural')
        if _norm(security.cell(14, 1).value) != 'poblacion ocupada':
            raise ValueError('Social Security occupation row moved')
        if _norm(security.cell(23, 1).value) != 'cotiza a pension':
            raise ValueError('Social Security pension row moved')
        n = _numeric(security, 14, 1+social_count, name='social occupation')
        subscribed = _numeric(security, 23, 1+social_count, name='pension contributors')
        if subscribed > n + .006:
            raise ValueError('Pension contributors exceed occupied')
        if abs(n-out[2]['occupied_thousands']) > .01:
            raise ValueError('Different occupied totals between Social Security and Informality annex sheets')
        return {'status': 'PASS_SOURCE_CONTENT', 'period': target, 'sha256': _digest(path),
                'source_file': path.name, 'three_month_window_start': _window_start(target),
                'source_content_validation': {'monthly': True, 'rolling_three_months': True,
                                              'social_security': True, 'sheet_periods_checked': 4,
                                              'occupied_formal_informal_identity': True},
                'observations': out,
                'social_security_rolling': {'period': target, 'occupied_thousands': n,
                                            'pension_contributors_thousands': subscribed,
                                            'pension_contributors_are_not_identical_to_formal': True},
                'authorizes_model_execution': False, 'authorizes_publication': False}
    finally:
        wb.close()
