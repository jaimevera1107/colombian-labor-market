"""Plan a recalculation before running it (dry run)."""

from __future__ import annotations

from collections.abc import Mapping

from icml.recalculation.gates import check_frozen_parameters
from icml.recalculation.policy import ANCHORED, MODES, TOTAL, AnchorPolicy


def plan_recalculation(
    mode: str,
    policy: AnchorPolicy,
    *,
    previous_inputs: Mapping[str, str],
    current_inputs: Mapping[str, str],
    previous_parameters: Mapping[str, str],
    current_parameters: Mapping[str, str],
    confirm_total: bool = False,
    accept_modified: bool = False,
    observation_checks: tuple[dict, ...] = (),
) -> dict:
    """Decide what a recalculation would do, without running anything.

    Parameters
    ----------
    mode : str
        ``anclado`` or ``total``.
    policy : AnchorPolicy
        Frozen years.
    previous_inputs, current_inputs : Mapping[str, str]
        ``{path: sha256}`` of the ingestion workbooks of the last delivery
        and of today.
    previous_parameters, current_parameters : Mapping[str, str]
        Same for the frozen parameters.
    confirm_total : bool
        Explicit confirmation required by the total mode.
    accept_modified : bool
        Allow an anchored run although an existing input changed content.
    observation_checks : tuple[dict, ...]
        Reports from ``check_frozen_observations`` (one per official source).

    Returns
    -------
    dict
        ``status``: ``SIN_CAMBIOS``, ``EJECUTAR`` or ``BLOQUEADO``.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    changed = sorted(
        path
        for path in set(previous_inputs) | set(current_inputs)
        if previous_inputs.get(path) != current_inputs.get(path)
    )
    added = [p for p in changed if p not in previous_inputs]
    removed = [p for p in changed if p not in current_inputs]
    modified = [p for p in changed if p in previous_inputs and p in current_inputs]
    parameters = check_frozen_parameters(previous_parameters, current_parameters)
    blockers: list[str] = []
    if mode == TOTAL:
        frozen_years = "se reescriben todos los años"
        if not confirm_total:
            blockers.append(
                "El recálculo total reescribe también los años anclados "
                f"(hasta {policy.last_anchor_year}); requiere --confirmar-total."
            )
    else:
        frozen_years = f"congelados hasta {policy.last_anchor_year}"
        if modified and not accept_modified:
            blockers.append(
                "Se modificó un insumo existente (" + ", ".join(modified) + "): puede "
                "tocar años congelados. Agregue el anexo nuevo como archivo nuevo, "
                "use --aceptar-modificados si no afecta años anclados, o el "
                "recálculo total."
            )
        if parameters["status"] == "BLOCKED":
            blockers.append(
                "Cambió un parámetro congelado: " + ", ".join(parameters["changed"])
            )
        for report in observation_checks:
            if report["status"] == "BLOCKED":
                changes = report.get("n_changes", report["n_revisions"])
                blockers.append(
                    f"{changes} cifras oficiales de años congelados cambiaron en la "
                    f"fuente (revisadas, eliminadas o agregadas; hasta "
                    f"{policy.last_anchor_year}); use el recálculo total si es intencional."
                )
    if blockers:
        status = "BLOQUEADO"
    elif not changed and mode == ANCHORED:
        status = "SIN_CAMBIOS"
    else:
        status = "EJECUTAR"
    return {
        "mode": mode,
        "status": status,
        "frozen_years": frozen_years,
        "last_anchor_year": policy.last_anchor_year,
        "inputs": {
            "added": added,
            "modified": modified,
            "removed": removed,
            "unchanged": len(set(previous_inputs) & set(current_inputs)) - len(modified),
        },
        "parameters": parameters,
        "observation_checks": list(observation_checks),
        "blockers": blockers,
    }
