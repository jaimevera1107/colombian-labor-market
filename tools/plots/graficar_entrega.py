"""Gráficos de una entrega del ICML (herramienta opcional).

Lee una entrega ya generada (la carpeta con ``MANIFEST.json``) y dibuja, para los dos universos:

* un **tablero** del nacional y de **cada departamento** (tasas laborales, niveles, informalidad
  y composición sectorial);
* **comparativos** de las tasas importantes (TD, TO, TGP, TI): nacional censo contra GEIH, los 33
  departamentos en miniatura, mapas de calor por año, ranking del último mes y dispersión
  departamental alrededor del nacional.

No cambia nada de la entrega y no es necesaria para calcular: solo lee resultados.

    python graficar_entrega.py --carpeta datos/3_salida/<entrega>
    python graficar_entrega.py --carpeta ... --solo nacional,comparativos --universo censo
    python graficar_entrega.py --carpeta ... --departamentos 05,11 --formato pdf

Escribe ``<entrega>_graficos/`` con un ``INDICE.html`` para recorrer todo en el navegador.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

UNIVERSES = ("censo", "geih")
UNIVERSE_LABEL = {"censo": "Universo censo (territorio completo)", "geih": "Universo GEIH (parte representada)"}
UNIVERSE_COLOR = {"censo": "#1F4E79", "geih": "#D55E00"}
#: Census thick and behind, GEIH thin and on top: where they coincide both stay visible.
UNIVERSE_WIDTH = {"censo": 2.6, "geih": 1.1}
UNIVERSE_ORDER = {"censo": 2, "geih": 3}
SPLICE = pd.Timestamp("2001-01-01")

#: Rate -> (domain, column, label, color). Colors are the Okabe-Ito palette (readable with color blindness).
RATES = {
    "TD": ("laboral", "TD", "Desempleo (TD)", "#D55E00"),
    "TO": ("laboral", "TO", "Ocupación (TO)", "#0072B2"),
    "TGP": ("laboral", "TGP", "Participación (TGP)", "#009E73"),
    "TI": ("informalidad", "TI", "Informalidad (TI)", "#CC79A7"),
}

SECTORS = ("A", "B", "C", "D_E", "F", "G", "H", "I", "J", "K", "L", "M_N", "O_P_Q", "R_S_T_U", "NO_INFO")
#: Short labels of the CIIU Rev. 4 A.C. sections the ICML uses (docs/sectoral/HITO10_*).
SECTOR_NAMES = {
    "A": "Agricultura y pesca",
    "B": "Minas y canteras",
    "C": "Industria",
    "D_E": "Electricidad, gas y agua",
    "F": "Construcción",
    "G": "Comercio",
    "H": "Transporte",
    "I": "Alojamiento y comidas",
    "J": "Información y comunicaciones",
    "K": "Financieras y seguros",
    "L": "Inmobiliarias",
    "M_N": "Profesionales y administrativas",
    "O_P_Q": "Administración pública, educación y salud",
    "R_S_T_U": "Otros servicios",
    "NO_INFO": "Sin información",
}
TEXT_COLUMNS = {"DPT", "CIUDAD", "Codigo", "Sector"}
GROUPS = ("nacional", "departamentos", "comparativos")

Frames = dict[tuple[str, str, str], pd.DataFrame]


@dataclass
class Meta:
    """What the figures say about where they come from."""

    cutoff: str = ""
    version: str = ""
    run_id: str = ""


@dataclass
class Output:
    """One figure written, for the index."""

    path: Path
    group: str
    title: str
    universe: str = ""


@dataclass
class Options:
    groups: tuple[str, ...] = GROUPS
    universes: tuple[str, ...] = UNIVERSES
    departments: tuple[str, ...] = ()
    dpi: int = 100
    fmt: str = "png"
    done: list[Output] = field(default_factory=list)


# ----------------------------------------------------------------------------- matplotlib


def _mpl():
    """Import matplotlib on demand, with the non-interactive backend."""
    try:
        import matplotlib
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SystemExit("Esta herramienta necesita matplotlib (pip install matplotlib; el instalador ya lo incluye).") from exc
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, PercentFormatter

    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "axes.titlelocation": "left",
            "grid.color": "#E3E3E3",
            "grid.linewidth": 0.6,
            "legend.frameon": False,
            "figure.facecolor": "white",
        }
    )
    return plt, mdates, PercentFormatter, FuncFormatter


# ----------------------------------------------------------------------------- helpers


def slug(text: str) -> str:
    """ASCII-safe file name fragment: ``Bogotá D.C.`` -> ``bogota-d-c``."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def scale_units(maximum: float) -> tuple[float, str]:
    """Divisor and unit name that keep a level readable (millones, miles or personas)."""
    if not np.isfinite(maximum):
        return 1.0, "personas"
    if maximum >= 1e6:
        return 1e6, "millones de personas"
    if maximum >= 1e3:
        return 1e3, "miles de personas"
    return 1.0, "personas"


