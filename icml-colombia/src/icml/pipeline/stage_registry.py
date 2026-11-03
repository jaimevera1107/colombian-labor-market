"""Lightweight, single-source stage metadata for CLI and full pipeline."""
from dataclasses import dataclass

@dataclass(frozen=True)
class StageSpec:
    name: str
    config_file: str
    upstream: tuple[str, ...]
    reads_sources: bool
    in_full_run: bool = True

SPECS = (
    StageSpec("census_bridge", "census_bridge.toml", ("quality",), True, False),
    StageSpec("national", "national.toml", (), True),
    StageSpec("urban", "urban.toml", ("national",), True),
    StageSpec("departmental", "departmental.toml", ("national",), True),
    StageSpec("integration", "integration.toml", ("national", "urban", "departmental"), True),
    StageSpec("modeling", "modeling.toml", ("integration", "departmental"), False),
    StageSpec("reconciliation", "reconciliation.toml", ("modeling", "integration", "departmental"), False),
    StageSpec("quality", "quality.toml", ("reconciliation",), False),
    StageSpec("informality", "informality.toml", ("quality",), True, False),
    StageSpec("evaluation", "evaluation.toml", ("integration", "departmental"), False, False),
)
STAGE_SPECS = {s.name:s for s in SPECS}
