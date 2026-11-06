"""H17 safety layer for H16 sectoral experimental output.

Never changes upstream ICML or a frozen research bundle. Publish remains blocked.
"""
from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from icml.domain.cutoff import N_MONTHS, ROWS_33

PANEL_NAME = "16_matriz_mensual_1993_2026_EXPERIMENTAL.csv"
INPUT_NAMES = (
    "12_composicion_nacional_unificada_1993_2026.csv",
    "departamentos.csv",
)


def sha256(path: Path) -> str:
    d=hashlib.sha256()
    with path.open("rb") as stream:
        for b in iter(lambda:stream.read(1024*1024),b""):
            d.update(b)
    return d.hexdigest()


def validate_bundle(root: Path) -> dict:
    """Audit frozen or recomputed H16 outputs; no data modification."""
    root=Path(root)
    out=root/"outputs"
    quality_file=out/"16_puerta_calidad.json"
    if not quality_file.is_file():
        raise FileNotFoundError(quality_file)
    quality=json.loads(quality_file.read_text(encoding="utf-8"))
    if quality.get("can_publish") is not False:
        raise ValueError("H16 publication gate must remain blocked pending external review")
    manifest_file=out/"16_manifest_hashes.json"
    frozen_manifest=json.loads(manifest_file.read_text(encoding="utf-8"))
    for kind in ["inputs","outputs"]:
        for filename,expected in frozen_manifest[f"{kind}_sha256"].items():
            file=root/kind/filename
            if not file.is_file() or sha256(file)!=expected:
                raise ValueError(f"Tampering or missing frozen {kind} file: {file}")
    mat=pd.read_csv(out/PANEL_NAME)
    expected_cols={"period","dep_code","sector_code","sector_share","employed_full_sector","employed_represented_sector_proxy"}
    if not expected_cols.issubset(mat.columns):
        raise ValueError(f"Missing required columns: {expected_cols-set(mat.columns)}")
    if len(mat)!=ROWS_33 * 15 or mat.period.nunique()!=N_MONTHS or mat.dep_code.nunique()!=33 or mat.sector_code.nunique()!=15:
        raise ValueError("H16 panel dimensions differ from expected frozen vintage")
    if mat[["period","dep_code","sector_code"]].duplicated().any():
        raise ValueError("Duplicate period-department-sector rows")
    for col in ["sector_share","employed_full_sector","employed_represented_sector_proxy"]:
        if not np.isfinite(mat[col]).all():raise ValueError(f"Nonfinite {col}")
    if not mat.sector_share.between(-1e-12,1+1e-12).all():
        raise ValueError("Invalid sector shares")
    sums=mat.groupby(["period","dep_code"],sort=False).agg(
        share=("sector_share","sum"),full=("employed_full_sector","sum"),
        represented=("employed_represented_sector_proxy","sum"))
    max_share=float((sums.share-1).abs().max())
    if max_share>1e-8:raise ValueError("Share closures failed")
    dep=pd.read_csv(root/"inputs"/"departamentos.csv",usecols=["period","dep_code","employed","employed_represented"])
    if dep[["period","dep_code"]].duplicated().any():raise ValueError("Duplicate department source rows")
    d=sums.reset_index().merge(dep,on=["period","dep_code"],validate="one_to_one")
    if len(d)!=len(sums):raise ValueError("Missing department inputs")
    max_full=float((d.full-d.employed).abs().max())
    max_rep=float((d.represented-d.employed_represented).abs().max())
    nat=pd.read_csv(root/"inputs"/"12_composicion_nacional_unificada_1993_2026.csv")
    totals=dep.groupby("period",as_index=False).employed.sum().rename(columns={"employed":"total"})
    reference=nat.merge(totals,on="period",validate="many_to_one")
    reference["target"]=reference.total*reference.sector_share
    obtained=mat.groupby(["period","sector_code"],as_index=False).employed_full_sector.sum()
    checking=reference.merge(obtained,on=["period","sector_code"],validate="one_to_one")
    if len(checking)!=len(reference):raise ValueError("Missing national-sector margins")
    max_nat=float((checking.target-checking.employed_full_sector).abs().max())
    if max(max_full,max_rep,max_nat)>1e-4:raise ValueError("Accounting margins outside tolerance")
    report={"status":"EXPERIMENTAL_NOT_CANONICAL", "can_publish":False,
        "months":int(mat.period.nunique()),"departments":int(mat.dep_code.nunique()),
        "sectors":int(mat.sector_code.nunique()),"cells":len(mat),
        "max_share_error":max_share,"max_department_full_error_persons":max_full,
        "max_department_represented_error_persons":max_rep,
        "max_national_sector_error_persons":max_nat,
        "input_output_sha256_verified":True}
    return report


def run_predictor(bundle_root: Path, output_root: Path) -> dict:
    """Run model in a new independent directory, never overwrite frozen references."""
    bundle_root=Path(bundle_root).resolve()
    output_root=Path(output_root).resolve()
    if bundle_root==output_root or output_root.is_relative_to(bundle_root):
        raise ValueError("Input bundle and output root must be different and non-overlapping")
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output root is not empty: {output_root}")
    source=bundle_root/"inputs"
    if not source.is_dir():raise FileNotFoundError(source)
    output_root.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,output_root/"inputs",dirs_exist_ok=True)
    from icml.sectoral.predictive_integration import main
    quality=main(output_root)
    validated=validate_bundle(output_root)
    return {"selection":quality.get("chosen_model"),"audit":validated,
            "output_root":str(output_root)}


def export_experimental(bundle_root: Path, output_root: Path) -> dict:
    """Export an explicitly noncanonical departmental/national sectoral product.

    Existing ICML labor bases, city products and input research vintages are never
    written to. Exported represented national totals are sums of department proxies,
    NOT official DANE national margins.
    """
    root=Path(bundle_root).resolve()
    dest=Path(output_root).resolve()
    if dest==root or dest.is_relative_to(root):
        raise ValueError("Output cannot be the source research bundle or inside it")
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"Output root is not empty: {dest}")
    audit=validate_bundle(root)
    dest.mkdir(parents=True,exist_ok=True)
    source=root/'outputs'/PANEL_NAME
    target=dest/'sectorial_departamental_1993_2026_EXPERIMENTAL.csv'
    shutil.copyfile(source,target)
    df=pd.read_csv(source,usecols=['period','sector_code','employed_full_sector','employed_represented_sector_proxy'])
    cols=['period','sector_code']
    national=df.groupby(cols,as_index=False).agg(
        occupied_full=('employed_full_sector','sum'),
        occupied_represented_department_proxy=('employed_represented_sector_proxy','sum'))
    national['share_full']=national.occupied_full/national.groupby('period').occupied_full.transform('sum')
    national['share_represented_department_proxy']=(
        national.occupied_represented_department_proxy/
        national.groupby('period').occupied_represented_department_proxy.transform('sum')
    )
    national['source_status']='H11_NATIONAL_COMPOSITION_EXPERIMENTAL_OR_ASSUMED_SPLIT'
    national['publication_status']='NO_CANONICAL'
    national.to_csv(dest/'sectorial_nacional_1993_2026_EXPERIMENTAL.csv',index=False,float_format='%.12g',lineterminator='\n')
    metadata={**audit,'source_panel_sha256':sha256(source),
        'export_panel_sha256':sha256(target),
        'national_export_rows':len(national),
        'represented_national_is_department_proxy_not_dane_official':True,
        'city_level_sectorial_not_available':True,
        'no_canonical_data_modified':True}
    (dest/'METADATOS_EXPERIMENTALES.json').write_text(
        json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return metadata
