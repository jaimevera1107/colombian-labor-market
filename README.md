# ICML 2.0 — Guía de uso

Repositorio: <https://github.com/jaimevera1107/colombian-labor-market>

Series mensuales de mercado laboral, informalidad y empleo por sector para los 33 territorios de Colombia, desde
1993-01, en dos universos (**censo**: territorio completo; **GEIH**: lo que la GEIH representa). Versión **2.4.0.dev0**,
corte vigente **2026-08**. Son resultados de investigación, no estadísticas oficiales.

**En una frase:** se dejan los dos Excel del DANE de cada mes en una carpeta, se corre `actualizar` y se recoge la entrega.

## Los comandos

Se ejecutan **desde la carpeta del proyecto**. El atajo `icml` no necesita activar el entorno:

| Sistema | Cómo se escribe |
|---|---|
| Linux o Mac | `./icml.sh <comando>` |
| Windows (cmd) | `icml <comando>` |
| Windows (PowerShell) | `.\icml <comando>` |

| Quiero… | Comando |
|---|---|
| Ver qué hay en el proyecto y qué sigue | `icml estado` |
| **Construir la base desde cero** (primera vez, o **forzar recomenzar todo**) | `icml consolidar --desde-cero` |
| Construir la base solo hasta un mes (por ejemplo julio) | `icml consolidar --desde-cero --hasta 2026-07` |
| **Agregar solo el mes nuevo** (los años anclados no se tocan) | `icml actualizar` |
| Dibujar la última entrega | `icml graficos` |
| Auditar una entrega | `icml verificar` |

Cada comando explica en español lo que va a hacer, pide confirmación cuando va a reemplazar la base publicada
(`--si` la omite) y admite `--simulacro` para ver el plan sin calcular nada. `icml <comando> --help` lista las opciones.

---

## 1. Preparación (una sola vez)

1. Instalar Python 3.12.
2. Desde la carpeta del proyecto, ejecutar el instalador:
   * Windows: doble clic en `INSTALAR_WINDOWS.bat`.
   * Linux o Mac: `./INSTALAR_LINUX_MAC.sh`.

   Crea la carpeta `.venv` con las versiones exactas que el proyecto necesita.
3. Comprobar que quedó bien: `icml estado` debe mostrar los anexos, la base publicada y el siguiente paso.

El proyecto ya trae una base publicada (corte 2026-08), sus entregas y los gráficos: `icml estado` los muestra.

---

## 2. Las tres rutinas

### A. Construir la base desde cero

```
icml consolidar --desde-cero                 # hasta el último mes con los dos anexos
icml consolidar --desde-cero --hasta 2026-07 # hasta julio, ignorando los anexos posteriores
```

Recalcula **todos** los años (1993 hasta el último mes) y publica la base vigente. Sirve para la primera vez, para
empezar de nuevo tras un cambio de método, o para rehacer la base hasta un mes anterior. Si ya hay una base publicada,
`consolidar` se niega a reemplazarla a menos que se pida `--desde-cero` (y pide confirmar). Las entregas anteriores se
conservan. Al terminar crea la entrega, la **audita** (36 comprobaciones) y crea los archivos sencillos.

Tarda unos 10 a 15 minutos. Hasta un mes anterior al congelado (agosto de 2026) el programa arma por sí solo una copia
de trabajo del proyecto cortada en ese mes y calcula allí: no se modifica nada de lo que hay en `datos/`.

### B. Actualizar solo el mes nuevo

```
icml actualizar
```

Agrega a la base vigente los meses nuevos. **Los años cubiertos por el anexo departamental (hasta 2025) quedan
congelados**: no cambia ninguna de sus cifras; solo se recalcula el año abierto. Dice `SOLO ACTUALIZAR` al empezar para
que no haya duda. Se niega si no hay base publicada ("primero consolidar") y no retrocede a un mes anterior al de la
base. Si no hay anexos nuevos responde que ya está al día.

### C. Gráficos

```
icml graficos                              # todo, ambos universos (unos 90 segundos)
icml graficos --solo nacional,comparativos --universo censo
icml graficos --departamentos 05,11
```

