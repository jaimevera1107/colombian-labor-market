# ICML v2.6.1 — How to test it and publish it

The repository is **complete**: code, data, frozen references, and everything needed to rebuild the August 2026 delivery and its figures. Tests are reviewed and undone with Git.

## 0. Install (once)

1. Install **Python 3.11 or later**.
2. Clone the repository and enter its folder.
3. Run the installer (needs internet and a few minutes; it creates `.venv` and installs the package from PyPI; add `--locked` for the exact pinned environment):
   * Linux or macOS: `./install.sh`
   * Windows: double-click `install.bat`
4. Check:

   ```
   ./icml.sh status        # Windows cmd: icml status     PowerShell: .\icml status
   ./icml.sh checksums     # every versioned file is intact
   git status              # should say: nothing to commit, working tree clean
   ```

   `status` lists the annexes through 2026-08 and, on a fresh clone, "Published base: none yet" (the products are generated locally, see step 1).

## 1. Rebuild from scratch with the July annexes

```
./icml.sh rebuild --through 2026-07 --yes
```

* `rebuild` **always starts over**; when a base is already published it asks for confirmation, and `--yes` answers it.
* `--through 2026-07` uses the annexes through July only and **ignores** the August ones already in the folder.
* `--dry-run` shows the plan without computing anything.

It takes 10 to 15 minutes, ends with `Audit: PASS (52 of 52 checks)`, creates the delivery and the simple files, and leaves July as the published base (`./icml.sh status` confirms it).

## 2. Incremental update: the new month only (August)

```
./icml.sh update --through 2026-08       # same as: ./icml.sh update
```

It prints `UPDATE ONLY through 2026-08`, sees the two August annexes as new, **freezes the anchored years (through 2025)** and recomputes only the open ones. It takes 8 to 10 minutes and ends with `Audit: PASS (52 of 52 checks)`.

What to expect (checked on a clean copy): between the July base and the August base there are **0 different cells through 2025**; in 2026 departmental employment changes with median 0.09 % (maximum 1.56 %) because one month enters. Running it again answers "Already up to date". `--dry-run` shows the plan without computing.

## 3. Figures

```
./icml.sh plots
```

Draws the published delivery (87 images, about 90 seconds) into `datos/3_salida/<delivery>_plots/`; open `index.html` in the browser. Options: `--only nacional,comparativos`, `--universe census`, `--departments 05,11`, `--force` (replace).

## Other commands

| Command | Purpose |
|---|---|
| `icml status` | What is there and what the next step is |
| `icml verify` | Audit the latest delivery again (52 checks) |
| `icml checksums` | Verify the checkout against `SHA256SUMS` (`--write` regenerates it) |
| `icml <command> --help` | Options of each command |

## After the tests: review, undo or publish

The tests **add deliveries** in `datos/3_salida/` and **change the published base** (`datos/2_procesamiento/vigente/`). Both are ignored by Git, so a clean tree is one command away:

```
git status                                           # what changed
git clean -fd datos/3_salida datos/2_procesamiento/vigente   # back to the state of the checkout
```

**Publishing** a change (a new annex, a fix) to GitHub:

1. Regenerate the hash listing: `./icml.sh checksums --write`.
2. `git add -A && git commit -m "Delivery YYYY-MM"`.
3. `git push`.

## If something fails

Every usage mistake prints a plain message with what to do. The most common ones:

| Message | What to do |
|---|---|
| "The environment is missing" | Run the installer (step 0) |
| Rebuild asks for confirmation | Use `update`, or `rebuild --yes` |
| "Both annexes of YYYY-MM are not available" | Copy the missing annex into `datos/1_ingesta/` |
| "... already exists. Use --force" | Add `--force` to `icml plots` |

License: MIT (`LICENSE`). More detail: `README.md` and `docs/production/MONTHLY_UPDATE.md`.
