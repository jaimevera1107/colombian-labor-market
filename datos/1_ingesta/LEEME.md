# Ingesta: anexos DANE y referencias

Aquí se dejan los Excel. **El período se lee del contenido del libro; el nombre solo lo clasifica.**

| Carpeta | Contenido | Nombre canónico |
|---|---|---|
| `geih_mercado_laboral/` | Anexo mensual de mercado laboral de la GEIH | `geih_mercado_laboral_AAAA-MM.xlsx` |
| `geih_informalidad/` | Anexo de informalidad (trimestre móvil que termina en el mes) | `geih_informalidad_AAAA-MM.xlsx` |
| `geih_departamentos/` | Anexo anual departamental (AAAA = último año cubierto) | `geih_departamentos_AAAA.xlsx` |
| `excel_originales/` | Referencias que no cambian cada mes (población, PIB, ISE, ENH, anexos sectoriales) | nombre original |
| `censo_original/` | CNPV 2018 ajustado por cobertura | nombre original |

También sirven los nombres del DANE (`Anexo GEIH Septiembre 2026.xlsx`, `anex-GEIH-sep2026.xlsx`). El corte es el
último mes con **los dos** anexos mensuales; un mes con un solo anexo queda pendiente. Si el nombre y el contenido no
coinciden, la ejecución se bloquea con el nombre del archivo. Detalle: `icml-colombia/docs/production/NOMBRES_Y_CORTE.md`.
