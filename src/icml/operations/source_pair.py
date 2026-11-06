"""Contract for synchronizing the two required DANE ICML monthly annexes.

GEIH labor is a reference month; DANE Informal Employment and Social Security
is a 3-month moving window. Both must END in the SAME target month.

This module checks calendar declarations and file presence only. It cannot
independently verify the content of the social-security XLSX and never grants
permission to publish a vintage. These checks precede content validation.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path


def _month(text: str) -> date:
    if len(text) != 7 or text[4] != "-":
        raise ValueError(f"Expected YYYY-MM, received: {text!r}")
    try:
        parsed = date.fromisoformat(text + "-01")
    except ValueError as exc:
        raise ValueError(f"Invalid reference month: {text!r}") from exc
    if parsed.strftime("%Y-%m") != text:
        raise ValueError(f"Invalid reference month: {text!r}")
    return parsed


def _shift_month(d: date, delta: int) -> date:
    number = d.year * 12 + (d.month - 1) + delta
    year, m0 = divmod(number, 12)
    return date(year, m0 + 1, 1)


def expected_social_window(target_month: str) -> tuple[str, str]:
    """For a target YYYY-MM, return the rolling 3-month window (inclusive)."""
    end = _month(target_month)
    return _shift_month(end, -2).strftime("%Y-%m"), target_month


def check_monthly_sources(
    target_month: str,
    labor_annex: Path | None,
    social_security_annex: Path | None,
    labor_month: str | None = None,
    social_start: str | None = None,
    social_end: str | None = None,
) -> dict:
    """Fail closed when either source is missing or their periods differ.

    The declared periods MUST ALSO be verified against the original workbook
    by the source-specific ingest pipeline. A passing structural check is only
    a prerequisite: it is never a license to compute or publish the ICML.
    """
    target = _month(target_month)
    expected_start, expected_end = expected_social_window(target_month)
    blockers: list[str] = []
    if labor_annex is None or not labor_annex.is_file():
        blockers.append("MISSING_GEIH_LABOR_ANNEX")
    if social_security_annex is None or not social_security_annex.is_file():
        blockers.append("MISSING_INFORMALITY_AND_SOCIAL_SECURITY_ANNEX")
    if labor_month is None:
        blockers.append("GEIH_REFERENCE_MONTH_NOT_DOCUMENTED")
    elif _month(labor_month) != target:
        blockers.append("GEIH_MONTH_MISMATCH")
    if social_start is None or social_end is None:
        blockers.append("SOCIAL_SECURITY_3M_WINDOW_NOT_DOCUMENTED")
    else:
        start, end = _month(social_start), _month(social_end)
        if start != _shift_month(target, -2) or end != target:
            blockers.append("SOCIAL_SECURITY_WINDOW_MISMATCH")
    result = {
        "target_month": target_month,
        "required_sources": ["DANE_GEIH_LABOR_MONTHLY", "DANE_INFORMAL_EMPLOYMENT_AND_SOCIAL_SECURITY_ROLLING_3M"],
        "expected_geih_reference_month": target_month,
        "expected_social_security_start_month": expected_start,
        "expected_social_security_end_month": expected_end,
        "declared_geih_month": labor_month,
        "declared_social_start": social_start,
        "declared_social_end": social_end,
        "labor_file_present": labor_annex is not None and labor_annex.is_file(),
        "social_security_file_present": social_security_annex is not None and social_security_annex.is_file(),
        "blockers": blockers,
        "content_provenance_verified": False,
        "may_run_full_monthly_reconstruction": False,
        "may_publish_new_vintage": False,
        "notice": "Declared dates and file presence do not verify original DANE workbook content. Both original annexes must pass content, version, revision and quality checks before computation.",
    }
    result["status"] = (
        "BLOCKED_MISSING_OR_MISMATCHED_SOURCE_PAIR" if blockers
        else "PAIR_CALENDAR_COHERENT_AWAITING_SOURCE_CONTENT_VALIDATION"
    )
    return result
