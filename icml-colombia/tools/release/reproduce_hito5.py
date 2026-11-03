"""Reproduce Hito 5 from two frozen CSVs without rerunning the labor models.

Run from project root. Outputs are immutable, separately hashed and
fully disjoint from national/urban/departmental labor outputs.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from icml.config import config_sha256
from icml.informality.national import InformalityNationalPipeline, load_informality_config
from icml.io.artifacts import ArtifactStore
from icml.pipeline.manifest import RunManifest, validate_run_id
from icml.informality.national import QUALITY_NATIONALS


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--nacionales', type=Path,required=True)
    parser.add_argument('--sources',type=Path,default=Path('data/sources/informality'))
    parser.add_argument('--config',type=Path,default=Path('configs/rc1/informality.toml'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.nacionales.is_file():raise FileNotFoundError(args.nacionales)
    if args.output.exists():raise FileExistsError(f'Vintage already exists: {args.output}')
    # The quality ArtifactSpec has a stable `products/nacionales.csv` path.
    # This portable adapter links the existing read-only CSV, not a copy.
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        target=Path(temp)/QUALITY_NATIONALS.relative_path
        target.parent.mkdir(parents=True,exist_ok=True)
        # Symlinks are optional on Windows, so a byte-exact copy is used here.
        import shutil
        shutil.copyfile(args.nacionales,target)
        result=InformalityNationalPipeline(load_informality_config(args.config)).run(
            args.sources,ArtifactStore(Path(temp)),ArtifactStore(args.output))
    run_id=validate_run_id(args.output.name)
    manifest=RunManifest(run_id=run_id,stage='informality',
       config_sha256=config_sha256(args.config),inputs=result.inputs,outputs=result.outputs)
    manifest.write(args.output/'manifest.json')
    print(f'Hito 5 written to {args.output} ({result.diagnostics["status"]})')

if __name__=='__main__':main()
