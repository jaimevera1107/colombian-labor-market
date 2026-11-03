# ICML v2.4.0 — Cómo probarlo y subirlo

Este ZIP es el repositorio **completo**, con su Git intacto (`.git`, `.gitignore`, `.gitattributes`, `.github/`): código,
datos, referencias, la entrega de agosto de 2026 y sus gráficos. Las pruebas se revisan y se deshacen con Git.

## 0. Instalar (una vez)

1. Instalar **Python 3.12**.
2. Descomprimir el ZIP y entrar a la carpeta `ICML`.
3. Ejecutar el instalador (necesita internet y unos minutos; crea `.venv` con las versiones exactas):
   * Linux o Mac: `./INSTALAR_LINUX_MAC.sh`
   * Windows: doble clic en `INSTALAR_WINDOWS.bat`
4. Comprobar:

   ```
   ./icml.sh estado        # Windows cmd: icml estado     PowerShell: .\icml estado
   git status              # debe decir: nothing to commit, working tree clean
   git log --oneline       # el commit de v2.4.0
   ```

   `estado` debe mostrar los anexos hasta 2026-08, la base publicada con corte 2026-08 y "Todo está al día".

## 1. Reconstrucción desde cero con los anexos de julio

```
./icml.sh consolidar --desde-cero --hasta 2026-07 --si
```

* `--desde-cero` **fuerza recomenzar todo** (sin esa bandera, `consolidar` se niega a reemplazar una base ya publicada).
* `--hasta 2026-07` usa solo los anexos hasta julio e **ignora** los de agosto, que ya están en la carpeta.
* `--si` omite la confirmación. `--simulacro` muestra el plan sin calcular nada.

Tarda unos 10 a 15 minutos. Termina con `Auditoría: PASS (36 de 36 comprobaciones)`, crea la entrega y los archivos sencillos,
y la base vigente queda en julio (`./icml.sh estado` lo confirma).

## 2. Actualización incremental: solo el mes nuevo (agosto)

```
./icml.sh actualizar --mes 2026-08       # igual que: ./icml.sh actualizar
```

Imprime `SOLO ACTUALIZAR hasta 2026-08`, ve los dos anexos de agosto como nuevos, **congela los años anclados (hasta 2025)**
y recalcula solo lo abierto. Tarda unos 8 a 10 minutos y termina con `Auditoría: PASS (36 de 36 comprobaciones)`.

Qué esperar (se comprobó en una copia limpia): entre la base de julio y la de agosto hay **0 celdas distintas hasta 2025**; en
2026 el empleo departamental cambia con mediana 0,09 % (máximo 1,56 %) porque entra un mes. Si se repite, responde "Ya está al
día". Con `--simulacro` se ve el plan sin calcular.

## 3. Gráficos

```
./icml.sh graficos
```

Dibuja la entrega vigente (87 imágenes, unos 90 segundos) en `datos/3_salida/<entrega>_graficos/`; abrir `INDICE.html` en el
navegador. Opciones: `--solo nacional,comparativos`, `--universo censo`, `--departamentos 05,11`, `--forzar` (reemplazar).

## Otros comandos

| Comando | Para qué |
|---|---|
| `icml estado` | Qué hay y cuál es el siguiente paso |
| `icml verificar` | Vuelve a auditar la última entrega (36 comprobaciones) |
| `icml <comando> --help` | Opciones de cada comando |

## Después de las pruebas: revisar, deshacer o subir

Las pruebas **agregan entregas** en `datos/3_salida/` y **cambian la base vigente** (`datos/2_procesamiento/vigente/`).
Como Git está intacto, se ve y se deshace así:

```
git status                                   # qué cambió
git restore datos && git clean -fd datos/3_salida   # volver exactamente al estado entregado
```

**Subir a GitHub** (si todo salió bien; el repositorio de destino ya existe y se reemplaza):

1. Respaldar lo que hay: `git clone --mirror https://github.com/jaimevera1107/colombian-labor-market.git respaldo.git`.
2. Si hizo las pruebas y quiere subir ese estado, regenerar los hashes: `python icml-colombia/tools/release/verify_checkout.py --escribir`
   y `git add -A && git commit -m "Entrega de prueba"`. Si volvió al estado entregado, no hace falta.
3. La identidad del commit es provisional (`no-reply@icml.invalid`); para poner la suya:
   `git config user.name "Su nombre"`, `git config user.email "su@correo"` y `git commit --amend --reset-author --no-edit`.
4. Subir:

   ```
   git remote add origin https://github.com/jaimevera1107/colombian-labor-market.git    # si ya existe: git remote set-url origin <url>
   git branch -M main
   git push --force -u origin main
   git push origin v2.4.0
   ```

   El push forzado **reemplaza todo el contenido** del repositorio de destino. Si su rama principal es `master`: `git push --force origin main:master`.
   GitHub avisa (no bloquea) por un archivo de 63 MB: `legacy/entregas_anteriores/entrega_2.3.0_corte-2026-08.zip`.

## Si algo falla

Cada error de uso imprime un mensaje en español con qué hacer. Lo más común:

| Mensaje | Qué hacer |
|---|---|
| "Falta el entorno" | Ejecutar el instalador (paso 0) |
| "Ya hay una base publicada…" | Usar `actualizar`, o `consolidar --desde-cero` |
| "No tengo los dos anexos de AAAA-MM" | Copiar el anexo que falta en `datos/1_ingesta/` |
| "Ya existe … gráficos" | Añadir `--forzar` |

Licencia: MIT (`LICENSE`). Más detalle: `README.md` y `icml-colombia/docs/production/ACTUALIZACION_MENSUAL.md`.