def spans(mask: pd.Series, dates: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Contiguous runs where ``mask`` is true, as (first date, last date)."""
    out, start, last = [], None, None
    for flag, date in zip(mask.to_numpy(bool), dates, strict=True):
        if flag and start is None:
            start = date
        if flag:
            last = date
        if not flag and start is not None:
            out.append((start, last))
            start = None
    if start is not None:
        out.append((start, last))
    return out


def annual_mean(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Annual mean of ``column`` by territory code: rows = Codigo, columns = year."""
    return frame.groupby(["Codigo", "Año"])[column].mean().unstack("Año")


def sector_label(code: str) -> str:
    return SECTOR_NAMES.get(code, code)


def sector_colors(codes: Iterable[str]) -> dict[str, str]:
    """Stable color per sector across every figure; the residual category is gray."""
    plt, *_ = _mpl()
    palette = plt.get_cmap("tab20")
    order = {code: i for i, code in enumerate(SECTORS)}
    colors = {}
    for code in codes:
        if code == "NO_INFO" or code not in order:
            colors[code] = "#9A9A9A"
        else:
            colors[code] = palette(order[code] % 20)
    return colors


# ----------------------------------------------------------------------------- data


def load_frames(delivery: Path) -> tuple[Frames, Meta]:
    """Read a delivery into simple frames keyed by (universe, domain, level).

    The simple frames (Fecha, DPT, Codigo, rates...) are the same the simple files hold,
    so the figures work whether or not the ``_sencillo`` folder exists.
    """
    from icml.delivery.builder import read_text_table
    from icml.delivery.simple import simple_frame

    delivery = Path(delivery)
    manifest = json.loads((delivery / "MANIFEST.json").read_text("utf-8"))
    frames: Frames = {}
    for entry in manifest["outputs"]:
        if not entry["path"].endswith(".csv"):
            continue
        frame = simple_frame(entry["domain"], entry["level"], read_text_table(delivery / entry["path"]))
        frame["Fecha"] = pd.to_datetime(frame["Fecha"])
        for column in frame.columns:
            if column not in TEXT_COLUMNS and column != "Fecha":
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frames[(entry["universe"], entry["domain"], entry["level"])] = frame
    meta = Meta(manifest.get("cutoff", ""), manifest.get("software_version", ""), manifest.get("run_id", ""))
    return frames, meta


def departments(frames: Frames) -> pd.DataFrame:
    """Code and name of every department present, sorted by code."""
    for universe in UNIVERSES:
        frame = frames.get((universe, "laboral", "departamentos"))
        if frame is not None:
            return frame[["Codigo", "DPT"]].drop_duplicates().sort_values("Codigo").reset_index(drop=True)
    return pd.DataFrame(columns=["Codigo", "DPT"])


def series(frames: Frames, universe: str, domain: str, level: str, code: str | None = None) -> pd.DataFrame | None:
    """One territory's rows (or the national ones) sorted by date; ``None`` if absent."""
    frame = frames.get((universe, domain, level))
    if frame is None:
        return None
    if code is not None:
        frame = frame[frame["Codigo"] == code]
    return frame.sort_values("Fecha").reset_index(drop=True)


# ----------------------------------------------------------------------------- panels


def _heading(fig, title: str, meta: Meta, *notes: str) -> None:
    """Title, then a gray line with the notes and the provenance; space is reserved for both."""
    height = fig.get_figheight()
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.998, va="top")
    lines = [*notes, f"ICML {meta.version} · corte {meta.cutoff}"]
    fig.text(0.5, 0.998 - 0.34 / height, "\n".join(lines), ha="center", va="top", fontsize=8, color="0.35", linespacing=1.4)
    engine = fig.get_layout_engine()
    if engine is not None:
        engine.set(rect=(0, 0, 1, 1 - (0.5 + 0.16 * len(lines)) / height))


