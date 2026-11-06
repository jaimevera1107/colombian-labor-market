# ICML 2.1.2.dev0 — Contrato de las tres bases laborales

## Productos públicos exclusivos de la etapa `quality`

- `quality/products/ciudades.csv`: 33 unidades por mes. Son **32 ciudades o áreas urbanas** más la **señal urbana sintética de Cundinamarca**. La sintética no se presenta como observación oficial; no sumar ciudades para obtener el país.
- `quality/products/departamentos.csv`: 33 unidades por mes (32 departamentos y Bogotá). Es el universo territorial completo; **su suma de niveles** define el nacional ICML y no pierde ningún territorio por ausencia de referencia.
- `quality/products/nacionales.csv`: **dos filas por mes**, `national_type=ICML_COMPLETO` y `national_type=DANE_REFERENCIA`, ambas con `dep_code="00"`. Clave: `(national_type, period)`. Nunca sumar ambas filas.

Cobertura de los tres productos: **1993-01 a 2026-08** (404 meses). Los seis niveles obligatorios, sin NA ni infinitos en ninguna fila: `population`, `working_age` (PET), `labor_force` (PEA), `employed`, `unemployed`, `inactive`.

## Nacionales no equivalentes

`ICML_COMPLETO` = suma **no ponderada** de las 33 estimaciones territoriales completas; el nacional ICML no se fuerza a coincidir con la referencia DANE. `DANE_REFERENCIA` = serie nacional que entregó `national_icml.csv` bajo los prefijos `dane_*`; para `2001-01` en adelante, referencia GEIH utilizada por ICML. **1993-01 a 2000-12 no contiene observaciones GEIH nacionales oficiales:** la cifra es una *referencia nacional histórica reconstruida*, señalada por `reference_status=HISTORICO_RECONSTRUIDO_NO_OFICIAL` e `is_official_observation=false`.

## Regla nueva de factores en los 33 departamentos

Para **cada período anterior a 2001-01**, `factor_* = 1.0` para las seis magnitudes, `*_represented = *` (nivel completo), y `factor_reference_status=SIN_REFERENCIA_GEIH_FACTOR_IDENTIDAD`. Esta identidad es una **convención de conservación de la reconstrucción**, no evidencia de inclusión en la GEIH. En los años posteriores se conservan sin cambio los factores de cobertura y la conciliación aprobada en 2.1.0. Algunos territorios tienen factor 0 hasta la ampliación GEIH de 2014; **siguen estando presentes con sus seis magnitudes y siguen sumando al nacional ICML**. Solo la suma representada frente al DANE utiliza factores, desde 2001.

En la base nacional, los factores del nacional ICML también son 1 antes de 2001; desde 2001 son la relación referencia/ICML correspondiente. El nacional DANE_REFERENCIA tiene factores identidad para todas las fechas.

## Reglas de calidad y prohibiciones

1. 33 ciudades/señales + 33 departamentos, 404 meses completos, sin duplicados; dos series nacionales en los mismos meses.
2. Ningún nulo, infinito o componente laboral negativo. `labor_force = employed + unemployed` y `working_age = labor_force + inactive` a tolerancia numérica; `working_age <= population`.
3. Antes de 2001, todos los factores departamentales y nacionales iguales a 1 y representación completa. Después de 2001, se preserva el contrato de representación frente a GEIH.
4. El nacional ICML se calcula desde los niveles completos (`groupby(period).sum()` de 33 departamentos), **jamás** desde la suma representada.
5. Los códigos de territorio deben importarse como texto (`dtype={'dep_code': 'string', 'city_code': 'string'}`) para preservar los ceros iniciales. El nacional solo se encuentra en `nacionales.csv`, código `00`.
6. Ningún cambio a los seis niveles estimados de 2.1.0; este cambio corrige la política de los factores históricos y organiza las exportaciones. El paquete 2.1.0 y su hash quedan intactos.
7. Las alertas preexistentes de linealidad y cambios estructurales **no** se consideran resueltas por la nueva exportación. El estado de publicación sigue `REQUIERE_REVISION_METODOLOGICA` hasta su cierre documentado.

## Ejemplo

```python
import pandas as pd
from pathlib import Path
p = Path('quality/products')
ciudades = pd.read_csv(p/'ciudades.csv', dtype={'city_code':'string','dep_code':'string'})
departamentos = pd.read_csv(p/'departamentos.csv', dtype={'dep_code':'string'})
nacionales = pd.read_csv(p/'nacionales.csv', dtype={'dep_code':'string'})
nac_icml = nacionales.query("national_type == 'ICML_COMPLETO'")
nac_ref = nacionales.query("national_type == 'DANE_REFERENCIA'")
```

La etapa de calidad se ejecuta sobre los cuatro insumos canónicos de conciliación, escribe estos tres productos y ejecuta las auditorías sin cambiar las fuentes previas. Los outputs auxiliares/auditorías se conservan en `/audit`, no constituyen cuartas bases para análisis.
