# ICML 2.2.18.dev0 — Hito 11, homologación histórica 1993–2001

**Estado: implementada y ejecutada como extensión exploratoria con trazabilidad.**

## Objetivo y alcance

Antes de julio de 2001 no contamos en este proyecto con una fuente mensual homologable para las 15 categorías actuales. Se transfieren **únicamente las tendencias de cuatro grandes participaciones del empleo** procedentes de `Ind_empleo_1958_2018.xlsx` del DANE. No sustituimos los niveles ICML por los porcentajes DANE ni declaramos observadas las 15 ramas.

La hoja `1958-2011` del libro describe las fuentes: **1991–2000 ENH a septiembre**, **2001–2006 ECH** y **2007–2011 GEIH**. El programa usa los años 1993–2001 y considera 1993–2000 como referencias puntuales de septiembre; el dato de 2001 no identifica realmente julio y se utiliza solo como frontera auxiliar convencional, con sensibilidad al retirarla. No se imponen medias anuales ENH como observaciones. La fuente define Servicios como transporte, almacenamiento y comunicaciones; intermediación financiera; actividades inmobiliarias; y servicios comunales, sociales y personales.

## Homologación establecida

| Referencia DANE | Categoría ICML 2.2.18 | Justificación / advertencia |
|---|---|---|
| Agricultura | `A` | Correspondencia conceptual agregada |
| Industria | `C` | Manufacturas, correspondencia conceptual |
| Comercio | `G`, `I` | Comercio, hoteles y restaurantes; Hito 10 `G_I` |
| Servicios | `H`, `J` | Transporte y comunicaciones |
| Servicios | `K` | Intermediación financiera |
| Servicios | `L`, `M_N` | Inmobiliarias y empresariales |
| Servicios | `O_P_Q`, `R_S_T_U` | Servicios comunales, sociales y personales |
| Otros = 100% − cuatro participaciones | `B`, `D_E`, `F` | Minería, servicios públicos y construcción; **residuo calculado**, no un quinto grupo publicado |
| No corresponde a actividad económica | `NO_INFO` | Separado de Otros; se fija en participación H11 julio 2001 (**supuesto**) |

Fuente de los nombres y puentes entre revisiones: `docs/sectoral/HITO10_EMPAlME_CIIU3_CIIU4_2_2_17.md` del mismo ICML, además de la nota original del Excel. Las categorías mezcladas bajo Servicios no son una conversión directa estadística CIIU Rev. 3 → Rev. 4: las fronteras cambiaron. Las particiones internas (`G/I`, `H/J`, `L/M_N`, `O_P_Q/R_S_T_U`, `B/D_E/F`) son supuestos de asignación respaldados por la composición del H11 en 2001 y no por observaciones individuales previas.

## Algoritmo implementado

1. Calcular `Otros` como residuo aritmético exacto de las cuatro participaciones, sin atribuirlo al DANE como sector observado.
2. Reconstruir trayectorias **latentes mensuales de cinco agregados** con restricciones puntuales ENH de septiembre y penalización cuadrática débil de primeras diferencias, siguiendo la lógica H11. El dato ECH 2001 se usa como frontera auxiliar convencional y también se evalúa la variante sin esa igualdad.
3. Tomar la composición sectorial del escenario `FULL_2015_BRIDGE` del H11 en julio de 2001 como **única referencia de escala**. Para cada uno de cinco agregados, trasladar retrospectivamente solo la razón de sus señales auxiliares respecto de julio 2001.
4. Reconciliar los cinco agregados positivos para que sumen `1 − participación(NO_INFO)` cada mes. `NO_INFO` permanece en su peso de julio de 2001 y no participa en la tendencia productiva. La participación total de 15 categorías es uno.
5. Desagregar cada agregado entre las categorías modernas con sus proporciones internas de julio de 2001 **congeladas hacia atrás**. Esta decisión evita inventar tendencias individuales sin evidencia. Multiplicar esa única composición por los ocupados mensuales propios de cada universo ICML.
6. Mantener completamente intactos los meses de julio 2001 en adelante y auditar cierre, restricciones, sensibilidad, concordancia de universos, hashes de entrada y procedencia.

