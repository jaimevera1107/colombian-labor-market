# ICML H35 — Preparación integral, H5/H6 y puerta de nuevas vintages

**Versión:** 2.2.35.dev0. **Corte reproducido:** agosto de 2026. **Uso:** investigación, no estadística oficial.

## Alcance implementado y demostrado

La ejecución `icml operations run-integral --root .. --output <carpeta-nueva> --mode recompute`
parte de los Excel archivados y construye los nueve derivados H29–H33. Posteriormente,
calcula el ICML laboral, regenera H5 con `InformalityNationalPipeline` usando el CSV
recién extraído de los Excel y las bases laborales de esta corrida y ejecuta H6
con el modelo secuencial original, las fuentes GEIH y los anclajes agregados de
13 ciudades. **Los dos archivos H6 de nacionales y 33 ciudades ahora provienen
de esa ejecución y NO del CSV heredado**, y pasan una prueba de identidad de
claves, columnas, categorías y tolerancias numéricas contra la vintage congelada.

El cierre H9 usa los nuevos H6. Conserva las matrices de puente censal CNPV
2018, las tasas previas MLP departamentales del modelo seleccionado y las
alternativas del vacío 2020 como **artefactos internos del modelo congelado**.
Esos artefactos no son entradas manuales ni observaciones directas desde Excel.
H16 vuelve a estimar el predictor sectorial, usando PIB/empleo sectorial derivados
de los Excel y las variables de la vintage del modelo seleccionada.

La diferencia entre `observed_monthly` (hoja Grandes dominios), `rolling_three_months`
(hoja Total nacional) y `latent_monthly` (inversión H5) está expresamente conservada.
No se sustituye una tasa latente modelada por la tasa observada de un mes.

## Nuevas comprobaciones

- `icml operations audit-social-annex --annex "...xlsx" --period AAAA-MM`:
  revisa las cuatro hojas originales, fecha de cierre, presencia de datos más
  recientes, identidades de formalidad y valores de seguridad social. Admite
  exclusivamente `.xlsx`. Devuelve `authorizes_publication=false`.
- `icml operations audit-informality-origin --root ..`:
  comprueba las 68 observaciones de ocupación desde enero de 2021 hasta agosto
  de 2026 contra la fuente Excel oficial y la serie latente seleccionada.
- `icml operations monthly-cycle --root .. --period AAAA-MM --geih-annex "...xlsx" --geih-month AAAA-MM --social-annex "...xlsx" --social-start AAAA-MM --social-end AAAA-MM --output <carpeta-nueva>`:
  valida ahora el contenido de ambas fuentes, además de los períodos declarados.
  **Sigue bloqueando el cálculo y publicación de nuevos meses** si no se ha
  desarrollado/verificado el adaptador correspondiente para las tres ramas.

## Procedimiento para la reproducción de agosto

```powershell
cd icml-colombia
python -m pip install -e .
python -m icml operations audit-social-annex --annex "..\insumos\fuentes\excel_originales\Mercado Laboral\Anexo GEIH Informalidad Agosto 2026.xlsx" --period 2026-08
python -m icml operations audit-informality-origin --root ..
python -m icml operations run-integral --root .. --output "..\..\ICML_H35_REPRODUCIDO" --mode recompute
```

**Salida:** nueve derivados, H5, H6, ocho productos y `integral_execution_report.json`
con evidencias completas. La ruta de salida no puede estar dentro del
checkpoint, ni existir previamente. El informe es el resultado autoritativo;
no basta con que el comando termine sin una excepción.

## Qué falta para afirmar que se actualiza cualquier mes usando solo seis Excel

1. H29–H33 implementan extractores de **vintage agosto 2026 con
   equivalencia congelada**, no conversores arbitrarios de anexos futuros.
2. H5/H6, el finalizador H9 y el selector H16 contienen ventanas y dimensiones
   fijadas al corte de agosto (404 meses). Es necesario parametrizar el mes
   final, las revisiones y las ventanas de validación sin reestimar históricos
   cuando llega solo un mes.
3. Los priors MLP departamentales, el puente CNPV y la vintage de
   características H16 deben versionarse y mantenerse coherentes con el
   mes nuevo. No debe usarse una matriz de características de una vintage
   distinta sin verificar su procedencia.
4. Un nuevo corte requiere **GEIH mensual M y Seguridad Social trimestre
   M−2..M**, ambos verificables en el XLSX original, además de la puerta de
   invariantes, revisiones oficiales y promoción explícita de vintage.
5. Las 131 pruebas Golden RC1 omitidas requieren el entorno Python 3.12 y
   versiones numéricas bloqueadas. Una equivalencia de ocho productos de
   agosto no sustituye esa certificación.

**Conclusión de alcance:** H35 reproduce agosto con una cadena más profunda,
auditando y regenerando H5/H6 desde fuentes Excel. No es legítimo presentar
H35 como sistema de actualización mensual completamente operativo para meses
posteriores: no existen adaptadores/modelos para generalizar el corte y aún
no se ha proporcionado una pareja futura validada.
