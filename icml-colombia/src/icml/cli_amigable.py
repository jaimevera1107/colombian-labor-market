"""Comandos sencillos del proyecto, en español.

``icml estado``       qué hay en el proyecto y cuál es el siguiente paso;
``icml consolidar``   construir la base completa (``--desde-cero`` fuerza recomenzar todo);
``icml actualizar``   actualizar SOLO el mes nuevo (los años anclados no se tocan);
``icml graficos``     dibujar la última entrega (herramienta opcional);
``icml verificar``    auditar una entrega.

Son una capa delgada sobre ``recalcular`` y ``entrega``: no calculan nada por su cuenta.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

COMMANDS = ("estado", "consolidar", "actualizar", "graficos", "verificar")
INGESTA = "datos/1_ingesta"
OUTPUT = "datos/3_salida"
CURRENT = "datos/2_procesamiento/vigente"
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
EXIT_OK, EXIT_ERROR, EXIT_ACTION = 0, 1, 2


# ----------------------------------------------------------------------------- parser


def add_commands(commands: argparse._SubParsersAction) -> None:
    """Register the friendly commands on the main parser."""

    def common(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--root", type=Path, help="Carpeta del proyecto (por defecto, la actual o la que la contiene)")

    common(commands.add_parser("estado", help="Qué hay en el proyecto y cuál es el siguiente paso"))

    consolidar = commands.add_parser(
        "consolidar",
        help="Construir la base completa; --desde-cero fuerza recomenzar todo",
        description="Recalcula TODOS los años (1993 hasta el último mes) y publica la base vigente.",
    )
    common(consolidar)
    consolidar.add_argument("--desde-cero", action="store_true", help="Forzar: recomenzar todo desde cero aunque ya haya una base publicada")
    consolidar.add_argument("--hasta", metavar="AAAA-MM", help="Último mes a incluir; los anexos posteriores se ignoran (por ejemplo 2026-07)")
    consolidar.add_argument("--si", action="store_true", help="No pedir confirmación")
    consolidar.add_argument("--simulacro", action="store_true", help="Solo mostrar qué haría, sin calcular")
    consolidar.add_argument("--sin-sencillo", action="store_true", help="No crear los archivos sencillos")

    actualizar = commands.add_parser(
        "actualizar",
        help="Actualizar SOLO el mes nuevo (los años anclados no se tocan)",
        description="Agrega el mes nuevo a la base vigente. Los años cubiertos por el anexo departamental quedan congelados.",
    )
    common(actualizar)
    actualizar.add_argument(
        "--hasta", "--mes", dest="hasta", metavar="AAAA-MM",
        help="Mes a incluir (por ejemplo 2026-07); los anexos posteriores se ignoran. --mes es lo mismo que --hasta",
    )
    actualizar.add_argument("--simulacro", action="store_true", help="Solo mostrar qué haría, sin calcular")
    actualizar.add_argument("--sin-sencillo", action="store_true", help="No crear los archivos sencillos")

    graficos = commands.add_parser("graficos", help="Dibujar la última entrega (tableros por territorio y comparativos)")
    common(graficos)
    graficos.add_argument("--carpeta", type=Path, help="Entrega a dibujar (por defecto, la vigente)")
    graficos.add_argument("--solo", help="nacional, departamentos, comparativos (separados por coma)")
    graficos.add_argument("--universo", help="censo o geih (por defecto ambos)")
    graficos.add_argument("--departamentos", help="Códigos DANE separados por coma (por defecto todos)")
    graficos.add_argument("--formato", choices=("png", "pdf", "svg"), default="png")
    graficos.add_argument("--forzar", action="store_true", help="Reemplazar los gráficos existentes")

    verificar = commands.add_parser("verificar", help="Auditar una entrega (36 comprobaciones)")
    common(verificar)
    verificar.add_argument("--carpeta", type=Path, help="Entrega a auditar (por defecto, la vigente)")


# ----------------------------------------------------------------------------- project state


def find_root(given: Path | None) -> Path:
    """The project root: the given folder, else the current one or the closest one above it."""
    candidates = [Path(given)] if given else [Path.cwd(), *Path.cwd().parents]
    for folder in candidates:
        folder = folder.resolve()
        if (folder / INGESTA).is_dir() and (folder / "icml-colombia").is_dir():
            return folder
    raise FileNotFoundError(
        "No encuentro la carpeta del proyecto (la que tiene datos/ e icml-colombia/). "
        "Ejecute el comando dentro de ella o use --root."
    )


def deliveries(root: Path) -> list[Path]:
    """Complete delivery folders (the ones with a manifest), oldest first."""
    output = root / OUTPUT
    return sorted(p for p in output.glob("*") if p.is_dir() and (p / "MANIFEST.json").is_file())


def current_vintage(root: Path) -> dict | None:
    """The published vintage: run id, mode and cutoff, or ``None`` when nothing is published."""
    path = root / CURRENT / "vigente.json"
    if not path.is_file():
        return None
    info = json.loads(path.read_text("utf-8"))
    if "cutoff" not in info:
        manifest = root / OUTPUT / info.get("run_id", "") / "MANIFEST.json"
        if manifest.is_file():
            info["cutoff"] = json.loads(manifest.read_text("utf-8")).get("cutoff")
    return info


def _delivery_folder(root: Path, given: Path | None) -> Path:
    if given:
        return Path(given).resolve()
    vintage = current_vintage(root)
    if vintage and (root / OUTPUT / vintage["run_id"]).is_dir():
        return root / OUTPUT / vintage["run_id"]
    found = deliveries(root)
    if not found:
        raise FileNotFoundError("Todavía no hay ninguna entrega. Primero: icml consolidar")
    return found[-1]


def _check_month(value: str | None) -> str | None:
    if value is not None and not _MONTH.match(value):
        raise ValueError(f"--hasta debe ser AAAA-MM (por ejemplo 2026-07), no {value!r}")
    return value


# ----------------------------------------------------------------------------- estado


def command_estado(root: Path) -> int:
    from icml import __version__
    from icml.domain.cutoff import FROZEN_CUTOFF
    from icml.ingestion.discovery import detect_cutoff

    detected = detect_cutoff(root / INGESTA)
    vintage = current_vintage(root)
    print(f"ICML {__version__} · proyecto: {root}\n")
    print("Anexos mensuales (datos/1_ingesta)")
    if detected["cutoff"]:
        print(f"  Último mes con los dos anexos: {detected['cutoff']}")
    else:
        print("  No hay ningún mes con los dos anexos (mercado laboral e informalidad).")
    for kind, label in (("only_mercado_laboral", "solo mercado laboral"), ("only_informalidad", "solo informalidad")):
        if detected["pending"][kind]:
            print(f"  Incompletos ({label}): {', '.join(detected['pending'][kind])}")
    print("\nBase publicada (la que usa la próxima actualización)")
    if vintage:
        print(f"  Corte {vintage.get('cutoff') or 'desconocido'} · corrida {vintage['run_id']} · modo {vintage['mode']}")
    else:
        print("  Ninguna todavía.")
    found = deliveries(root)
    print(f"\nEntregas: {len(found)}" + (f" (la última: {found[-1].name})" if found else ""))
    latest = found[-1] if found else None
    if latest is not None:
        sencillo, graficos = latest.with_name(latest.name + "_sencillo"), latest.with_name(latest.name + "_graficos")
        print(f"  archivos sencillos: {'sí' if sencillo.is_dir() else 'no'} · gráficos: {'sí' if graficos.is_dir() else 'no'}")

    print("\nSiguiente paso")
    reached = detected["cutoff"]
    if reached is None:
        print("  Copie en datos/1_ingesta/ los dos anexos de un mismo mes (ver datos/1_ingesta/LEEME.md).")
    elif reached > FROZEN_CUTOFF:
        print(f"  Hay anexos de {reached}, posteriores a {FROZEN_CUTOFF}: ese mes aún no se puede procesar.")
        print(f"  Para trabajar hasta {FROZEN_CUTOFF}: icml actualizar --hasta {FROZEN_CUTOFF}")
    elif vintage is None:
        print(f"  Primera vez: icml consolidar --desde-cero   (hasta {reached}; use --hasta AAAA-MM para otro mes)")
    elif (vintage.get("cutoff") or "") < reached:
        print(f"  Hay anexos más nuevos que la base ({vintage.get('cutoff')} → {reached}): icml actualizar")
    else:
        print("  Todo está al día. Para dibujar la última entrega: icml graficos")
        print("  Para recomenzar todo desde cero: icml consolidar --desde-cero")
    return EXIT_OK


# ----------------------------------------------------------------------------- consolidar / actualizar


def _relaunch(root: Path, command: str, args: argparse.Namespace, target: str) -> int:
    """Run the same command in a new process whose calendar ends at ``target``.

    The cutoff is fixed when the program starts (``ICML_CUTOFF``), so a month other than the default needs a fresh process.
    """
    cmd = [sys.executable, "-m", "icml", command, "--root", str(root), "--hasta", target]
    for flag in ("desde_cero", "si", "simulacro", "sin_sencillo"):
        if getattr(args, flag, False):
            cmd.append("--" + flag.replace("_", "-"))
    print(f"El cálculo hasta {target} necesita arrancar con ese corte; reiniciando el programa...\n")
    return subprocess.run(cmd, env={**os.environ, "ICML_CUTOFF": target}).returncode


def _confirm(message: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(message + "\n\nNo hay una terminal para confirmar: repita el comando con --si.")
        return False
    return input(message + "\n\nEscriba SI para continuar: ").strip().lower() in {"si", "sí"}


def _print_plan(plan: dict, ignored: frozenset[str] = frozenset()) -> None:
    inputs = plan.get("inputs", {})
    print(f"Plan: {plan['mode']} · años: {plan['frozen_years']}")
    for key, label in (("added", "anexos nuevos"), ("modified", "modificados"), ("removed", "retirados")):
        names = [Path(p).name for p in inputs.get(key, [])]
        if key == "removed":
            skipped = [n for n in names if n in ignored]
            names = [n for n in names if n not in ignored]
            if skipped:
                print(f"  ignorados por --hasta (se usarán en la próxima actualización): {', '.join(skipped)}")
        if names:
            print(f"  {label}: {', '.join(names)}")
    for blocker in plan.get("blockers", []):
        print(f"  BLOQUEADO: {blocker}")


def command_run(root: Path, command: str, args: argparse.Namespace) -> int:
    """``consolidar`` and ``actualizar``: both end in a delivery, its simple files and its audit."""
    from icml.cli_delivery import run_recalculation
    from icml.domain.cutoff import ACTIVE_CUTOFF, FROZEN_CUTOFF
    from icml.ingestion.discovery import detect_cutoff
    from icml.recalculation.policy import ANCHORED, TOTAL

    hasta = _check_month(args.hasta)
    vintage = current_vintage(root)
    detected = detect_cutoff(root / INGESTA, hasta)
    target = hasta or detected["cutoff"]
    if target is None:
        print("No hay un mes con los dos anexos (mercado laboral e informalidad) en datos/1_ingesta.")
        return EXIT_ACTION
    if hasta and hasta != detected["cutoff"]:
        print(f"No tengo los dos anexos de {hasta}. El último mes completo hasta ahí es {detected['cutoff']}.")
        return EXIT_ACTION
    if target > FROZEN_CUTOFF:
        print(
            f"Los anexos llegan hasta {target}, pero lo más nuevo que se puede procesar es {FROZEN_CUTOFF}: "
            "extender los parámetros congelados a meses nuevos aún no tiene una regla definida.\n"
            f"Para trabajar hasta {FROZEN_CUTOFF} ignorando lo posterior: icml {command} --hasta {FROZEN_CUTOFF}"
        )
        return EXIT_ACTION

    if command == "consolidar":
        mode = TOTAL
        if vintage and not args.desde_cero:
            print(
                f"Ya hay una base publicada (corte {vintage.get('cutoff')}).\n"
                "  · Para agregar un mes nuevo:           icml actualizar\n"
                "  · Para recomenzar todo desde cero:     icml consolidar --desde-cero"
            )
            return EXIT_ACTION
    else:
        mode = ANCHORED
        if vintage is None:
            print("Todavía no hay una base publicada que actualizar. Primero: icml consolidar --desde-cero")
            return EXIT_ACTION
        if vintage.get("cutoff") and target < vintage["cutoff"]:
            print(
                f"La base ya llega a {vintage['cutoff']}; actualizar no retrocede a {target}.\n"
                f"Para rehacerla hasta {target}: icml consolidar --desde-cero --hasta {target}"
            )
            return EXIT_ACTION

    if target != ACTIVE_CUTOFF:
        return _relaunch(root, command, args, target)

    if command == "consolidar" and vintage and not args.simulacro:
        ok = _confirm(
            f"Va a recalcular TODO desde cero hasta {target}.\n"
            f"Reemplaza la base publicada (corte {vintage.get('cutoff')}); las entregas anteriores se conservan.",
            args.si,
        )
        if not ok:
            print("No se cambió nada.")
            return EXIT_ACTION
    headline = (
        f"RECOMENZAR DESDE CERO hasta {target}: se recalculan todos los años."
        if mode == TOTAL
        else f"SOLO ACTUALIZAR hasta {target}: los años anclados se conservan y solo se recalcula lo abierto."
    )
    print(headline + "\n")
    result = run_recalculation(
        root,
        mode,
        confirm_total=mode == TOTAL,
        dry_run=args.simulacro,
        upto=target if (hasta or target < FROZEN_CUTOFF) else None,
    )
    plan = result["plan"]
    from icml.ingestion.discovery import annexes_after

    _print_plan(plan, frozenset(p.name for p in annexes_after(root / INGESTA, target)))
    if plan["status"] == "BLOQUEADO":
        return EXIT_ACTION
    if plan["status"] == "SIN_CAMBIOS":
        print("\nYa está al día: no hay anexos nuevos desde la última actualización.")
        return EXIT_OK
    if args.simulacro:
        print("\nSimulacro: no se calculó ni se cambió nada.")
        return EXIT_OK
    folder = root / OUTPUT / result["manifest"]["run_id"]
    return _finish(root, folder, make_simple=not args.sin_sencillo)


def _finish(root: Path, folder: Path, *, make_simple: bool) -> int:
    from icml.delivery.simple import build_simple
    from icml.delivery.verify import verify_delivery

    print(f"\nEntrega: {folder}")
    report = verify_delivery(folder)
    failed = [c["check"] for c in report["checks"] if not c["passed"]]
    print(f"Auditoría: {report['status']} ({len(report['checks']) - len(failed)} de {len(report['checks'])} comprobaciones)")
    for name in failed:
        print(f"  FALLÓ: {name}")
    if make_simple:
        simple = build_simple(folder)
        print(f"Archivos sencillos: {simple['folder']}")
    print("\nSiguiente paso: icml graficos")
    return EXIT_OK if report["status"] == "PASS" else EXIT_ERROR


# ----------------------------------------------------------------------------- graficos / verificar


def _audit_plots_tool():
    """Load graficar_auditoria — reads quality products directly, no MANIFEST needed."""
    path = Path(__file__).resolve().parents[2] / "tools" / "plots" / "graficar_auditoria.py"
    if not path.is_file():
        raise FileNotFoundError(f"No encuentro la herramienta de gráficos de auditoría: {path}")
    spec = importlib.util.spec_from_file_location("graficar_auditoria", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def command_graficos(root: Path, args: argparse.Namespace) -> int:
    """Generate audit plots for all 33 territories and national.

    Reads directly from the frozen quality products so no delivery MANIFEST
    is required.  Output goes to datos/2_procesamiento/productos_congelados/
    laboral/graficas_auditoria/ unless --carpeta overrides the source folder.
    """
    if args.carpeta:
        productos = Path(args.carpeta)
    else:
        productos = root / "datos/2_procesamiento/productos_congelados/laboral"

    salida = productos.parent / "graficas_auditoria"
    if salida.exists() and not args.forzar:
        print(
            f"Ya existe {salida}. Use --forzar para regenerar.",
            file=sys.stderr,
        )
        return 2
    if salida.exists() and args.forzar:
        import shutil as _shutil
        _shutil.rmtree(salida)

    print(f"Generando gráficas de auditoría desde {productos} ...")
    code = _audit_plots_tool().run(productos, salida, dpi=args.formato == "pdf" and 150 or 100)
    if code == 0:
        print(f"\nGráficas en {salida}")
    return code


def command_verificar(root: Path, args: argparse.Namespace) -> int:
    from icml.delivery.verify import verify_delivery

    folder = _delivery_folder(root, args.carpeta)
    report = verify_delivery(folder)
    failed = [c["check"] for c in report["checks"] if not c["passed"]]
    print(f"{folder.name}: {report['status']} ({len(report['checks']) - len(failed)} de {len(report['checks'])} comprobaciones)")
    for name in failed:
        print(f"  FALLÓ: {name}")
    return EXIT_OK if report["status"] == "PASS" else EXIT_ERROR


def run_command(args: argparse.Namespace) -> int:
    """Dispatch a friendly command; a user mistake prints a plain message, never a traceback."""
    try:
        root = find_root(args.root)
        if args.command == "estado":
            return command_estado(root)
        if args.command in ("consolidar", "actualizar"):
            return command_run(root, args.command, args)
        if args.command == "graficos":
            return command_graficos(root, args)
        return command_verificar(root, args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"\n{exc}", file=sys.stderr)
        return EXIT_ERROR
