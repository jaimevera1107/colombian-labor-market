# Publishing on GitHub

The repository holds everything needed to rebuild the deliveries (code, inputs, frozen parameters), about 100 MB, no Git LFS: anyone who downloads it, even as a ZIP, gets all of it. Deliveries, figures and the published base are generated locally and ignored by Git.

## Check a copy

From the root of any copy: `icml checksums`. It compares every versioned file with `SHA256SUMS` and reports what is missing or altered. `sha256sum -c SHA256SUMS` does the same on Linux/macOS.

## Monthly backup

After recalculating and verifying a delivery:

```
icml checksums --write
git add -A
git commit -m "Delivery YYYY-MM"
git push
```

Earlier deliveries are never deleted locally: the latest one is the reference of the next anchored recalculation.

## Continuous integration

`.github/workflows/tests.yml` installs the package from PyPI on Python 3.11, 3.12 and 3.13 (job `tests`) and also in the locked environment of the reference vintage (job `reproducible`); both run the test suite, and `tests` runs the dry run of the monthly plan (`icml recalc --root . --dry-run`), on every push and pull request. The RC1 golden references are not in the repository, so the 46 golden regression tests skip automatically.

## License

MIT (`LICENSE`, also declared in `pyproject.toml`).
