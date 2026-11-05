<div align="center">


  # ICML

  **Indicadores de Condiciones del Mercado Laboral de Colombia**

  *Reconstrucción, actualización y validación de series mensuales del mercado laboral colombiano.*

  [![Version](https://img.shields.io/badge/versi%C3%B3n-2.4.0-183153?style=flat-square)](icml-colombia/CHANGELOG.md)
  ![Cobertura](https://img.shields.io/badge/corte-2026--08-536779?style=flat-square)
  ![Python](https://img.shields.io/badge/Python-3.12-376994?style=flat-square)
  [![Licencia](https://img.shields.io/badge/licencia-MIT-536779?style=flat-square)](LICENSE)
  ![Carácter](https://img.shields.io/badge/uso-investigaci%C3%B3n-687687?style=flat-square)

  [**Inicio rápido**](#inicio-rápido) · [**Comandos**](#comandos-principales) · [**Actualización mensual**](#actualización-mensual) · [**Metodología y límites**](#alcance-y-limitaciones) · [**Documentación**](#documentación)

</div>

---

ICML reúne series mensuales de **mercado laboral, informalidad y empleo sectorial** para **33 territorios de Colombia**, con información desde **enero de 1993** y dos universos de análisis:

- **Censo:** cobertura del territorio completo.
- **GEIH:** cobertura de la población que la Gran Encuesta Integrada de Hogares representa.

El proyecto integra el código, los insumos, los parámetros de procesamiento, las pruebas y las entregas para **reconstruir y verificar resultados de investigación** sin depender de archivos externos adicionales.

> [!IMPORTANT]
> **Los resultados de ICML son productos de investigación y no constituyen estadísticas oficiales del DANE.** La versión descrita aquí es **2.4.0**, con corte vigente en **2026-08**.

## En síntesis

| Dimensión | Alcance |
|:--|:--|
| **Período** | Series mensuales desde `1993-01` |
| **Cobertura territorial** | 33 territorios de Colombia; tableros nacionales y departamentales |
| **Universos** | Censo y GEIH |
| **Contenido** | Mercado laboral, informalidad y empleo por sector |
| **Insumos periódicos** | Dos anexos del DANE correspondientes al mismo mes |
| **Calidad** | 36 comprobaciones automáticas por entrega |
| **Última versión documentada** | `2.4.0` · corte `2026-08` |

## Inicio rápido

### 1. Preparar el entorno

Se requiere **Python 3.12**. Desde la carpeta raíz del proyecto, ejecuta el instalador correspondiente:

| Sistema | Instalación | Ejemplo de comando |
|:--|:--|:--|
| Windows · PowerShell | Doble clic en `INSTALAR_WINDOWS.bat` | `.\icml estado` |
| Windows · CMD | Doble clic en `INSTALAR_WINDOWS.bat` | `icml estado` |
| Linux / macOS | `./INSTALAR_LINUX_MAC.sh` | `./icml.sh estado` |

El instalador configura `.venv` con las versiones de dependencias requeridas. **No necesitas activar manualmente el entorno virtual para usar el atajo `icml`.**

### 2. Consultar el estado

En PowerShell:

```powershell
.\icml estado
```

El comando identifica los anexos disponibles, la base publicada y el siguiente paso.

### 3. Ejecutar el flujo completo

El repositorio distribuye el código y los insumos fuente; los productos se generan localmente. Para reconstruir desde cero hasta julio, actualizar con agosto y producir los gráficos:

```powershell
.\icml consolidar --desde-cero --hasta 2026-07 --si
.\icml actualizar
.\icml graficos
```

O equivalentemente con `python -m icml` (útil si se trabaja directamente sobre el paquete sin el wrapper):

```bash
python -m icml consolidar --root . --hasta 2026-07 --desde-cero --si
python -m icml actualizar --root .
python -m icml graficos --root .
```

> **Nota:** `actualizar` no tiene flag `--si`; corre directo sin pedir confirmación.

Este flujo **reconstruye y publica** una base. Sigue previamente las precauciones y las comprobaciones indicadas en [PRUEBAS.md](PRUEBAS.md). Si solo quieres inspeccionar lo que haría un comando, utiliza `--simulacro`.

> Los ejemplos siguientes utilizan `icml` como nombre genérico. En PowerShell escribe `.\icml`; en Linux/macOS, `./icml.sh`.

## Comandos principales

| Objetivo | Comando |
|:--|:--|
| Consultar insumos, estado y próximos pasos | `icml estado` |
| Reconstruir todo el histórico desde cero | `icml consolidar --desde-cero` |
| Reconstruir hasta un mes determinado | `icml consolidar --desde-cero --hasta 2026-07` |
| Actualizar la base publicada con los meses procesables | `icml actualizar` |
| Generar los gráficos de la última entrega | `icml graficos` |
| Ejecutar nuevamente las auditorías | `icml verificar` |
| Simular una operación sin calcular | `icml <comando> --simulacro` |
| Consultar opciones | `icml <comando> --help` |

Los comandos presentan sus acciones en español. Cuando una operación puede reemplazar la base publicada, solicitan confirmación; `--si` permite omitirla cuando corresponde.

### Reconstrucción completa frente a actualización

| | Reconstruir: `consolidar --desde-cero` | Actualizar: `actualizar` |
|:--|:--|:--|
| **Uso** | Primera construcción, reinicio o cambio de método | Incorporar meses procesables a una base existente |
| **Histórico** | Recalcula el período desde 1993 | Mantiene congelados los años anclados por el anexo departamental (hasta 2025) |
| **Requisito previo** | Los insumos del período | Una base publicada previamente |
| **Control** | Confirmación, auditoría y nueva entrega | Auditoría de la entrega; no retrocede a cortes anteriores |

Una reconstrucción completa suele tardar **10 a 15 minutos**, según lo documentado para este proyecto. Cuando se solicita un corte anterior al vigente, el programa prepara una copia de trabajo sin modificar los insumos originales de `datos/`.

## Actualización mensual

La rutina utiliza **dos archivos Excel oficiales de entrada del DANE para el mismo mes**:

| Insumo | Origen | Ubicación dentro del proyecto |
|:--|:--|:--|
| Mercado laboral (GEIH) | Anexos del mercado laboral | `datos/1_ingesta/geih_mercado_laboral/` |
| Informalidad y seguridad social | Anexos de informalidad de la GEIH | `datos/1_ingesta/geih_informalidad/` |

**Procedimiento:**

1. Descarga ambos anexos correspondientes al **mismo mes**. El anexo de informalidad puede publicarse después del de mercado laboral; sin los dos, ese mes no se calcula.
2. Coloca cada archivo en su carpeta. No hace falta cambiar el nombre: el sistema identifica el mes dentro del Excel. Conserva los anexos de períodos anteriores.
3. Comprueba los insumos con `icml estado` y, si el mes está admitido por el modelo, ejecuta `icml actualizar`.
4. Revisa el resultado de las auditorías (`PASS` o detalle de errores). Puedes repetirlas con `icml verificar`.
5. Opcionalmente, ejecuta `icml graficos` y conserva las carpetas de la entrega completa, la sencilla y los gráficos.

```powershell
.\icml estado
.\icml actualizar --simulacro
.\icml actualizar
.\icml graficos
```

> [!WARNING]
> **Límite metodológico vigente: agosto de 2026.** Aunque existan los dos anexos de septiembre de 2026 o meses posteriores, la versión 2.4.0 **bloquea su procesamiento**. Los parámetros mensuales de informalidad y del puente censal solo están congelados hasta `2026-08`. Es necesario definir su extensión antes de actualizar más allá de ese corte. No debe interpretarse `icml actualizar` como una actualización ilimitada a cualquier mes futuro.

### Generación de gráficos

```bash
icml graficos
icml graficos --solo nacional,comparativos --universo censo
icml graficos --departamentos 05,11
```

Se crea una carpeta `<entrega>_graficos/`, con visualizaciones nacionales, departamentales y comparaciones de tasas. El archivo `INDICE.html` permite consultarlas en el navegador. **Generar gráficos no altera los resultados estadísticos.** Consulta [GRAFICOS.md](icml-colombia/docs/production/GRAFICOS.md).

## Alcance y limitaciones

La validez de las series depende del universo, la cobertura histórica y las decisiones metodológicas documentadas. En particular:

- **Diferencias de representatividad:** en el universo GEIH, las tasas de nueve territorios permanecen vacías entre 2001 y 2013 —Arauca, Casanare, Putumayo, San Andrés, Amazonas, Guainía, Guaviare, Vaupés y Vichada— porque la encuesta no los representaba en ese período. **No son datos faltantes accidentales.**
- **Meses posteriores a `2026-08`:** su incorporación está bloqueada hasta extender metodológicamente los parámetros de informalidad y puente censal.
- **Nuevo anexo departamental anual:** el año anclado se determina con el archivo configurado (`geih_departamentos_2025.xlsx`). Cuando se incorpore un nuevo anexo, **no basta con copiarlo**: se requiere ajustar la configuración y ejecutar un recálculo total.
- **Cambios metodológicos:** las modificaciones que afecten años cerrados necesitan una versión nueva, registro de cambios y recálculo total controlado.

Para un recálculo total avanzado tras una modificación metodológica:

```bash
icml recalcular --root . --modo total --confirmar-total
```

### Controles para preservar la reproducibilidad

- No editar ni borrar archivos de `datos/1_ingesta/` o `datos/2_procesamiento/`.
- No eliminar entregas históricas de `datos/3_salida/`: la última es la referencia del siguiente recálculo.
- No ejecutar dos recálculos simultáneamente.
- No modificar `icml-colombia/configs/` sin evaluar su efecto sobre la reconstrucción histórica.

### Problemas frecuentes

<details>
<summary><strong>Ver mensajes habituales y cómo resolverlos</strong></summary>

| Mensaje o situación | Explicación / acción |
|:--|:--|
| Ya existe una base publicada | Usa `actualizar`, o `consolidar --desde-cero` si realmente necesitas reconstruir. |
| No hay base para actualizar | Ejecuta primero `consolidar --desde-cero`. |
| No están los dos anexos del mes | Incorpora el anexo faltante antes de procesar. |
| Los anexos superan `2026-08` | La versión vigente no puede procesar esos meses; utiliza únicamente el corte soportado. |
| «Ya está al día» | No hay meses nuevos procesables. |
| `BLOQUEADO: Se modificó un insumo existente` | Si se trata de una corrección intencional del DANE, consulta el recálculo con `icml recalcular --root . --aceptar-modificados`. |
| El nombre del archivo y el mes del libro no coinciden | Corrige el nombre o utiliza el archivo del mes correcto. |
| Dos archivos declaran el mismo mes | Mantén solo el anexo válido correspondiente. |

Los archivos temporales de Excel con prefijo `~$` se ignoran. Las herramientas `icml recalcular` e `icml entrega` siguen disponibles para administración avanzada.

</details>

## Estructura del repositorio

```text
.
├── README.md
├── PRUEBAS.md
├── LICENSE
├── assets/
│   └── icml-logo.png
├── INSTALAR_WINDOWS.bat
├── INSTALAR_LINUX_MAC.sh
├── dependencias/                 # Paquete auxiliar (tempdisagg)
├── datos/
│   ├── 1_ingesta/                # Anexos del DANE
│   ├── 2_procesamiento/          # Parámetros y fuentes internas
│   └── 3_salida/                 # Entregas y resultados
├── icml-colombia/                # Código, configuración, pruebas y documentación
└── legacy/                       # Referencias RC1 y material histórico
```

El repositorio distribuye código fuente, pruebas, documentación, anexos de entrada y parámetros congelados. Los productos (entregas, gráficos, bases vigentes) se generan localmente al correr `icml consolidar`. El tamaño descargado es aproximadamente **100 MB**, sin Git LFS.

Para comprobar la integridad de una copia descargada:

```bash
# Linux / macOS
sha256sum -c SHA256SUMS

# Cualquier sistema con Python
python icml-colombia/tools/release/verify_checkout.py
```

El instalador normal no incorpora `torch`; lo requieren tres pruebas del modelo de informalidad. Para ese entorno, el proyecto documenta el archivo `icml-colombia/requirements/lock-py312-ml.txt`.

## Publicación y respaldos

Cada entrega se conserva como una versión reproducible de resultados. Antes de registrar sus cambios en GitHub, actualiza el inventario de hashes y ejecuta el control de integridad correspondiente.

```bash
python icml-colombia/tools/release/verify_checkout.py --escribir

git add -A
git commit -m "Entrega AAAA-MM"
git push
```

Consulta [PUBLICACION_EN_GITHUB.md](icml-colombia/docs/production/PUBLICACION_EN_GITHUB.md) para las instrucciones de publicación inicial y la organización de las entregas.

## Documentación

| Documento | Contenido |
|:--|:--|
| [PRUEBAS.md](PRUEBAS.md) | Ejercicio guiado: reconstruir hasta julio, actualizar agosto, graficar y publicar |
| [Marco general](icml-colombia/docs/MARCO_GENERAL_PROCESAMIENTO.md) | Reglas y funcionamiento del procesamiento |
| [Índice técnico](icml-colombia/docs/README.md) | Navegación de la documentación del proyecto |
| [Reconstrucción laboral](icml-colombia/docs/production/RECONSTRUCCION_LABORAL.md) | PET, población y componentes de 1993–2000 |
| [Empalmes 2001](icml-colombia/docs/production/EMPALMES_2001.md) | Tratamiento de los empalmes de enero de 2001 (2.3.0) |
| [Gráficos](icml-colombia/docs/production/GRAFICOS.md) | Generación y consulta de visualizaciones |
| [Guía para desarrollo](icml-colombia/README.md) | Arquitectura, operación y pruebas del código |
| [Changelog](icml-colombia/CHANGELOG.md) | Historial de versiones |

---

<div align="center">

**ICML 2.0** · Proyecto de investigación sobre el mercado laboral colombiano

**Autor:** Jaime A. Vera-Jaramillo · **Licencia:** [MIT](LICENSE)

</div>
