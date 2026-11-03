# Datos

Tres etapas, en el orden en que los usa el sistema:

| Carpeta | Qué guarda | ¿Se edita a mano? |
|---|---|---|
| `1_ingesta/` | Anexos DANE y referencias en Excel, tal como se descargan (ver `1_ingesta/LEEME.md`) | Sí: se agregan anexos nuevos |
| `2_procesamiento/` | Todo lo que el sistema necesita además de la ingesta | No |
| `3_salida/` | Entregas fechadas por universo (completas y sencillas); la última va incluida | No |

`2_procesamiento/` contiene:

| Subcarpeta | Contenido |
|---|---|
| `catalogos/` | Catálogo de fuentes y registro de Excel originales con sus hashes |
| `fuentes_preparadas/` | Tablas derivadas de los Excel (urbano, informalidad, anclas DANE, señales históricas) |
| `parametros_congelados/` | Parámetros que no se reentrenan: puente censal CNPV 2018, priors del modelo de informalidad, secuencia H5/H6 de referencia, escenarios 2020 |
| `productos_congelados/` | La vintage congelada de agosto de 2026 (referencia de equivalencia y de las pruebas) |
| `sectorial_h11/`, `sectorial_h16/` | Insumos, modelo y referencias del componente sectorial |
| `auditoria_historica_h30/` | Evidencia de linaje de los donantes urbanos y anexos históricos |
| `vigente/` | La última entrega promovida: lo que congela el próximo recálculo anclado |
| `_corridas/` | Espacio temporal de cada recálculo (vacío; su contenido no se versiona) |
