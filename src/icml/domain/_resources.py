"""Access to reference catalogs shipped as package data."""

from __future__ import annotations

import csv
import io
from importlib import resources

_DATA_PACKAGE = "icml.domain"
_DATA_FOLDER = "data"


def read_reference_table(file_name: str) -> list[dict[str, str]]:
    """Read a reference CSV bundled with the package.

    Parameters
    ----------
    file_name : str
        Name of the CSV file inside ``icml/domain/data``.

    Returns
    -------
    list[dict[str, str]]
        One dictionary per row, with raw string values.

    Raises
    ------
    FileNotFoundError
        If the file is not part of the installed package.
    """
    resource = resources.files(_DATA_PACKAGE).joinpath(_DATA_FOLDER, file_name)
    if not resource.is_file():
        raise FileNotFoundError(
            f"Reference table not found in package data: {file_name}"
        )
    text = resource.read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text, newline="")))
