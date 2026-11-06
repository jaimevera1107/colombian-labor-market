# Nueva estructura: ingesta, procesamiento, salida y legacy

## Carpetas

```
<raíz del proyecto>/
  icml-colombia/              código, configuraciones, pruebas y documentación
  datos/
    1_ingesta/                Excel que usted mantiene (anexos DANE, censo, series originales)
    2_procesamiento/          lo que produce el programa: CSV preparados, parámetros
                              congelados, productos congelados, catálogos
    3_salida/                 entregas por universo, una carpeta por ejecución
    MAPA_MIGRACION.json       cada archivo: ruta vieja, ruta nueva y SHA-256
  legacy/                     referencias y duplicados sin uso (nada se borró)
  dependencias/               rueda de tempdisagg (necesaria para instalar)
```

`legacy/validacion/rc1_original` contiene la referencia RC1 que usan las 131
pruebas Golden: apunte `ICML_GOLDEN_DIR` ahí.

Los anexos DANE de meses anteriores quedaron en
`1_ingesta/excel_originales/Mercado Laboral/Anteriores/` y **no** en `legacy/`,
porque son el material con el que se comprueban revisiones del DANE.

## Cómo se aplica

```
cd icml-colombia && patch -p1 < codigo_nueva_estructura.patch     # código y pruebas
cd .. && python icml-colombia/tools/release/reorganize_layout.py --root .          # simulacro
python icml-colombia/tools/release/reorganize_layout.py --root . --aplicar         # mueve
```

La herramienta solo mueve (nunca borra), verifica el SHA-256 en el destino, se
detiene si algún archivo no tiene regla, y avisa si queda escrito en el código el
nombre de una carpeta renombrada (`exit 3`). Es idempotente.

## Entregas por universo

Cada ejecución crea `datos/3_salida/AAAA-MM-DD_HHMMSS_corte-AAAA-MM_modo/`
(hora de Bogotá) con `universo_censo/` y `universo_geih/`; dentro, `laboral/`,
`informalidad/` y `sectorial/`, y en cada una nacional, ciudades y departamentos
(sectorial: solo nacional y departamentos). El nombre de cada archivo repite el
corte y la marca de tiempo. `MANIFEST.json` guarda los hashes y el mapa de
columnas original → entregada.

* **Censo** = territorio completo (población CNPV 2018, `ICML_COMPLETO`).
* **GEIH** = la parte que la GEIH representa. Su nacional laboral es la cifra
  publicada por el DANE; las columnas `represented_sum_*` y
  `gap_published_minus_sum_*` la comparan con la suma de los departamentos
  representados. Coinciden desde 2014; antes difieren por la reconstrucción y la
  entrada de las nueve capitales.
* **Ciudades**: la misma serie en ambas carpetas (dominios urbanos GEIH, señales
  no aditivas). No existe una serie censal de ciudades y no se inventa.
* El sectorial es experimental y su serie representada es un proxy.

```
python -m icml entrega construir --desde-corrida <carpeta de run-integral> --salida datos/3_salida [--excel]
python -m icml entrega verificar --carpeta datos/3_salida/<ejecución>
```

## Recálculo

```
python -m icml recalcular --root . --simulacro          # solo muestra el plan
python -m icml recalcular --root .                      # anclado (por defecto)
python -m icml recalcular --root . --modo total --confirmar-total
```

* **Anclado.** Los años que cubre el anexo departamental (hoy hasta 2025) quedan
  **congelados completos**: se toman de la entrega vigente y nunca se
  reescriben. Los años posteriores se recalculan. Al llegar un anexo nuevo
  (por ejemplo el de 2026 en abril de 2027) se agrega como archivo nuevo en
  `1_ingesta/` y el año ancla avanza.
* **Se bloquea** si cambia un parámetro congelado o si se modifica un insumo que
  ya existía (misma ruta, otro contenido); `--aceptar-modificados` lo permite
  cuando no toca años anclados.
* **Total.** Reescribe todo, incluidos los años anclados; exige
  `--confirmar-total`.
* Sin cambios en los insumos, el modo anclado responde `SIN_CAMBIOS` y no
  calcula nada.

## Límites conocidos

* El corte (`FROZEN_CUTOFF`, 2026-08) sigue siendo una constante: el recálculo
  reproduce la vintage de agosto; **no** procesa todavía un mes nuevo. Septiembre
  requiere además el anexo de Empleo Informal y Seguridad Social julio–septiembre.
* El modo anclado detecta cambios por hash de archivo. No compara aún el
  contenido de las cifras oficiales entre dos publicaciones (existe la
  compuerta `check_frozen_observations`, sin conectar a los anexos reales).
* No son estadísticas oficiales; H9 sigue sin validación científica independiente.