Crea `<entrega>_graficos/` con un tablero del nacional y de cada departamento y los comparativos de las tasas. Abrir
`INDICE.html` en el navegador. No cambia ninguna cifra. Detalle: `icml-colombia/docs/production/GRAFICOS.md`.

---

## 3. Cada mes

### Paso 1 · Descargar los dos anexos del mes

Del sitio del DANE se necesitan **dos** archivos del mismo mes:

| Anexo | Dónde está en el DANE | Carpeta de destino |
|---|---|---|
| Mercado laboral (GEIH) | Página de la GEIH, mercado laboral | `datos/1_ingesta/geih_mercado_laboral/` |
| Informalidad y seguridad social | Página de informalidad de la GEIH | `datos/1_ingesta/geih_informalidad/` |

El anexo de informalidad suele publicarse después que el de mercado laboral. **Hasta que estén los dos, el mes no se
calcula**: esa regla es parte del método.

### Paso 2 · Copiarlos en su carpeta

* No hace falta renombrarlos: sirve el nombre con que los descarga el DANE (`Anexo GEIH Septiembre 2026.xlsx`,
  `anex-GEIH-sep2026.xlsx`) o el canónico (`geih_mercado_laboral_2026-09.xlsx`). El sistema lee el mes **dentro** del
  libro.
* **No borrar los meses anteriores** ni editar los Excel.

### Paso 3 · Actualizar

```
icml estado         # confirma que ve los dos anexos nuevos
icml actualizar     # agrega el mes (con --simulacro muestra el plan sin calcular)
icml graficos       # opcional
```

### Paso 4 · Revisar antes de compartir

* `icml actualizar` y `icml consolidar` ya auditan la entrega y muestran `PASS` o qué comprobación falló. Para
  volver a auditar: `icml verificar`.
* En el universo GEIH, 9 territorios (Arauca, Casanare, Putumayo, San Andrés, Amazonas, Guainía, Guaviare, Vaupés y
  Vichada) tienen tasas vacías de 2001 a 2013: la GEIH no los representaba. Es correcto, no es un error.

### Paso 5 · Compartir

Subir las carpetas del mes (la completa, la `_sencillo` y, si se generaron, los gráficos) al repositorio: es el respaldo
de cada entrega (ver la sección 8).

### Si algo sale distinto

| Mensaje o situación | Qué pasa | Qué hacer |
|---|---|---|
| "Ya hay una base publicada…" (al consolidar) | Protección para no reemplazar la base por accidente | `icml actualizar`, o `icml consolidar --desde-cero` si se quiere recomenzar |
| "Todavía no hay una base publicada que actualizar" | No hay base sobre la cual actualizar | `icml consolidar --desde-cero` |
| "No tengo los dos anexos de AAAA-MM" | Falta uno de los dos anexos de ese mes | Copiar el que falta |
| "Los anexos llegan hasta AAAA-MM, pero lo más nuevo que se puede procesar es 2026-08" | **Limitación actual** (ver la sección 4) | `icml actualizar --hasta 2026-08` ignora lo posterior |
| "Ya está al día" | No hay anexos nuevos desde la última actualización | Nada |
| `BLOQUEADO: Se modificó un insumo existente` | Se reemplazó un Excel que ya se había usado | Si fue a propósito (el DANE corrigió el anexo): `icml recalcular --root . --aceptar-modificados` |
| "…el nombre dice AAAA-MM pero el libro declara…" | El archivo no es del mes que dice su nombre | Descargar el correcto o renombrarlo con su mes real |
| "…different files claim it…" | Dos archivos distintos para el mismo mes | Dejar solo uno |

Tener un Excel abierto mientras se corre no molesta: los archivos temporales de Excel (`~$…`) se ignoran.

Los comandos `icml recalcular` y `icml entrega …` siguen disponibles para uso avanzado: los comandos de arriba son una
capa sencilla sobre ellos.

---

## 4. Lo que hoy no es automático

