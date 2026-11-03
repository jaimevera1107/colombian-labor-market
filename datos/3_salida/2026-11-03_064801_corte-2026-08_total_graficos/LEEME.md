# Gráficos de la entrega 2026-11-03_064801_corte-2026-08_total

Versión 2.4.0 · corte 2026-08. Abra `INDICE.html` en el navegador.

* `universo_censo/` y `universo_geih/`: un tablero del nacional y uno por departamento (tasas laborales, niveles, informalidad y composición sectorial).
* `comparativos/`: nacional censo contra GEIH, los 33 departamentos en miniatura por tasa, mapas de calor anuales, ranking del último mes y dispersión departamental.

Sombreado gris: tramo reconstruido (1993-2000). Línea discontinua: empalme de 2001-01. Franja rosada (GEIH): meses sin representación del territorio en la GEIH.

Se generan con `python icml-colombia/tools/plots/graficar_entrega.py --carpeta <entrega>`; no cambian ninguna cifra.
