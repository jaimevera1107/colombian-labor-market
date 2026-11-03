"""Column conventions of the national stage."""

from __future__ import annotations

from collections.abc import Mapping

from icml.domain.quantities import LaborQuantity

PERIOD_COLUMN = "period"
YEAR_COLUMN = "year"
PROVENANCE_COLUMN = "provenance"

QUANTITY_COLUMNS: tuple[str, ...] = tuple(str(q) for q in LaborQuantity)

# Quantities disaggregated independently, then reconciled; ``labor_force``
# and ``working_age`` are derived from them by accounting identities.
BASE_QUANTITIES: tuple[str, ...] = (
    str(LaborQuantity.EMPLOYED),
    str(LaborQuantity.UNEMPLOYED),
    str(LaborQuantity.INACTIVE),
    str(LaborQuantity.POPULATION),
)

# Canonical-to-RC1 names, used only by regression comparisons.
RC1_COLUMN_MAP: Mapping[str, str] = {
    PERIOD_COLUMN: "periodo",
    str(LaborQuantity.LABOR_FORCE): "pea",
    str(LaborQuantity.WORKING_AGE): "pet",
}


def source_token(quantity: str) -> str:
    """Return the token used for a quantity in RC1 source column names.

    RC1 sources name columns ``<token>_<source>``, e.g. ``pet_enh``.
    """
    return RC1_COLUMN_MAP.get(quantity, quantity)