* **Meses posteriores a agosto de 2026.** Aunque lleguen los dos anexos, el recálculo se bloquea. El modelo de
  informalidad y el puente censal tienen parámetros congelados mes a mes hasta agosto de 2026, y falta decidir cómo
  extenderlos a meses nuevos. Es una decisión metodológica pendiente, no un error de operación. Mientras tanto, la rutina
  de las secciones 2 y 3 sirve para incorporar anexos corregidos del período ya cubierto.
* **El anexo departamental anual.** El año que se congela sale del anexo departamental fijado en la configuración
  (`geih_departamentos_2025.xlsx`). Cuando el DANE publique el de 2026, dejarlo en `geih_departamentos/` no basta:
  hay que actualizar la configuración y recalcular en modo total.
* **Cambios de método.** Si se cambia la configuración de forma que se alteran años cerrados:
  `icml recalcular --root . --modo total --confirmar-total`, con versión nueva y nota en el registro de cambios.

---

## 5. Qué no hacer

* No editar ni borrar archivos de `datos/1_ingesta/` ni de `datos/2_procesamiento/`.
* No borrar entregas anteriores de `datos/3_salida/`: la más reciente es la referencia del próximo recálculo.
* No correr dos recálculos a la vez.
* No cambiar archivos de `icml-colombia/configs/` sin entender el efecto: puede reescribir la historia.

---

## 6. Estructura del proyecto

```
.
├── README.md                   esta guía
├── INSTALAR_WINDOWS.bat · INSTALAR_LINUX_MAC.sh
├── dependencias/               paquete auxiliar (tempdisagg)
├── datos/
│   ├── 1_ingesta/              aquí van los Excel del DANE (lo único que se toca cada mes)
│   ├── 2_procesamiento/        parámetros y fuentes internas (no tocar)
│   └── 3_salida/               entregas fechadas (la última va incluida)
├── icml-colombia/              el programa: código, configuración, pruebas y documentación
└── legacy/                     referencias de validación RC1 (las pruebas las usan) y archivo histórico
```

## 7. Qué contiene este repositorio

**Todo**: el código, la configuración, las pruebas, la documentación, los Excel del DANE, los parámetros congelados,
la vintage vigente, las referencias de validación RC1, la última entrega (completa, sencilla y sus gráficos) y la
bitácora de las sesiones de trabajo. Quien lo descarga puede reproducir y verificar todo sin pedirle nada a nadie. Pesa unos 650 MB
(798 archivos; el mayor, 35 MB); no usa Git LFS, así que el botón *Download ZIP* de GitHub también trae todo.

El instalador no incluye `torch` (solo lo necesitan 3 pruebas del modelo de informalidad). Para instalarlo:
`pip install -r icml-colombia/requirements/lock-py312-ml.txt` dentro de `.venv`.

Para comprobar que la copia está completa e intacta, desde la raíz: `sha256sum -c SHA256SUMS` (Linux o Mac) o
`python icml-colombia/tools/release/verify_checkout.py` (cualquier sistema).

## 8. Respaldo en GitHub

Cada mes, después de verificar la entrega:

```
git add -A
git commit -m "Entrega AAAA-MM"
git push
```

Antes del commit, regenerar la lista de hashes: `python icml-colombia/tools/release/verify_checkout.py --escribir`.
Las instrucciones del primer push están en `icml-colombia/docs/production/PUBLICACION_EN_GITHUB.md`.

## 9. Más información

* Cómo funciona por dentro: `icml-colombia/docs/MARCO_GENERAL_PROCESAMIENTO.md` y el índice `icml-colombia/docs/README.md`.
* PET lineal y componentes de 1993-2000: `icml-colombia/docs/production/RECONSTRUCCION_LABORAL.md`.
* Empalmes de 2001-01 (2.3.0): `icml-colombia/docs/production/EMPALMES_2001.md`.
* Para quien mantiene el código, incluidas las pruebas: `icml-colombia/README.md`.
* Cambios por versión: `icml-colombia/CHANGELOG.md`.

Autor: Jaime A. Vera-Jaramillo. Licencia MIT (`LICENSE`).
