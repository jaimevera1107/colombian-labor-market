"""Build the nine-city CNPV coverage anchor directly from official legacy XLS.

Usage: python scripts/census/extract_capitals_2018.py <original.xls> <out.csv>
The OLE/BIFF reader is vendored only to parse the official legacy file.
"""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

from _xls_legacy_reader import ole_streams, parse_workbook

CAPITALS = {"81":"81001", "85":"85001", "86":"86001", "88":"88001",
            "91":"91001", "94":"94001", "95":"95001", "97":"97001", "99":"99001"}


def run(source: Path, target: Path) -> None:
    tables = parse_workbook(ole_streams(source)["Workbook"])
    dep = tables["Ajuste por Cobertura CNPV 2018"]
    municipalities = tables["Ajuste por Cobertura CNPV Mpios"]
    depts = {}
    for row in range(9,46):
        code=dep.get((row,0))
        if code is not None:
            code=str(code).zfill(2)
            if code in CAPITALS:
                depts[code] = int(dep.get((row,2)))
    capital = {}
    for row in range(9,1134):
        code=municipalities.get((row,0))
        if code is not None:
            code=str(code).zfill(5)
            if code in CAPITALS.values():
                capital[code] = int(municipalities.get((row,4)))
    if set(depts)!=set(CAPITALS) or set(capital)!=set(CAPITALS.values()):
        raise ValueError("Missing one or more municipality/dept census anchors")
    assert all(depts[c] > capital[CAPITALS[c]]>0 for c in CAPITALS)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["dep_code","cnpv_departamento_ajustado","cnpv_cabecera_capital"])
        writer.writeheader()
        for code in sorted(CAPITALS):
            writer.writerow({"dep_code":int(code),"cnpv_departamento_ajustado":depts[code],
                             "cnpv_cabecera_capital":capital[CAPITALS[code]]})
    print(f"CNPV SHA256 {hashlib.sha256(source.read_bytes()).hexdigest()} | 9 capital cabeceras | {target}")


if __name__=="__main__":
    run(Path(sys.argv[1]),Path(sys.argv[2]))
