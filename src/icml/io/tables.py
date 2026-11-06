"""Deterministic reading and writing of tabular artifacts.

Every CSV written by ICML uses the same format so that identical data
always produces identical bytes (and therefore identical hashes).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CsvFormat:
    """Serialization settings for CSV artifacts.

    Attributes
    ----------
    float_format : str | None
        ``printf`` format for floats, or ``None`` for the shortest decimal
        that round-trips (Python ``repr``, the default). RC1 wrote that
        way, and pandas' default parser reads it back exactly, whereas
        17-digit ``%.17g`` strings can come back one or two units in the
        last place off; the hierarchical closure amplifies such errors
        (1e-10 persons in an anchor moved reconciled months by 7e-5).
    encoding : str
        Text encoding.
    line_terminator : str
        Line terminator, fixed to avoid platform-dependent bytes.
    """

    float_format: str | None = None
    encoding: str = "utf-8"
    line_terminator: str = "\n"


DEFAULT_CSV_FORMAT = CsvFormat()


def write_table(
    frame: pd.DataFrame,
    path: Path,
    *,
    csv_format: CsvFormat = DEFAULT_CSV_FORMAT,
    overwrite: bool = False,
) -> Path:
    """Write a table atomically.

    The data is written to a temporary file in the destination folder and
    then moved into place, so a crash never leaves a truncated artifact.

    Parameters
    ----------
    frame : pandas.DataFrame
        Table to write. The index is not written.
    path : pathlib.Path
        Destination file.
    csv_format : CsvFormat, optional
        Serialization settings.
    overwrite : bool, default False
        Whether an existing file may be replaced.

    Returns
    -------
    pathlib.Path
        The destination path.

    Raises
    ------
    FileExistsError
        If the destination exists and ``overwrite`` is False.
    """
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(
            descriptor, "w", encoding=csv_format.encoding, newline=""
        ) as handle:
            frame.to_csv(
                handle,
                index=False,
                float_format=csv_format.float_format,
                lineterminator=csv_format.line_terminator,
            )
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return path


def read_table(
    path: Path,
    *,
    dtypes: Mapping[str, str] | None = None,
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """Read a CSV artifact.

    ``utf-8-sig`` transparently handles the byte-order mark that some RC1
    files carry.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(
        path, dtype=dict(dtypes) if dtypes else None, encoding=encoding
    )