def _legend_above(ax, ncols: int) -> None:
    """Legend over the panel's top-right corner so it never covers a line."""
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncols=ncols, fontsize=8, handlelength=1.6, columnspacing=1.2)


def _style_time(ax, mdates, first: pd.Timestamp, last: pd.Timestamp, label_splice: str | bool = False) -> None:
    """Time axis with the reconstructed stretch shaded and the 2001-01 splice marked.

    ``label_splice``: ``"full"`` names both marks (wide panels), ``"compact"`` writes only
    the splice, rotated along its line (narrow panels), ``False`` writes nothing.
    """
    ax.xaxis.set_major_locator(mdates.YearLocator(5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_xlim(first, last)
    ax.axvspan(first, SPLICE, color="0.5", alpha=0.08, lw=0, zorder=0)
    ax.axvline(SPLICE, color="0.4", lw=0.8, ls="--")
    if label_splice == "compact":
        ax.text(SPLICE, 0.02, " empalme 2001-01", transform=ax.get_xaxis_transform(), rotation=90, va="bottom",
                ha="left", fontsize=7.5, color="0.35")
    elif label_splice:
        ax.text(first, 1.0, " reconstrucción 1993-2000", transform=ax.get_xaxis_transform(), va="top", ha="left",
                fontsize=7.5, color="0.35")
        ax.text(SPLICE, 1.0, " empalme 2001-01", transform=ax.get_xaxis_transform(), va="top", ha="left",
                fontsize=7.5, color="0.35")


def _mark_unrepresented(ax, dates: pd.Series, mask: pd.Series, label: bool = False) -> None:
    for start, end in spans(mask, dates):
        ax.axvspan(start, end, color="#E8B4B4", alpha=0.35, lw=0, zorder=0)
        if label:
            ax.text(start, 0.02, " sin representación GEIH", transform=ax.get_xaxis_transform(), va="bottom",
                    ha="left", fontsize=7.5, color="#8A3A3A")


def _levels(ax, frame: pd.DataFrame, columns: Mapping[str, str], colors: Mapping[str, str]) -> None:
    peak = float(np.nanmax(frame[list(columns)].to_numpy(float))) if len(frame) else 0.0
    divisor, unit = scale_units(peak)
    for column, label in columns.items():
        ax.plot(frame["Fecha"], frame[column] / divisor, label=label, color=colors[column], lw=1.4)
    ax.set_ylabel(unit)
    _legend_above(ax, len(columns))
    ax.set_ylim(bottom=0)


def plot_dashboard(
    frames: Frames,
    universe: str,
    *,
    code: str | None,
    name: str,
    path: Path,
    meta: Meta,
    dpi: int = 100,
) -> bool:
    """Draw the dashboard of one territory (``code=None`` = national). ``False`` if there is no data."""
    plt, mdates, PercentFormatter, _ = _mpl()
    level = "nacional" if code is None else "departamentos"
    labor = series(frames, universe, "laboral", level, code)
    if labor is None or labor.empty:
        return False
    informal = series(frames, universe, "informalidad", level, code)
    sector = series(frames, universe, "sectorial", level, code)
    labor = labor.copy()
    # Mark periods with no GEIH representation for shading only —
    # do NOT blank the data. All 33 territories cover the full
    # 1993-to-present range in both universes.
    unrepresented = labor["PET"].fillna(0) <= 0
    first, last = labor["Fecha"].min(), labor["Fecha"].max()

    fig = plt.figure(figsize=(12.5, 13.2), layout="constrained")
    grid = fig.add_gridspec(4, 2, height_ratios=[1.1, 1, 1, 1.2])

    ax = fig.add_subplot(grid[0, :])
    for rate in ("TD", "TO", "TGP"):
        _, column, label, color = RATES[rate]
        ax.plot(labor["Fecha"], labor[column], label=label, color=color, lw=1.5)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_title("Mercado laboral: tasas")
    _legend_above(ax, 3)
    _style_time(ax, mdates, first, last, label_splice="full")
    _mark_unrepresented(ax, labor["Fecha"], unrepresented, label=bool(unrepresented.any()))

    ax = fig.add_subplot(grid[1, 0])
    _levels(ax, labor, {"PET": "PET", "PEA": "PEA", "Ocupados": "Ocupados"},
            {"PET": "#7F7F7F", "PEA": "#E69F00", "Ocupados": "#0072B2"})
    ax.set_title("Población y ocupación")
    _style_time(ax, mdates, first, last)
    _mark_unrepresented(ax, labor["Fecha"], unrepresented)

    ax = fig.add_subplot(grid[1, 1])
    _levels(ax, labor, {"Desocupados": "Desocupados", "Inactivos": "Inactivos"},
            {"Desocupados": "#D55E00", "Inactivos": "#56B4E9"})
    ax.set_title("Desocupados e inactivos")
    _style_time(ax, mdates, first, last)
    _mark_unrepresented(ax, labor["Fecha"], unrepresented)

    ax = fig.add_subplot(grid[2, 0])
    ax.set_title("Informalidad: tasa")
    if informal is not None and not informal.empty:
        ax.plot(informal["Fecha"], informal["TI"], color=RATES["TI"][3], lw=1.5)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        _style_time(ax, mdates, first, last)
        _mark_unrepresented(ax, labor["Fecha"], unrepresented)
    else:
        ax.text(0.5, 0.5, "sin datos", transform=ax.transAxes, ha="center", color="0.5")

    ax = fig.add_subplot(grid[2, 1])
    ax.set_title("Informales y formales")
    if informal is not None and not informal.empty:
        peak = float(np.nanmax((informal["Informales"] + informal["Formales"]).to_numpy(float)))
        divisor, unit = scale_units(peak)
        ax.stackplot(informal["Fecha"], informal["Informales"].fillna(0) / divisor, informal["Formales"].fillna(0) / divisor,
                     labels=["Informales", "Formales"], colors=[RATES["TI"][3], "#BBD3E8"], lw=0)
        ax.set_ylabel(unit)
        _legend_above(ax, 2)
        _style_time(ax, mdates, first, last)
        _mark_unrepresented(ax, labor["Fecha"], unrepresented)

    ax = fig.add_subplot(grid[3, :])
    ax.set_title("Composición del empleo por sector")
    if sector is not None and not sector.empty:
        wide = sector.pivot(index="Fecha", columns="Sector", values="Participacion").reindex(columns=[c for c in SECTORS if c in set(sector["Sector"])])
        wide = wide.loc[:, wide.max() > 0.0005].fillna(0.0)
        colors = sector_colors(wide.columns)
        ax.stackplot(wide.index, *[wide[c] for c in wide.columns], labels=[sector_label(c) for c in wide.columns],
                     colors=[colors[c] for c in wide.columns], lw=0)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.set_ylim(0, 1)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncols=5, fontsize=8)
        _style_time(ax, mdates, first, last)
        _mark_unrepresented(ax, labor["Fecha"], unrepresented)

    notes = ["sombreado gris: tramo reconstruido (1993-2000)"]
    if unrepresented.any():
        notes.append("antes de 2001 el universo GEIH reconstruye todo el territorio; desde 2014 solo la parte representada")
    _heading(fig, f"{name} · {UNIVERSE_LABEL[universe]}", meta, *notes)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return True


# ----------------------------------------------------------------------------- comparatives


def _rate_series(frames: Frames, universe: str, rate: str, level: str, code: str | None = None) -> pd.DataFrame | None:
    domain, column, *_ = RATES[rate]
    frame = series(frames, universe, domain, level, code)
    return None if frame is None else frame[["Fecha", column]].rename(columns={column: "valor"})


def plot_national_comparison(frames: Frames, path: Path, meta: Meta, dpi: int = 100) -> bool:
    """Nacional: the four rates, censo against GEIH."""
    plt, mdates, PercentFormatter, _ = _mpl()
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8), layout="constrained", sharex=True)
    drawn = False
    for ax, rate in zip(axes.ravel(), RATES, strict=True):
        for universe in UNIVERSES:
            data = _rate_series(frames, universe, rate, "nacional")
            if data is not None and not data.empty:
                ax.plot(data["Fecha"], data["valor"], color=UNIVERSE_COLOR[universe], lw=UNIVERSE_WIDTH[universe],
                        zorder=UNIVERSE_ORDER[universe], label=UNIVERSE_LABEL[universe])
                drawn = True
        ax.set_title(RATES[rate][2])
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        lo = min((frames[(u, RATES[rate][0], "nacional")]["Fecha"].min() for u in UNIVERSES if (u, RATES[rate][0], "nacional") in frames), default=SPLICE)
        hi = max((frames[(u, RATES[rate][0], "nacional")]["Fecha"].max() for u in UNIVERSES if (u, RATES[rate][0], "nacional") in frames), default=SPLICE)
        _style_time(ax, mdates, lo, hi, label_splice="compact" if rate == "TD" else False)
    if not drawn:
        plt.close(fig)
        return False
    axes[0, 0].legend(loc="upper right", fontsize=8.5)
    _heading(fig, "Tasas nacionales: universo censo frente a universo GEIH", meta, "línea discontinua: empalme de 2001-01")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return True


