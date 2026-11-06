# ICML — Regla obligatoria de sincronización de fuentes DANE

**Versión:** 2.2.24.dev0 · Corrección H22b · 2 de noviembre de 2026.

## Condición indispensable

El ICML **solo puede ejecutar una actualización mensual integral** cuando recibe, para un mismo mes objetivo `M`, las **dos publicaciones oficiales del DANE**:

- **Gran Encuesta Integrada de Hogares (GEIH), Mercado Laboral:** anexo mensual cuyo período de referencia sea **M**.
- **Empleo Informal y Seguridad Social:** anexo de trimestre móvil cuyo **mes final sea M**. El trimestre debe abarcar exactamente `M−2`, `M−1` y `M`.

En consecuencia:

`mes_GEIH = mes_final_trimestre_movil_informalidad_seguridad_social = mes_actualizacion_ICML`.

**Ejemplo:** septiembre de 2026 requiere **GEIH septiembre de 2026** junto con **Empleo Informal y Seguridad Social julio–septiembre de 2026**. La edición junio–agosto de 2026 **no puede utilizarse** para actualizar septiembre, aunque sea la última publicada en ese momento.

## Puerta de actualización (obligatoria)

Si cualquiera de los dos anexos no está publicado, no se ha obtenido o no ha podido verificarse, o su período de referencia no coincide:

1. **BLOQUEAR** toda estimación mensual nueva del ICML (nacional, urbana, departamental, informalidad y sectorial), incluidas las conciliaciones y productos finales.
2. **NO** trasladar la última tasa disponible de informalidad/Seguridad Social, ni imputar un anexo ausente como si fuera observado, ni cruzar anexos de meses diferentes.
3. **NO** generar ni promover una nueva vintage de resultados ni cambiar el último corte congelado.
4. Permitir únicamente una **recepción y auditoría aislada** de las fuentes que sí existan, con marcas de `staging` y sin publicar resultados.

Si ambas fuentes están disponibles, verificar adicionalmente su contenido, origen y período declarado dentro de los XLSX, SHA-256, revisiones y puertas estadísticas. Su mera existencia en disco y la coincidencia de nombres **no bastan** para autorizar la actualización.

## Estado de septiembre de 2026

- GEIH septiembre: publicación anunciada por el DANE; el XLSX no estaba descargado en el checkpoint H22.
- Empleo Informal y Seguridad Social julio–septiembre: **pendiente** en el corte de este documento.
- Publicación esperada aproximadamente a mediados de noviembre de 2026, según la información comunicada; la fecha es **orientativa y no verificada**.
- **Última vintage de resultados válida en el paquete: agosto de 2026.** Se mantiene intacta.

## Implementación

`icml operations check-monthly-sources` revisa presencia y coherencia de **períodos declarados**; sus reportes nunca habilitan por sí solos la publicación. El contenido de la fuente de Seguridad Social debe verificarse en una etapa posterior de ingestión oficial, antes de cualquier ejecución integral. `icml operations intake-geih` permite inspeccionar GEIH por adelantado, pero informa que la actualización integral permanece bloqueada hasta tener su pareja sincronizada.

Este requisito es una **dependencia metodológica innegociable** para el pipeline de producción, no una recomendación opcional.
