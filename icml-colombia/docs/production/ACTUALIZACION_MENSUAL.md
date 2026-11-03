# Consolidar, actualizar y graficar: las tres rutinas y qué esperar

Los comandos (`icml estado`, `consolidar`, `actualizar`, `graficos`, `verificar`) están descritos en el README de la raíz.
Esta nota recoge lo que se **comprobó de punta a punta** en una copia limpia del proyecto, con un entorno creado por el
instalador (sin `torch`), para que quien replique el uso sepa qué cifras y qué avisos son normales.

## Las tres pruebas, tal como se ejecutaron

| # | Comando | Resultado |
|---|---|---|
| 1 | `icml consolidar --desde-cero --hasta 2026-07 --si` | Base de julio: 1993-01 a 2026-07 (806 filas nacionales, 13.299 departamentales). Auditoría 36 de 36. Archivos sencillos creados. La base vigente queda en julio |
| 2 | `icml actualizar` | `SOLO ACTUALIZAR hasta 2026-08`: detecta los dos anexos de agosto como nuevos, calcula y publica. Auditoría 36 de 36 |
| 3 | `icml graficos` | 87 gráficos y `INDICE.html` |

Tiempos aproximados: la prueba 1, 10 a 15 minutos (arma una copia de trabajo cortada en julio y recalcula todo); la prueba
2, unos 8 a 10; la prueba 3, unos 90 segundos. Se ejecutó con el proyecto tal como se entrega: ya traía la base de agosto,
y `--desde-cero` la reemplazó por la de julio (las entregas anteriores se conservan).

## Qué se comprobó de la actualización

Comparando la entrega de agosto (anclada) con la de julio:

* **Años congelados (hasta 2025): 0 celdas distintas** en laboral, informalidad y sectorial, en los dos universos.
* **Año abierto (2026):** cambia, porque entra un mes y se reestima. Enero a julio de 2026, en departamentos: el empleo cambia
  con mediana 0,09 %, percentil 99 de 1,25 % y máximo 1,56 %; la PET, máximo 0,49 %.
* **Lo que se agrega:** 33 filas por producto departamental y 1 por nacional.
* **Equivale a recalcular todo:** el año abierto de la actualización es **idéntico (0,0000 %)** al de un recálculo total de
  agosto.
* **Un escalón pequeño en la unión 2025 → 2026.** Como lo congelado queda como lo dejó la base anterior, la PET suavizada
  tiene en enero de 2026 una curvatura de hasta 0,23 % del nivel (0,06 % en un recálculo total). Es esperable y no es un
  error.

## Qué pasa con los anexos de otros meses

La huella de entradas de una entrega incluye solo los anexos **hasta su corte**. Por eso se puede consolidar hasta julio
teniendo ya el de agosto copiado: agosto aparece luego como entrada nueva de `actualizar` (sin esto, la actualización vería
"sin cambios"). Los anexos posteriores a agosto de 2026 siguen sin poder procesarse (ver la sección 4 del README).

## Avisos que son normales

* `MultipleOptimaWarning: The rho criterion has competing local optima…` en la etapa departamental: la emite la librería de
  desagregación temporal. No viene de los cambios recientes, pero las corridas de desarrollo anteriores se ejecutaron con las
  advertencias silenciadas, así que no hay un registro previo con el que compararla. Las entregas pasan las 36 comprobaciones.
* `FutureWarning … incompatible dtype … bool` al injertar los años congelados (`graft.py`): es de pandas; las cifras
  congeladas salieron idénticas (0 celdas distintas).

## Mensajes de error comunes

| Situación | Qué responde |
|---|---|
| `consolidar` con una base ya publicada y sin `--desde-cero` | Explica que protege la base y ofrece `actualizar` o `--desde-cero` |
| `actualizar` sin base publicada | Pide `consolidar --desde-cero` |
| `actualizar --hasta` un mes anterior al de la base | "No retrocede"; ofrece `consolidar --desde-cero --hasta` |
| `--hasta 2026-13` | Pide el formato AAAA-MM |
| Un mes sin los dos anexos | "No tengo los dos anexos de AAAA-MM" y dice cuál es el último completo |
| Carpeta equivocada | "No encuentro la carpeta del proyecto" |
| `graficos` cuando ya existen | Ofrece `--forzar` |

## Antes de subir a GitHub tras las pruebas

Las pruebas **cambian el proyecto**: agregan entregas en `datos/3_salida/` y cambian la base vigente
(`datos/2_procesamiento/vigente/`). Para volver al estado entregado: `git checkout -- datos` y
`git clean -fd datos/3_salida`. Para subir el estado después de las pruebas, regenerar `SHA256SUMS`
(`python icml-colombia/tools/release/verify_checkout.py --escribir`).
