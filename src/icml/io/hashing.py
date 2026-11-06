"""Content hashing for reproducibility manifests."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_BYTES = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks.

    Raises
    ------
    FileNotFoundError
        If the path is not an existing file.
    """
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    """Return the SHA-256 hex digest of an in-memory payload."""
    return hashlib.sha256(payload).hexdigest()
