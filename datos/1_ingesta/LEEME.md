# Ingestion: DANE annexes and references

Drop the Excel files here. **The period is read from the content of the workbook; the name only classifies it.**

| Folder | Content | Canonical name |
|---|---|---|
| `geih_mercado_laboral/` | Monthly GEIH labor-market annex | `geih_mercado_laboral_YYYY-MM.xlsx` |
| `geih_informalidad/` | Informality annex (moving quarter ending in the month) | `geih_informalidad_YYYY-MM.xlsx` |
| `geih_departamentos/` | Annual departmental annex (YYYY = last year covered) | `geih_departamentos_YYYY.xlsx` |
| `excel_originales/` | References that do not change monthly (population, GDP, ISE, ENH, sectoral annexes) | original name |
| `censo_original/` | CNPV 2018 adjusted by coverage | original name |

DANE's own names also work (`Anexo GEIH Septiembre 2026.xlsx`, `anex-GEIH-sep2026.xlsx`). The cutoff is the last month with **both** monthly annexes; a month with one annex stays pending. If the name and the content disagree, the run stops and names the file. Detail: `docs/production/FILE_NAMES_AND_CUTOFF.md`.
