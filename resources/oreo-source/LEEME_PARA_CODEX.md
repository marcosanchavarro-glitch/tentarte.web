# Tentarte — recursos Oreo 2.5D

Este paquete contiene los originales, versiones optimizadas para web y **cuatro recortes RGBA con transparencia real** para una animación 2.5D.

## Archivos
- `originales/`: imágenes originales sin modificar, más una referencia visual generada.
- `web/oreo_hero.webp`: foto ambientada para hero.
- `web/oreo_superior.webp`: foto superior.
- `web/oreo_tarta_transparente.png`: tarta completa aislada del fondo blanco.
- `web/oreo_corte_transparente.png`: porción aislada.
- `web/oreo_corte.webp`: imagen de respaldo.
- `capas/01_decoracion_oreo.png`: decoración.
- `capas/02_crema_oreo.png`: crema Oreo.
- `capas/03_relleno_chocolate.png`: relleno chocolate.
- `capas/04_base_sablee_chocolate.png`: base.

## Advertencias de calidad
1. Los JPG originales tenían fondo blanco, y los PNG se extrajeron por máscara de color: **revisar bordes claros, especialmente crema blanca** antes de publicar.
2. Los recortes de `capas/` se derivan de una **composición generada**, no de fotografías independientes de cada capa. Son recursos de prototipo; **no afirmar que son una reconstrucción exacta de la tarta real**.
3. Los recortes de las capas incluyen migas decorativas y pueden requerir retoque fino; no son un modelo 3D ni permiten giro 360° real.
4. Mantener siempre la foto real de la porción como modo alternativo. La experiencia se aplica **solo a Oreo**.

## Integración recomendada
- Renderizar capas con imágenes individuales en contenedor relativo, usando transformaciones `translate3d` con valores moderados.
- Posicionar de abajo hacia arriba: base, chocolate, crema y decoración.
- Animar progresivamente y permitir reversa con scroll o controles; no usar una sola imagen plana como sustituto de capas.
- Comprobar layout móvil, carga, accesibilidad y `prefers-reduced-motion`.
- No publicar la vista de capas sin aprobación visual final de Valen.