def plot_department_grid(frames: Frames, rate: str, path: Path, meta: Meta, dpi: int = 100) -> bool:
    """The 33 departments in miniature for one rate, both universes over the national reference."""
    plt, mdates, PercentFormatter, _ = _mpl()
    deps = departments(frames)
    if deps.empty:
        return False
    cols = 6
    rows = int(np.ceil(len(deps) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(14, 2.05 * rows + 1.2), layout="constrained", sharex=True, sharey=True)
    flat = axes.ravel()
    reference = _rate_series(frames, "censo", rate, "nacional")
    for ax, (_, dep) in zip(flat, deps.iterrows(), strict=False):
        if reference is not None:
            ax.plot(reference["Fecha"], reference["valor"], color="0.7", lw=0.8)
        for universe in UNIVERSES:
            data = _rate_series(frames, universe, rate, "departamentos", dep["Codigo"])
            if data is not None and not data.empty:
                ax.plot(data["Fecha"], data["valor"], color=UNIVERSE_COLOR[universe], lw=UNIVERSE_WIDTH[universe] * 0.6,
                        zorder=UNIVERSE_ORDER[universe])
        ax.set_title(dep["DPT"], fontsize=8)
        ax.axvline(SPLICE, color="0.4", lw=0.5, ls="--")
        ax.xaxis.set_major_locator(mdates.YearLocator(10))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.tick_params(labelsize=7)
    for ax in flat[len(deps):]:
        ax.set_visible(False)
    handles = [plt.Line2D([], [], color=UNIVERSE_COLOR[u], lw=UNIVERSE_WIDTH[u], label=UNIVERSE_LABEL[u]) for u in UNIVERSES]
    handles.append(plt.Line2D([], [], color="0.7", lw=1.2, label="Nacional (censo)"))
    fig.legend(handles=handles, loc="outside lower center", ncols=3, fontsize=9)
    _heading(fig, f"{RATES[rate][2]}: los 33 departamentos", meta, "misma escala vertical en todos los departamentos")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return True


def plot_heatmap(frames: Frames, universe: str, rate: str, path: Path, meta: Meta, dpi: int = 100) -> bool:
    """Department by year (annual mean) heat map, sorted by the latest year."""
    plt, mdates, PercentFormatter, _ = _mpl()
    domain, column, label, _ = RATES[rate]
    frame = frames.get((universe, domain, "departamentos"))
    deps = departments(frames)
    if frame is None or deps.empty:
        return False
    table = annual_mean(frame, column)
    table = table.dropna(how="all")
    if table.empty:
        return False
    last_full = table.columns[-1]
    order = table.sort_values(last_full, ascending=True, na_position="first").index
    table = table.loc[order]
    names = deps.set_index("Codigo")["DPT"].reindex(table.index)
    fig, ax = plt.subplots(figsize=(12.5, 0.27 * len(table) + 2.2), layout="constrained")
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#EDEDED")
    mesh = ax.pcolormesh(np.arange(table.shape[1] + 1), np.arange(table.shape[0] + 1), np.ma.masked_invalid(table.to_numpy(float)), cmap=cmap)
    ax.set_yticks(np.arange(table.shape[0]) + 0.5, labels=names.to_numpy(), fontsize=8)
    step = 3
    ticks = np.arange(0, table.shape[1], step)
    ax.set_xticks(ticks + 0.5, labels=[str(int(table.columns[i])) for i in ticks], fontsize=8)
    ax.grid(False)
    ax.spines[:].set_visible(False)
    bar = fig.colorbar(mesh, ax=ax, shrink=0.8, pad=0.01)
    bar.ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    notes = ["gris = sin dato (la GEIH no representa el territorio)"] if universe == "geih" else []
    _heading(fig, f"{label}: promedio anual por departamento · {UNIVERSE_LABEL[universe]}", meta, *notes, "el último año es parcial")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return True


def plot_ranking(frames: Frames, rate: str, path: Path, meta: Meta, dpi: int = 100) -> bool:
    """Latest month: every department, censo against GEIH, with the national value."""
    plt, mdates, PercentFormatter, _ = _mpl()
    domain, column, label, _ = RATES[rate]
    values: dict[str, pd.Series] = {}
    for universe in UNIVERSES:
        frame = frames.get((universe, domain, "departamentos"))
        if frame is not None and not frame.empty:
            latest = frame["Fecha"].max()
            values[universe] = frame[frame["Fecha"] == latest].set_index("Codigo")[column]
    if "censo" not in values:
        return False
    deps = departments(frames).set_index("Codigo")["DPT"]
    order = values["censo"].sort_values().index
    fig, ax = plt.subplots(figsize=(10, 0.3 * len(order) + 2), layout="constrained")
    y = np.arange(len(order))
    for universe in UNIVERSES:
        if universe in values:
            ax.scatter(values[universe].reindex(order), y, color=UNIVERSE_COLOR[universe], s=90 if universe == "censo" else 24,
                       label=UNIVERSE_LABEL[universe], zorder=3 if universe == "censo" else 4)
    if "geih" in values:
        ax.hlines(y, values["censo"].reindex(order), values["geih"].reindex(order), color="0.8", lw=1.2, zorder=2)
    for universe in UNIVERSES:
        national = _rate_series(frames, universe, rate, "nacional")
        if national is not None and not national.empty:
            ax.axvline(national.sort_values("Fecha")["valor"].iloc[-1], color=UNIVERSE_COLOR[universe], lw=1, ls=":", alpha=0.8)
    ax.set_yticks(y, labels=deps.reindex(order).to_numpy(), fontsize=8)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    month = frames[("censo", domain, "departamentos")]["Fecha"].max().strftime("%Y-%m")
    ax.legend(loc="lower right", fontsize=8.5)
    _heading(fig, f"{label} por departamento · {month}", meta, "líneas punteadas: valor nacional")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return True


def plot_dispersion(frames: Frames, universe: str, path: Path, meta: Meta, dpi: int = 100) -> bool:
    """How far the departments sit from the national value, over time, for the four rates."""
    plt, mdates, PercentFormatter, _ = _mpl()
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8), layout="constrained", sharex=True)
    drawn = False
    for ax, rate in zip(axes.ravel(), RATES, strict=True):
        domain, column, label, color = RATES[rate]
        frame = frames.get((universe, domain, "departamentos"))
        national = _rate_series(frames, universe, rate, "nacional")
        if frame is None or frame.empty:
            continue
        wide = frame.pivot(index="Fecha", columns="Codigo", values=column)
        low, high = wide.quantile(0.1, axis=1), wide.quantile(0.9, axis=1)
        ax.fill_between(wide.index, wide.min(axis=1), wide.max(axis=1), color=color, alpha=0.12, lw=0, label="mínimo a máximo")
        ax.fill_between(wide.index, low, high, color=color, alpha=0.3, lw=0, label="percentil 10 a 90")
        ax.plot(wide.index, wide.median(axis=1), color=color, lw=1.2, ls="--", label="mediana departamental")
        if national is not None:
            ax.plot(national["Fecha"], national["valor"], color="black", lw=1.4, label="nacional")
        ax.set_title(label)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        _style_time(ax, mdates, wide.index.min(), wide.index.max(), label_splice="compact" if rate == "TD" else False)
        drawn = True
    if not drawn:
        plt.close(fig)
        return False
    axes[0, 0].legend(loc="upper right", fontsize=8)
    _heading(fig, f"Dispersión departamental alrededor del nacional · {UNIVERSE_LABEL[universe]}", meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return True


# ----------------------------------------------------------------------------- orchestration


def _record(options: Options, path: Path, group: str, title: str, universe: str = "") -> None:
    options.done.append(Output(path, group, title, universe))


def build_all(frames: Frames, output: Path, meta: Meta, options: Options | None = None) -> list[Output]:
    """Draw everything the options ask for into ``output`` and return what was written."""
    options = options or Options()
    ext = options.fmt
    output = Path(output)
    deps = departments(frames)
    wanted = set(options.departments)
    if "nacional" in options.groups:
        for universe in options.universes:
            path = output / f"universo_{universe}" / f"nacional.{ext}"
            if plot_dashboard(frames, universe, code=None, name="Nacional", path=path, meta=meta, dpi=options.dpi):
                _record(options, path, "nacional", "Nacional", universe)
    if "departamentos" in options.groups:
        for universe in options.universes:
            for _, dep in deps.iterrows():
                if wanted and dep["Codigo"] not in wanted:
                    continue
                path = output / f"universo_{universe}" / "departamentos" / f"{dep['Codigo']}_{slug(dep['DPT'])}.{ext}"
                if plot_dashboard(frames, universe, code=dep["Codigo"], name=dep["DPT"], path=path, meta=meta, dpi=options.dpi):
                    _record(options, path, "departamentos", dep["DPT"], universe)
    if "comparativos" in options.groups:
        folder = output / "comparativos"
        path = folder / f"nacional_censo_vs_geih.{ext}"
        if {"censo", "geih"} <= set(options.universes) and plot_national_comparison(frames, path, meta, options.dpi):
            _record(options, path, "comparativos", "Tasas nacionales: censo frente a GEIH")
        for rate in RATES:
            if {"censo", "geih"} <= set(options.universes):
                path = folder / f"departamentos_{rate}_censo_vs_geih.{ext}"
                if plot_department_grid(frames, rate, path, meta, options.dpi):
                    _record(options, path, "comparativos", f"{RATES[rate][2]}: los 33 departamentos")
                path = folder / f"ranking_{rate}.{ext}"
                if plot_ranking(frames, rate, path, meta, options.dpi):
                    _record(options, path, "comparativos", f"{RATES[rate][2]}: ranking del último mes")
            for universe in options.universes:
                path = folder / f"mapa_calor_{rate}_{universe}.{ext}"
                if plot_heatmap(frames, universe, rate, path, meta, options.dpi):
                    _record(options, path, "comparativos", f"{RATES[rate][2]}: mapa de calor anual", universe)
        for universe in options.universes:
            path = folder / f"dispersion_departamental_{universe}.{ext}"
            if plot_dispersion(frames, universe, path, meta, options.dpi):
                _record(options, path, "comparativos", "Dispersión departamental", universe)
    return options.done


def write_index(output: Path, items: list[Output], meta: Meta) -> Path:
    """INDICE.html (thumbnails grouped by section) and LEEME.md."""
    output = Path(output)
    sections = {
        "comparativos": "Comparativos de tasas",
        "nacional": "Tableros nacionales",
        "departamentos": "Tableros por departamento",
    }
    body = []
    for group, heading in sections.items():
        rows = [i for i in items if i.group == group]
        if not rows:
            continue
        body.append(f"<h2>{html.escape(heading)} <small>({len(rows)})</small></h2><div class='grid'>")
        for item in rows:
            rel = item.path.relative_to(output).as_posix()
            label = html.escape(item.title + (f" · {item.universe}" if item.universe else ""))
            thumb = f"<img loading='lazy' src='{html.escape(rel)}' alt='{label}'>" if item.path.suffix == ".png" else "<span>PDF/SVG</span>"
            body.append(f"<figure><a href='{html.escape(rel)}'>{thumb}</a><figcaption>{label}</figcaption></figure>")
        body.append("</div>")
    page = (
        "<!doctype html><html lang='es'><meta charset='utf-8'><title>ICML: gráficos</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;color:#222}h1{margin-bottom:0}"
        ".sub{color:#666;margin-top:4px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}"
        "figure{margin:0}img{width:100%;border:1px solid #ddd;border-radius:4px}figcaption{font-size:13px;margin-top:4px}"
        "small{color:#888;font-weight:normal}</style>"
        f"<h1>ICML: gráficos de la entrega</h1><p class='sub'>Versión {html.escape(meta.version)} · corte {html.escape(meta.cutoff)}"
        f" · {html.escape(meta.run_id)}</p>" + "".join(body) + "</html>"
    )
    index = output / "INDICE.html"
    index.write_text(page, encoding="utf-8")
    (output / "LEEME.md").write_text(
        f"# Gráficos de la entrega {meta.run_id}\n\nVersión {meta.version} · corte {meta.cutoff}. Abra `INDICE.html` en el navegador.\n\n"
        "* `universo_censo/` y `universo_geih/`: un tablero del nacional y uno por departamento "
        "(tasas laborales, niveles, informalidad y composición sectorial).\n"
        "* `comparativos/`: nacional censo contra GEIH, los 33 departamentos en miniatura por tasa, mapas de calor anuales, "
        "ranking del último mes y dispersión departamental.\n\n"
        "Sombreado gris: tramo reconstruido (1993-2000). Línea discontinua: empalme de 2001-01. Franja rosada (GEIH): "
        "meses sin representación del territorio en la GEIH.\n\n"
        "Se generan con `python tools/plots/graficar_entrega.py --carpeta <entrega>`; no cambian ninguna cifra.\n",
        encoding="utf-8",
    )
    return index


def _csv_list(text: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(",") if part.strip()) if text else ()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--carpeta", type=Path, required=True, help="Carpeta de la entrega (la que trae MANIFEST.json)")
    parser.add_argument("--salida", type=Path, help="Destino; por defecto <carpeta>_graficos")
    parser.add_argument("--solo", help=f"Grupos separados por coma: {', '.join(GROUPS)}")
    parser.add_argument("--universo", help="censo, geih o ambos (por defecto ambos)")
    parser.add_argument("--departamentos", help="Códigos DANE separados por coma (por defecto todos)")
    parser.add_argument("--dpi", type=int, default=100)
    parser.add_argument("--formato", choices=("png", "pdf", "svg"), default="png")
    parser.add_argument("--forzar", action="store_true", help="Reemplazar la carpeta de salida si existe")
    args = parser.parse_args(argv)
    groups = _csv_list(args.solo) or GROUPS
    universes = _csv_list(args.universo) or UNIVERSES
    for value, allowed, what in ((groups, GROUPS, "--solo"), (universes, UNIVERSES, "--universo")):
        bad = [v for v in value if v not in allowed]
        if bad:
            parser.error(f"{what}: valores no válidos {bad}; use {list(allowed)}")
    output = args.salida or args.carpeta.parent / f"{args.carpeta.name}_graficos"
    if output.exists():
        if not args.forzar:
            print(f"Ya existe {output}. Use --forzar para reemplazarla.", file=sys.stderr)
            return 2
        shutil.rmtree(output)
    frames, meta = load_frames(args.carpeta)
    options = Options(groups, universes, tuple(_csv_list(args.departamentos)), args.dpi, args.formato)
    items = build_all(frames, output, meta, options)
    if not items:
        print("No se pudo dibujar nada con esas opciones.", file=sys.stderr)
        return 1
    write_index(output, items, meta)
    print(f"{len(items)} gráficos en {output} (abra INDICE.html)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
