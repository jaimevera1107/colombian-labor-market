"""Gráficas de auditoría visual del ICML: 33 territorios + nacional.

Lee directamente los productos de quality (departamentos.csv, nacionales.csv)
y genera una gráfica por indicador (TD, TO, TGP) con los 33 departamentos
paginados en grupos de 11, más el comparativo nacional.

Uso:
    python graficar_auditoria.py --productos /tmp/out/labor/quality/products --salida /tmp/graficas
    python graficar_auditoria.py --root .    --salida /tmp/graficas
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import matplotlib
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


INDICATORS: list[tuple[str, str, str]] = [
    ("unemployment_rate",  "TD — Tasa de Desempleo",            "TD"),
    ("employment_rate",    "TO — Tasa de Ocupación",             "TO"),
    ("participation_rate", "TGP — Tasa Global de Participación", "TGP"),
]
PAGE_SIZE = 11
COLOR_CENSO = "#1F4E79"
COLOR_GEIH  = "#E67E22"
SPLICE_2001 = pd.Timestamp("2001-01-01")
SPLICE_2014 = pd.Timestamp("2014-01-01")


def _geih_rate(s: pd.DataFrame, col: str) -> np.ndarray:
    """Return the GEIH rate for the given column.

    For TD, use the represented numerator/denominator so that the capital's
    differential signal is preserved for the nine partial territories.
    For TO and TGP, the published rate already equals the census rate by
    construction (factors cancel in the ratio), so we return it directly.
    """
    if col == "unemployment_rate":
        lf = s["labor_force_represented"].values.astype(float)
        return np.where(lf > 0, s["unemployed_represented"].values / lf * 100, np.nan)
    return s[col].values * 100.0


def plot_departments(
    dep: pd.DataFrame,
    ind_col: str,
    ind_label: str,
    slug: str,
    output: Path,
    dpi: int = 100,
) -> list[Path]:
    """Generate paginated department plots for one indicator."""
    names_map = (
        dep[["dep_code", "territory_name"]]
        .drop_duplicates()
        .set_index("dep_code")["territory_name"]
        .to_dict()
    )
    codes = sorted(dep.dep_code.unique())
    pages = [codes[i : i + PAGE_SIZE] for i in range(0, len(codes), PAGE_SIZE)]
    written: list[Path] = []

    for pg, page_codes in enumerate(pages, 1):
        n = len(page_codes)
        fig, axes = plt.subplots(n, 1, figsize=(14, n * 2.1), constrained_layout=True)
        if n == 1:
            axes = [axes]
        fig.suptitle(
            f"{ind_label}  |  Censo (azul) · GEIH (naranja)  |  Pág {pg}/{len(pages)}",
            fontsize=10,
            weight="bold",
        )
        for row, code in enumerate(page_codes):
            s = dep[dep.dep_code == code].sort_values("period")
            dates = pd.to_datetime(s.period)
            name  = names_map.get(code, str(code))
            yc    = s[ind_col].values * 100.0
            yg    = _geih_rate(s, ind_col)

            ax = axes[row]
            ax.axvspan(dates.min(), SPLICE_2001, alpha=0.05, color="gray")
            ax.axvline(SPLICE_2001, color="gray",    lw=0.7, ls=":")
            ax.axvline(SPLICE_2014, color="#C0392B", lw=0.7, ls=":")
            ax.plot(dates, yc, color=COLOR_CENSO, lw=1.0, alpha=0.6, label="Censo")
            ax.plot(dates, yg, color=COLOR_GEIH,  lw=1.1, ls="--",   label="GEIH")
            ax.set_ylim(0, None)
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda v, _: f"{v:.0f}%")
            )
            ax.tick_params(labelsize=6)
            ax.set_ylabel(
                name, fontsize=7, weight="bold",
                rotation=0, ha="right", va="center", labelpad=72,
            )
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            if row == 0:
                ax.legend(fontsize=7, loc="upper right")

        out = output / f"{slug}_p{pg}.png"
        fig.savefig(out, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        written.append(out)

    return written


def plot_national(nat: pd.DataFrame, output: Path, dpi: int = 110) -> Path:
    """Generate the national comparison plot (ICML_COMPLETO vs DANE_REFERENCIA)."""
    nat_i = nat[nat.national_type == "ICML_COMPLETO"].sort_values("period")
    nat_g = nat[nat.national_type == "DANE_REFERENCIA"].sort_values("period")
    dates_i = pd.to_datetime(nat_i.period)
    dates_g = pd.to_datetime(nat_g.period)

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), constrained_layout=True)
    fig.suptitle(
        "Nacional — ICML_COMPLETO (azul) · DANE_REFERENCIA (naranja)",
        fontsize=11, weight="bold",
    )
    for ax, (col, label) in zip(
        axes,
        [("unemployment_rate", "TD"), ("employment_rate", "TO"), ("participation_rate", "TGP")],
    ):
        ax.axvline(SPLICE_2001, color="gray",    lw=0.8, ls=":")
        ax.axvline(SPLICE_2014, color="#C0392B", lw=0.8, ls=":")
        ax.plot(dates_i, nat_i[col] * 100, color=COLOR_CENSO, lw=1.5, label="ICML_COMPLETO")
        ax.plot(dates_g, nat_g[col] * 100, color=COLOR_GEIH,  lw=1.5, ls="--", label="DANE_REFERENCIA")
        ax.set_title(label, fontsize=9, weight="bold")
        ax.set_ylim(0, None)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=8)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    out = output / "nacional.png"
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out


def run(productos: Path, salida: Path, dpi: int = 100) -> int:
    dep_path = productos / "departamentos.csv"
    nat_path = productos / "nacionales.csv"
    if not dep_path.exists() or not nat_path.exists():
        print(f"Error: no se encontraron productos en {productos}", file=sys.stderr)
        return 1

    dep = pd.read_csv(dep_path)
    nat = pd.read_csv(nat_path)
    salida.mkdir(parents=True, exist_ok=True)

    all_files: list[Path] = []
    for ind_col, ind_label, slug in INDICATORS:
        files = plot_departments(dep, ind_col, ind_label, slug, salida, dpi=dpi)
        all_files.extend(files)
        print(f"  {slug}: {len(files)} páginas")

    nat_file = plot_national(nat, salida, dpi=dpi + 10)
    all_files.append(nat_file)
    print(f"  nacional: 1 gráfica")
    print(f"\nTotal: {len(all_files)} gráficas en {salida}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--productos", type=Path,
        help="Carpeta con departamentos.csv y nacionales.csv (p.ej. labor/quality/products)",
    )
    group.add_argument(
        "--root", type=Path,
        help="Raíz del proyecto; busca los productos en datos/2_procesamiento/productos_congelados/laboral/",
    )
    parser.add_argument(
        "--salida", type=Path,
        help="Carpeta de salida (por defecto <productos>/../graficas_auditoria)",
    )
    parser.add_argument("--dpi", type=int, default=100)
    args = parser.parse_args(argv)

    if args.root is not None:
        productos = args.root / "datos/2_procesamiento/productos_congelados/laboral"
    else:
        productos = args.productos

    salida = args.salida or productos.parent / "graficas_auditoria"
    return run(productos, salida, dpi=args.dpi)


if __name__ == "__main__":
    sys.exit(main())
