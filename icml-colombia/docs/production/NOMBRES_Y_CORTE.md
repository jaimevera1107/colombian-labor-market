# Nombres de los Excel y corte de cálculo

## Principio

**Todo se calcula hasta donde hay información del anexo, y no más.** El corte
no se escribe a mano: es el **último mes para el que existen los dos anexos
mensuales** (mercado laboral e informalidad). Y el nombre de un archivo nunca
decide nada: solo lo clasifica. El período que cuenta es el que el libro
declara **por dentro**, y debe coincidir con el del nombre.

## Carpetas y nombres canónicos

```
datos/1_ingesta/
  geih_mercado_laboral/   geih_mercado_laboral_AAAA-MM.xlsx    anexo mensual
  geih_informalidad/      geih_informalidad_AAAA-MM.xlsx       trimestre móvil que termina en AAAA-MM
  geih_departamentos/     geih_departamentos_AAAA.xlsx         anual; AAAA = último año cubierto
  excel_originales/       referencias que no cambian cada mes (población, PIB, ENH, ...)
  censo_original/
```

Minúsculas, guiones bajos, sin tildes ni espacios, y el período en formato
`AAAA-MM`. Los archivos `.xls` binarios son archivos históricos y **nunca**
deciden el corte.

## Qué nombres se aceptan

Cualquiera de estos funciona; no hace falta renombrar lo que baja del DANE:

| Nombre | Se lee como |
|---|---|
| `geih_mercado_laboral_2026-09.xlsx` | mercado laboral, septiembre de 2026 |
| `Anexo GEIH Septiembre 2026.xlsx` | mercado laboral, septiembre de 2026 |
| `anex-GEIH-sep2026.xlsx` | mercado laboral, septiembre de 2026 |
| `Anexo GEIH Informalidad Septiembre 2026.xlsx` | informalidad, septiembre de 2026 |
| `geih_departamentos_2026.xlsx` | departamental anual, 2026 |

## Qué pasa cuando cambia el mes

1. Se deja el anexo nuevo en `datos/1_ingesta/` (en la carpeta que corresponda, o
   incluso suelto: se busca por nombre en todo el árbol).
2. `python -m icml recalcular --root . --simulacro` muestra el corte detectado.

| Situación | Resultado |
|---|---|
| Llega solo el anexo laboral de septiembre | El corte sigue en agosto; septiembre queda **pendiente**. No se calcula nada de más. |
| Llega el par completo de septiembre | El corte pasa a septiembre (ver el límite de abajo). |
| El nombre dice septiembre pero el libro declara julio | **Bloqueado**: "el nombre dice 2026-09 pero el libro declara 2026-07". |
| Dos archivos distintos reclaman el mismo mes | **Error de ambigüedad**; copias idénticas cuentan como una. |
| Falta el anexo del mes de la corrida | **Bloqueado**: "Faltan los anexos de AAAA-MM". |

El nombre no puede romper el cálculo: o se lee bien, o el sistema dice
exactamente qué archivo y por qué.

## Renombrar lo existente

`tools/release/rename_ingestion.py` aplica la convención a lo que ya está
(simulacro por defecto). No borra nada: las copias idénticas (por ejemplo, el
anexo de agosto estaba dos veces) pasan a `legacy/ingesta_duplicados`, se
verifica el hash tras cada movimiento y se reescriben las rutas en código,
configuraciones y catálogos. El mapa queda en `datos/MAPA_RENOMBRADO_INGESTA.json`.

## Límite que hay que decidir

Un mes **posterior a la vintage congelada** (agosto de 2026) no se puede calcular
todavía, aunque lleguen los dos anexos, y `recalcular` lo dice en vez de calcular
agosto en silencio. Los **priors del MLP** de H9 y el **puente censal** son
parámetros congelados con una fila por mes hasta agosto: para septiembre falta
una regla de extensión (por ejemplo, reentrenar el MLP con semilla fija hasta el
nuevo mes, o guardar y aplicar los pesos del entrenamiento original, y arrastrar
los factores del puente). Es una decisión metodológica, no de ingeniería.
Un mes **anterior** sí se puede reconstruir (ver `SIMULACION_JULIO_AGOSTO.md`).

## Cuadre del residuo entre 2020 y 2021

Entre 2020 y 2021 hubo cambios metodológicos, y desde 2021 cada ventana nueva
re-identifica los meses latentes, de modo que la suma departamental del puente
censal y el empleo nacional **no coinciden exactamente**. Eso no bloquea:

1. Si los niveles del puente difieren del producto laboral vigente en más de
   1e-3 personas, se **refrescan** desde el laboral y el universo GEIH se
   reconstruye de forma jerárquica con los factores congelados (las identidades
   PEA = ocupados + desocupados y PET = PEA + inactivos se mantienen).
2. El residuo que quede se **registra** (`employed_total_residual_people`) y se
   absorbe por la tasa nacional.
3. Solo se detiene ante un desajuste grosero (más del 1 % del empleo nacional),
   que indicaría insumos de vintages distintas y no una brecha metodológica.

Con el corte congelado (agosto) nada cambia: no hay filas desactualizadas.
