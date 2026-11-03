# Gráficos de una entrega (herramienta opcional)

`tools/plots/graficar_entrega.py` dibuja una entrega ya calculada. **No es parte de la estimación**: solo lee los
resultados, no cambia ninguna cifra y nada depende de ella. Necesita matplotlib, que el instalador ya trae.

```
python icml-colombia/tools/plots/graficar_entrega.py --carpeta datos/3_salida/<entrega>
```

(En Windows: `.venv\Scripts\python icml-colombia\tools\plots\graficar_entrega.py ...`.) Escribe `<entrega>_graficos/`
al lado de la entrega, con un `INDICE.html` que se abre en el navegador. Tarda unos 90 segundos y produce 87 imágenes
(25 MB).

| Opción | Efecto |
|---|---|
| `--solo nacional,departamentos,comparativos` | Dibuja solo esos grupos |
| `--universo censo` o `geih` | Un solo universo |
| `--departamentos 05,11` | Solo esos departamentos (códigos DANE) |
| `--formato png\|pdf\|svg`, `--dpi N` | Formato y resolución |
| `--salida CARPETA`, `--forzar` | Destino; `--forzar` reemplaza una salida existente |

## Qué dibuja

**Tableros** (uno del nacional y uno por cada uno de los 33 departamentos, en cada universo: 68 imágenes): tasas
laborales (TD, TO, TGP), niveles (PET, PEA, ocupados, desocupados, inactivos), informalidad (tasa e informales frente a
formales) y composición del empleo por sector.

**Comparativos** (19 imágenes):

| Archivo | Muestra |
|---|---|
| `nacional_censo_vs_geih` | Las cuatro tasas nacionales, universo censo frente a GEIH |
| `departamentos_<TASA>_censo_vs_geih` | Los 33 departamentos en miniatura, con la misma escala vertical y el nacional de referencia |
| `mapa_calor_<TASA>_<universo>` | Promedio anual por departamento, ordenado por el último año |
| `ranking_<TASA>` | Último mes: cada departamento, censo y GEIH, con el valor nacional |
| `dispersion_departamental_<universo>` | Rango mínimo-máximo, percentiles 10 a 90 y mediana departamental alrededor del nacional |

## Cómo leerlos

* **Sombreado gris, 1993-2000:** tramo reconstruido, sin ancla oficial. La línea discontinua marca el empalme de 2001-01.
* **Franja rosada (universo GEIH):** meses en que la GEIH no representa ningún habitante del territorio; la serie se
  interrumpe en vez de mostrar ceros. Antes de 2001 el universo GEIH reconstruye todo el territorio y desde 2014 solo
  la parte representada, por lo que los niveles de esos territorios cambian de escala; no es un error.
* **Censo y GEIH coinciden** en la mayoría de los departamentos: la línea del censo, más gruesa, queda detrás de la de
  la GEIH. La informalidad es la misma en ambos universos por el supuesto de que el complemento tiene igual tasa.
* **"Sin información" en el panel sectorial:** hay meses con una porción visible (hasta 5,8 % en 2006-07). Es un
  rasgo del producto sectorial, que conserva la categoría residual de las fuentes; el gráfico solo lo hace visible.
* Los nombres de los sectores son rótulos cortos de las secciones CIIU Rev. 4 A.C. que usa el proyecto
  (`docs/sectoral/HITO10_EMPAlME_CIIU3_CIIU4_2_2_17.md`).

## Dónde están los de la entrega vigente

Ya generados, en `datos/3_salida/<entrega>_graficos/`. Para otro mes, basta con repetir el comando sobre su entrega.