La fuente histórica no fija la escala: en septiembre la trayectoria auxiliar coincide con ENH por construcción, pero el agregado final reconciliado **puede no coincidir** con la participación ENH. Esa diferencia no se corrige artificialmente.

## Sensibilidades y lectura

- **Principal:** ENH septiembre 1993–2000, frontera auxiliar ECH 2001 condicionada.
- **Temporal:** mismo estimador con media anual en lugar de ancla septiembre, hipótesis no preferida y conservada solo para comparación.
- **Frontera:** retirar la igualdad auxiliar de 2001, preservando igualmente el punto de enlace H11.
- **Composición interna:** congelación como punto central y bandas determinísticas de **±25% en *odds* de cada rama respecto al resto de su grupo** al inicio de 1993, que decrecen progresivamente a cero en julio 2001. Las bandas **no son intervalos estadísticos de confianza** y sus extremos para diferentes ramas no son simultáneos. Dos estrés composicionales factibles permiten comprobar cierre.

## Resultado de esta implementación

- **102 mensualidades** de enero 1993 a junio 2001.
- **15 categorías** (`14` actividades + `NO_INFO`), para **dos universos**, **tres tratamientos temporales**: **9.180 filas**.
- Error máximo de cierre: **7,45 × 10⁻⁹ personas**; error máximo de simplex: **4,44 × 10⁻¹⁶**.
- Diferencia máxima escenario media vs septiembre: **0,559 pp**.
- Diferencia máxima al relajar 2001: **0,132 pp**.
- Sensibilidad máxima entre estrés internos factibles y centro: **3,122 pp**; amplitud máxima de banda interna de supuestos: **3,337 pp**.
- La corrección de `NO_INFO` respecto al escenario anterior cambia como máximo **0,0058 pp**, y no reescribe el H11 previo.
- El máximo desajuste de los cuatro agregados publicados ENH respecto a la **composición final calibrada** fue **0,754 pp**. La señal auxiliar, en cambio, preserva sus anclas a precisión numérica.

## Regla de publicación

Esta serie es adecuada como **candidato ICML experimental con trazabilidad**, para análisis de sensibilidad y continuidad de modelos. No es una observación mensual oficial, ni debe pasar automáticamente a canónica. La razón de cautela es la ausencia real de observaciones de las 15 ramas antes de 2001, no un error funcional del reconstruidor. Los límites proceden fundamentalmente del cambio de clasificaciones, el soporte temporal de la ENH, la frontera ECH 2001 y las proporciones internas no identificadas.

## Integración en el paquete

Se añade `src/icml/sectoral_historical_homologation.py` y el subcomando `icml sectoral homologate-historical` sin cambiar las otras rutas del CLI. Se adjunta el `cli.py` de la 2.2.18 con un cambio localizado, así como las pruebas. La ejecución independiente `run_h11_homologacion.py` usa solo numpy, scipy y stdlib, por lo que sirve si faltan otras dependencias del proyecto completo.

```powershell
python run_h11_homologacion.py
python -m pytest -q patch/icml-colombia/tests/unit/test_sectoral_historical_homologation.py
```

Desde el repositorio ICML completo una vez copiados `src/icml/sectoral_historical_homologation.py` y el `cli.py` de este parche:

```powershell
icml sectoral homologate-historical --dane-csv inputs/dane_4_ramas_anuales_vintages.csv --link-csv inputs/h11_link_2001_07_FULL.csv --totals-csv inputs/totales_icml_1993_2001.csv --mapping-csv inputs/11_crosswalk_ENH_4_grupos_a_15_ramas_CIIU4.csv --output outputs
```

**No se sobrescribe** el checkpoint integral, el H11 de julio 2001 a 2026, las series laborales ni los anexos DANE originales.
