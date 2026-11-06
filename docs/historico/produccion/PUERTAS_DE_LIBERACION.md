# Puertas de liberación H20

| Puerta | Resultado | Interpretación |
|---|---|---|
| SHA-256 de ocho productos y estructura | Requiere auditoría H20 en cada paquete | Integridad exacta, no exactitud científica |
| H19 preflight: H18 + H16 + 3 laborales + informalidad | Requiere auditoría H19 en cada paquete | Cierre técnico sin nueva estimación |
| Suite de pruebas | Referencia histórica: 314 aprobadas; 137 omitidas | Se debe repetir en entrega H20 |
| Golden RC1 externos (102) | NO EJECUTADOS | Bloquea etiqueta estable certificada |
| Actualización con mes DANE nuevo | NO EJECUTADA | Bloquea operación mensual certificada |
| Homologación sectorial y retropolación antigua | Hipótesis explícitas, estimación H16 congelada | No reclasificar a observada/oficial |
| Estadística sectorial departamental | Experimental | No equivale a GEIH oficial |

Regla: para una versión estable de software no basta con que pase la contabilidad; hay que completar regresiones y ensayo con fuente nueva. Los productos de investigación sí pueden distribuirse con etiqueta expresa.

## Integración continua

El workflow `h20-delivery-smoke.yml` comprueba solamente el paquete portable
(`H20` y vintages). No sustituye los tests integrados que usan datos externos.
El workflow heredado `ci.yml` mantiene verificadores más amplios; no debe
interpretarse como una certificación Golden cuando se ejecuta sin sus artefactos.
