<div align="center">

  # ICML

  **Colombian Labor Market Conditions Indicators**

  *Reconstruction, monthly update and validation of Colombian labor-market series.*

  [![Version](https://img.shields.io/badge/version-2.6.0-183153?style=flat-square)](CHANGELOG.md)
  ![Cutoff](https://img.shields.io/badge/cutoff-2026--08-536779?style=flat-square)
  ![Python](https://img.shields.io/badge/Python-3.11%2B-376994?style=flat-square)
  [![License](https://img.shields.io/badge/license-MIT-536779?style=flat-square)](LICENSE)
  ![Use](https://img.shields.io/badge/use-research-687687?style=flat-square)

  [**Quick start**](#quick-start) · [**Commands**](#commands) · [**Monthly update**](#monthly-update) · [**Scope and limits**](#scope-and-limits) · [**Documentation**](#documentation)

</div>

---

ICML assembles monthly series of **labor market, informality and sectoral employment** for **33 Colombian territories**, from **January 1993**, in two universes:

- **Census:** coverage of the whole territory.
- **GEIH:** coverage of the population represented by the Gran Encuesta Integrada de Hogares.

The repository holds the code, the inputs, the frozen processing parameters, the tests and the delivery pipeline, so research results can be **rebuilt and verified** without any external file.

> [!IMPORTANT]
> **ICML results are research products and are not official DANE statistics.** This is version **2.6.0**, with cutoff **2026-08**.

## At a glance

| Dimension | Scope |
|:--|:--|
| **Period** | Monthly series from `1993-01` |
| **Territorial coverage** | 33 territories; national and departmental dashboards |
| **Universes** | Census and GEIH |
| **Content** | Labor market, informality and employment by sector |
| **Periodic inputs** | Two DANE annexes of the same month |
| **Quality** | 52 automatic checks per delivery |
| **Latest documented version** | `2.6.0` · cutoff `2026-08` |

## Quick start

### 1. Prepare the environment

**Python 3.11 or later.** From the project root, run the installer:

| System | Install | Example |
|:--|:--|:--|
| Windows · PowerShell | double-click `install.bat` | `.\icml status` |
| Windows · CMD | double-click `install.bat` | `icml status` |
| Linux / macOS | `./install.sh` | `./icml.sh status` |

The installer creates `.venv` and installs ICML like any library: `pip install -e ".[dev]"`, with every dependency (including `tempdisagg`) resolved from PyPI within the ranges declared in `pyproject.toml`. **You do not need to activate the environment to use the `icml` shortcut.**

To reproduce the exact environment the reference vintage was frozen with (Python 3.12, versions pinned in `requirements/lock-py312.txt`), run `./install.sh --locked` or `install.bat --locked`. The eight frozen products are the same under both environments (see CHANGELOG 2.6.0).

### 2. Check the status

```powershell
.\icml status
```

It lists the available annexes, the published base and the next step. On a fresh clone there is no published base yet: the products are generated locally.

### 3. Run the whole flow

To rebuild everything from scratch through July, update with August and draw the figures:

```powershell
.\icml rebuild --through 2026-07 --yes
.\icml update
.\icml plots
```

Or, equivalently, with `python -m icml` (useful when working on the package without the wrapper):

```bash
python -m icml rebuild --root . --through 2026-07 --yes
python -m icml update --root .
python -m icml plots --root .
```

This flow **rebuilds and publishes** a base. Read the precautions and checks in [TESTING.md](TESTING.md) first. To see what a command would do without computing anything, add `--dry-run`.

> In the examples below `icml` is a generic name. In PowerShell type `.\icml`; in Linux/macOS, `./icml.sh`.

## Commands

| Goal | Command |
|:--|:--|
| Inputs, status and next step | `icml status` |
| Rebuild the whole history from scratch | `icml rebuild` |
| Rebuild through a given month | `icml rebuild --through 2026-07` |
| Update the published base with the processable months | `icml update` |
| Draw the latest delivery | `icml plots` |
| Run the delivery audits again | `icml verify` |
| Verify the checkout against `SHA256SUMS` | `icml checksums` |
| Show what a command would do | `icml <command> --dry-run` |
| Options of a command | `icml <command> --help` |

When an operation would replace the published base, `rebuild` asks for confirmation; `--yes` skips the question (required when there is no terminal, as in CI). `update` never asks.

### Rebuild versus update

| | Rebuild: `rebuild` | Update: `update` |
|:--|:--|:--|
| **Use** | First build, restart, or a methodological change | Add processable months to an existing base |
| **History** | Recomputes the period from 1993 | Keeps the years anchored by the departmental annex frozen (through 2025) |
| **Prerequisite** | The inputs of the period | A previously published base |
| **Control** | Confirmation, audit and a new delivery | Audit of the delivery; never goes back to an earlier cutoff |

A full rebuild takes **10 to 15 minutes**. When a cutoff earlier than the current one is requested, the program prepares a working copy without modifying the original inputs in `datos/`.

## Monthly update

The routine uses **two official DANE Excel files of the same month**:

| Input | Source | Location in the project |
|:--|:--|:--|
| Labor market (GEIH) | Labor-market annexes | `datos/1_ingesta/geih_mercado_laboral/` |
| Informality and social security | GEIH informality annexes | `datos/1_ingesta/geih_informalidad/` |

**Procedure:**

1. Download both annexes of the **same month**. The informality annex may be published after the labor-market one; without both, that month is not computed.
2. Place each file in its folder. Renaming is not required: the month is read inside the workbook. Keep the annexes of earlier periods.
3. Check the inputs with `icml status` and, if the month is supported by the model, run `icml update`.
4. Review the audit result (`PASS` or the detail of the failures). They can be repeated with `icml verify`.
5. Optionally run `icml plots` and keep the folders of the full delivery, the simple files and the figures.

```powershell
.\icml status
.\icml update --dry-run
.\icml update
.\icml plots
```

> [!NOTE]
> **Months after August 2026.** The frozen parameters (census bridge, informality priors, national sectoral composition) are frozen through `2026-08`. For a later month they are carried forward with explicit rules and the products say so (`prior_provenance`, `source_status`); see [EXTENSION_BEYOND_FROZEN_CUTOFF.md](docs/production/EXTENSION_BEYOND_FROZEN_CUTOFF.md). The first real month after August is the first end-to-end test of that path: run `icml update --dry-run` first and review the manifest.

### Figures

```bash
icml plots
icml plots --only national,comparatives --universe census
icml plots --departments 05,11
```

A `<delivery>_plots/` folder is created with national, departmental and comparative figures; `index.html` browses them. **Drawing never changes a number.** See [PLOTS.md](docs/production/PLOTS.md).

## Scope and limits

The validity of the series depends on the universe, the historical coverage and the documented methodological decisions. In particular:

- **Representativeness differences:** in the GEIH universe the rates of nine territories stay empty between 2001 and 2013 (Arauca, Casanare, Putumayo, San Andrés, Amazonas, Guainía, Guaviare, Vaupés and Vichada) because the survey did not represent them then. **They are not accidental gaps.**
- **Months after `2026-08`:** processed with frozen parameters carried forward and tagged; no re-estimation of the informality priors or the census bridge.
- **A new annual departmental annex:** the anchored year comes from the configured file (`geih_departamentos_2025.xlsx`). Adding a new annex is **not** a matter of copying it: the configuration has to change and a total recalculation has to run.
- **Methodological changes:** changes that touch closed years need a new version, a changelog entry and a controlled total recalculation.

Advanced total recalculation after a methodological change:

```bash
icml recalc --root . --mode total --confirm-total
```

### Reproducibility rules

- Never edit or delete files under `datos/1_ingesta/` or `datos/2_procesamiento/`.
- Never delete historical deliveries from `datos/3_salida/`: the latest one is the reference of the next recalculation.
- Never run two recalculations at the same time.
- Never modify `configs/` without assessing the effect on the historical reconstruction.

### Frequent messages

<details>
<summary><strong>Usual messages and what to do</strong></summary>

| Message or situation | Explanation / action |
|:--|:--|
| Rebuild asks for confirmation | A base is already published. Use `update` to add a month, or confirm (`--yes`) to rebuild. |
| There is no published base to update | Run `rebuild` first. |
| Both annexes of the month are not available | Add the missing annex before processing. |
| The annexes reach past `2026-08` | They are processed; the frozen parameters are carried forward and the products say so. |
| "Already up to date" | No new processable months. |
| `BLOCKED: An existing input was modified` | If it is an intentional DANE correction, see `icml recalc --root . --accept-modified`. |
| The file name and the month inside the workbook disagree | Fix the name or use the file of the right month. |
| Two files declare the same month | Keep only the valid annex. |

Excel lock files (`~$` prefix) are ignored. `icml recalc` and `icml delivery` remain available for advanced administration.

</details>

## Repository layout

```text
.
├── README.md, TESTING.md, CHANGELOG.md, LICENSE
├── install.sh / install.bat        # create .venv with the pinned versions
├── icml.sh / icml.bat              # run icml without activating .venv
├── pyproject.toml                  # package metadata and dependency ranges
├── requirements/                   # locked environment of the reference vintage (optional, --locked)
├── SHA256SUMS                      # hash of every versioned file (icml checksums)
├── configs/                        # stage configurations of the reference vintage (rc1) and the golden catalog
├── src/icml/                       # the package (see docs/production/ARCHITECTURE.md)
├── tests/                          # unit and regression tests
├── tools/                          # maintainer scripts (vintage root, census anchor extractor)
├── docs/                           # methodology and operations
└── datos/
    ├── 1_ingesta/                  # DANE annexes and original workbooks (never edited)
    ├── 2_procesamiento/            # prepared sources, frozen parameters and products, published base
    └── 3_salida/                   # deliveries, simple files and figures (generated locally)
```

The repository ships the source code, the tests, the documentation, the input annexes and the frozen parameters (about **100 MB**, no Git LFS). Deliveries, figures and the published base are generated locally by `icml rebuild`. The folder names under `datos/` are deliberately unchanged: hundreds of versioned manifests and catalogs record those paths and the integrity checks depend on them.

To check the integrity of a downloaded copy:

```bash
sha256sum -c SHA256SUMS      # Linux / macOS
icml checksums               # any system with Python
```

The standard installer does not include `torch`; three tests of the informality MLP experiment need it: `pip install -e ".[ml]"`.

## Publishing and backups

Every delivery is a reproducible version of the results. Before committing, refresh the hash listing and run the integrity check:

```bash
icml checksums --write
git add -A
git commit -m "Delivery YYYY-MM"
git push
```

See [PUBLISHING.md](docs/production/PUBLISHING.md) for the first push and the organization of the deliveries.

## Documentation

| Document | Content |
|:--|:--|
| [TESTING.md](TESTING.md) | Guided exercise: rebuild through July, update with August, draw and publish |
| [Processing framework](docs/PROCESSING_FRAMEWORK.md) | Rules, gates and operation of the processing |
| [Technical index](docs/README.md) | Navigation of the project documentation |
| [Architecture](docs/production/ARCHITECTURE.md) | Package layout, command groups and data flow |
| [Monthly update](docs/production/MONTHLY_UPDATE.md) | Operational guide of the monthly cycle |
| [Labor reconstruction](docs/production/RECONSTRUCCION_LABORAL.md) | PET, population and 1993–2000 components (Spanish) |
| [Changelog](CHANGELOG.md) | Version history |

---

<div align="center">

**ICML 2.0** · Research project on the Colombian labor market

**Author:** Jaime A. Vera-Jaramillo · **License:** [MIT](LICENSE)

</div>
