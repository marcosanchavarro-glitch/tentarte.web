# Tentarte

Catálogo Flask con PostgreSQL externo y Cloudinary. Conserva productos, variantes de 28 y 12 cm, autenticación y panel. No requiere un Persistent Disk ni almacenamiento local permanente.

## Variables de entorno

Ver `.env.example`. Configurar las variables en la sesión local o en Render; la app no carga `.env` automáticamente.

- `DATABASE_URL`: PostgreSQL externo, por ejemplo `postgresql://USER:PASSWORD@HOST/DB?sslmode=require`. Usar TLS según el proveedor.
- `SECRET_KEY`: clave aleatoria estable para sesiones, conservada entre despliegues.
- `ADMIN_PASSWORD`: contraseña del panel; sin ella queda deshabilitado.
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: configuración privada del backend.
- `HTTPS`: `1` en Render, `0` en desarrollo HTTP local.

No guardar credenciales en Git. Los archivos `.env` están ignorados; `.env.example` solo contiene placeholders. Si falta PostgreSQL, la clave de sesión o la configuración de Cloudinary, la app falla al iniciar; nunca cambia silenciosamente a almacenamiento local.

## Ejecución local

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# Configurar las variables anteriores en el entorno.
.venv\Scripts\python app.py
```

Abrir http://127.0.0.1:5000 y `/admin`. El esquema se crea en PostgreSQL al iniciar; la cuenta de base de datos debe tener permisos de creación de tablas. Los seeds son idempotentes y respetan los cambios del panel. SQLite se admite exclusivamente en pruebas.

## Imágenes iniciales

Se mantienen las rutas existentes para evitar cambios innecesarios:

| Archivo | Destino |
|---|---|
| oreo.jpg | public/images/products/oreo/oreo.jpg |
| banoffee.jpg | public/images/products/banoffee/banoffee.jpg |
| toffee.jpg | public/images/products/toffee/toffee.jpg |
| tentarte-logo.png | public/images/branding/tentarte-logo.png |
| banner-tentarte.jpg (opcional) | public/images/banners/banner-tentarte.jpg |

Las URLs públicas comienzan en `/images/`. Ejecutar `python organize_assets.py` para organizar archivos iniciales entregados dentro del proyecto; ya no se ejecuta al arrancar el servidor. Conserva conflictos e informa faltantes. No participa en las subidas del panel.

Las fotos iniciales son de 28 cm. La variante de 12 cm reutiliza la principal hasta tener foto propia, con aclaración de referencia. No se generan fotos. Ante una imagen ausente se muestra “Foto pendiente”; logo y banner son opcionales.

## Imágenes del panel

Valen sigue seleccionando un archivo y presionando **Guardar fotografía**. Se validan JPG/PNG/WebP (8 MB, 25 megapíxeles), se corrige orientación y se recodifica en memoria a JPEG o PNG con transparencia, de hasta 2400 px. La subida va directamente a Cloudinary con un identificador aleatorio. PostgreSQL guarda `image` (URL HTTPS) e `image_id` (public ID), para producto, corte, variante, galería, capa y banner. No se guardan imágenes ni claves de sesión en disco local. La CSP permite `res.cloudinary.com`.

Al reemplazar, primero se sube la nueva foto y se confirma el cambio en una transacción; después se elimina la anterior si no tiene referencias. **Eliminar fotografía** permite quitar la principal o la propia de una variante. La variante sin foto vuelve a usar la principal. Las imágenes estáticas nunca se borran físicamente desde el panel.

La tabla `image_cleanup` conserva las eliminaciones pendientes si Cloudinary falla. Se reintentan después de subir/eliminar y mediante:

```powershell
.venv\Scripts\python -m flask --app wsgi cleanup-images
```

En Render o un scheduler externo usar `python -m flask --app wsgi cleanup-images`, con las mismas variables. Devuelve error si persisten fallos. No se crea automáticamente un cron pago. Si no hay actividad en el panel, ejecutar o programar ese comando para completar la limpieza.

Antes de subir se registra el identificador previsto con 24 horas de gracia. Si el proceso termina inesperadamente, un barrido posterior puede eliminar el recurso huérfano. El guardado confirmado elimina ese registro. Un error de subida conserva la foto anterior; un fallo al borrar no revierte una actualización confirmada. Los identificadores no se reutilizan. PostgreSQL y Cloudinary no comparten una transacción: la cola compensa los fallos entre ambos.

## Render

`render.yaml` configura un servicio **free**, Gunicorn y variables externas; no tiene `disk` ni crea una base paga en Render. Al crear el Blueprint, ingresar `DATABASE_URL` y las tres variables de Cloudinary. Render genera `SECRET_KEY` y `ADMIN_PASSWORD`; conservarlas y consultar la contraseña en el panel privado del servicio. Los planes y cuotas de los proveedores externos se gestionan por separado.

Los despliegues pueden descartar el filesystem local sin perder datos ni fotos. La clave estable mantiene válidas las sesiones firmadas. Para publicación pública se recomienda limitar intentos de login mediante el proxy o una capa de protección externa.

## Datos de la versión anterior

No se encontró almacenamiento `instance/` anterior con datos en este proyecto. No se importa automáticamente una base SQLite o fotos locales de otra instalación. Si existieran, respaldarlas y migrarlas a PostgreSQL/Cloudinary antes de cambiar tráfico; conservar la copia anterior hasta verificar la migración. Los productos iniciales se crean desde `seeds/products.json`.

## Pruebas

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

Las pruebas locales usan SQLite temporal y un doble de Cloudinary, sin subidas externas. Cubren autenticación/CSRF, seeds, variantes, validación, reemplazos, eliminaciones, referencias compartidas y recuperación ante fallos. No sustituyen una integración real con los proveedores configurados.

## Rediseño y administración

La aplicación conserva Flask/Jinja, SQLAlchemy Core, PostgreSQL y Cloudinary. No incorpora un framework de frontend ni librerías de animación: el selector, las transiciones y los formularios dinámicos usan JavaScript pequeño y CSS. Se respeta `prefers-reduced-motion`.

- `/`: experiencia interactiva, bloques editoriales, banners y catálogo publicado.
- `/tartas/<slug>`: ficha, tamaños, precios y opciones.
- `/tartas/<slug>/encargar`: valida el tamaño/opciones y construye el enlace oficial `wa.me` con el precio de la base, nunca el enviado por el navegador.
- `/admin`: productos, banners y número central de WhatsApp.
- `/admin/products/new` y `/admin/products/<id>`: información, composición ordenable, variantes, publicación, imágenes y experiencia visual.
- `/admin/banners/new` y `/admin/banners/<id>`: publicaciones con imagen opcional, texto, enlace, ubicación, orden y activación.

Para crear una tarta: completar información, agregar componentes y tamaños/precios, elegir una foto, marcar **Publicado en catálogo** y guardar. No necesita corte ni capas. **Destacado** y **Mostrar en experiencia principal** son independientes de publicar. Para ocultar un producto o banner, desmarcar su publicación/activación y guardar. No hay inventario ni promesas de entrega o pago.

Las variantes comparten el producto y pueden tener imágenes propias. Los precios se guardan como centavos enteros (ARS); un precio vacío permite consultar. La migración inicial incorpora los importes y WhatsApp confirmados por el propietario, una sola vez; las ediciones posteriores del panel se conservan.

Composición, capas, galería y opciones se agregan y reordenan con controles del panel. Para nuevas capas/fotos de galería, crear el espacio y guardar primero; después subir su fotografía. Las opciones con alternativas separadas por `|` ofrecen un selector; sin alternativas permiten texto libre. No agregamos opciones comerciales ficticias.

La experiencia interactiva pública es exclusiva de Oreo. Banoffee, Toffee y los demás productos mantienen su catálogo fotográfico. El bloque editorial existente `experience` aloja `OreoExperience`, sin cambios de base de datos ni infraestructura.

- Foto principal: composición original completa, sin recorte ni ingredientes generados.
- Foto de corte: se carga en Administración → Oreo → Fotografías → Interior / corte. Al cargarla, se habilita «Explorar el interior» con transición reversible. Sin foto válida, el botón queda deshabilitado con explicación; no se reutiliza la foto completa como un corte ficticio.
- La ficha de Oreo incluye acceso a la misma experiencia y regreso al formulario de pedido. Precios, variantes y WhatsApp conservan sus rutas existentes.
- Entrada por scroll de 24 px como máximo, reversible al subir; movimiento reducido desactiva desplazamientos y transiciones. Sin JavaScript se muestran las fotografías disponibles.
- Los campos `product_visual_layers` se conservan para la fase posterior. Los slots previstos son `chocolate-base`, `chocolate-filling`, `oreo-cream` y `decoration`; cada recurso tendrá su propio elemento `.oreo-layer` y desplazamientos `--layer-x` / `--layer-y`. **La animación de capas no está activada**: requiere cuatro recursos independientes con transparencia real, composición alineada y revisión visual. Subir archivos a los campos existentes no activa una separación automática.

Pendientes al implementar esta etapa: foto real del corte y las cuatro capas recortadas. También se comprobó que el panel de producción todavía no tiene una foto de corte de Oreo. Los tests usan imágenes sintéticas únicamente en bases temporales, nunca como fotografías publicadas.

Verificación Oreo: `python -m unittest discover -s tests -v` y `node tests/oreo_motion.cjs`. Esta última comprueba reversibilidad de vistas/scroll, cambio dinámico de movimiento reducido y ausencia de corte. La validación visual del interior real queda pendiente de recibir ese archivo.

`forms.py` valida los formularios; `presentation.py` arma las vistas y enlaces; `uploads.py` procesa archivos en memoria. Las imágenes de Cloudinary usan transformaciones de tamaño/calidad/formato y `srcset`. Las fotos fuera del hero cargan de forma diferida. Se usa el logo transparente actualizado del repositorio, sin agregar fondos ni contenedores visibles.

## Migraciones de esta versión

`migrations.py` aplica cambios **aditivos y transaccionales** al inicio. Agrega columnas a `products` y `variants` y crea `product_components`, `product_visual_layers`, `product_images`, `product_options`, `banners`, `site_settings` y `schema_migrations`. Conserva identificadores, URLs, public IDs, nombres y descripciones anteriores. PostgreSQL usa un bloqueo asesor para evitar carreras entre procesos al migrar. La cuenta necesita permisos de `CREATE` y `ALTER`.

La composición inicial se deriva de la descripción existente una vez. Las futuras ejecuciones no recrean componentes o variantes eliminadas. Los formularios usan revisión para evitar que una pestaña vieja sobrescriba una edición nueva. Las fotografías se conservan al editar los metadatos y las referencias compartidas se comprueban antes de borrar un recurso remoto.

Antes de actualizar producción, conservar un respaldo/restauración disponible del proveedor PostgreSQL. El despliegue se hace mediante el repositorio y servicio Render existentes; no requiere nuevas variables, comandos ni disco. Una reversión del código no necesita borrar las nuevas columnas o tablas.

El plan gratuito de Render puede suspender el servicio y demorar la primera visita. Es una limitación de infraestructura: no se agregan pings artificiales ni procesos para evitar la suspensión.

Las pruebas de evolución cubren también migración desde el esquema anterior, precios y contacto persistentes, alta/edición/publicación, formularios obsoletos, banners, generación de WhatsApp, transparencia y compatibilidad del modelo visual anterior. Los datos de prueba se crean en bases temporales y no se publican.

## Tentarte 3.0: sistema editorial

### Arquitectura y migración

Se amplía `banners` en lugar de duplicar sus imágenes y registros. La migración 3 agrega metadatos editoriales, animación, dimensiones, enlaces tipados, archivo, timestamps UTC y relación opcional con campaña. Crea únicamente `editorial_campaigns` y `home_blocks`. Los banners anteriores mantienen texto, URL, public ID, publicación y ubicación; quedan con presentación `legacy` y sin movimiento inicial. La composición inicial conserva las secciones de la versión anterior. No borra productos ni cambia credenciales, servicio Render o almacenamiento.

`editorial.py` valida y persiste, `editorial_routes.py` proporciona las rutas protegidas, `templates/posters/macros.html` renderiza carteles y `public/editorial.js` ejecuta las animaciones. Los componentes anteriores de la home están separados en `templates/home/` y se recorren según `home_blocks`. El motor es un registro de funciones, no un enum de base de datos: agregar un efecto no exige migrar el esquema.

### Uso para Valen

1. Entrar en **Administración → Carteles → Crear cartel**.
2. Escribir nombre interno y texto alternativo, y elegir PNG/JPG/WebP. Una nueva publicación inicia en **Float · 35 % · Publicado**. Para publicarla debe tener una imagen válida. Puede guardarse como borrador sin imagen.
3. Elegir ubicación, alineación, tamaño, ajuste y orden. `contain` muestra el diseño completo; `cover` es una elección explícita que puede recortar. Las dimensiones originales reservan espacio y las variantes Cloudinary reducen transferencia sin alterar la composición.
4. Elegir movimiento, intensidad y retraso. Al 35 %, Float recorre 6,3 px en un ciclo de 6,02 segundos. Cero intensidad o animación desactivada muestran el cartel estático.
5. Elegir destino (producto, catálogo, sección, ruta conocida o HTTPS externo). Solo enlaces externos admiten nueva pestaña. Los enlaces a productos despublicados se omiten automáticamente.
6. Opcionalmente seleccionar campaña y fechas. Los timestamps son UTC; las entradas se interpretan en `BUSINESS_TIMEZONE` (Buenos Aires por defecto). No necesita un cron: cada visita aplica los límites `inicio <= ahora < vencimiento`, tanto del cartel como de la campaña.
7. **Actualizar vista previa** permite revisar el mismo componente en un marco de escritorio de 1100 px o celular de 390 px; el área tiene desplazamiento horizontal si no entra. La previsualización no publica ni sube a Cloudinary. Después, **Guardar cartel** confirma el contenido.

Duplicar crea un borrador que comparte la imagen original: no consume una segunda subida. Archivar lo oculta y conserva todo; restaurar lo deja como borrador. Eliminar requiere marcar confirmación y elimina el registro, pero solamente borra el recurso remoto si no tiene referencias en ningún producto, variante, corte, capa, galería o cartel. La cola existente conserva los fallos de limpieza.

La subida nueva se prepara en memoria y ocurre antes de confirmar los cambios del cartel. Si falla el guardado, se compensa la subida; si falla Cloudinary, el registro previo se conserva. La vista previa utiliza una imagen temporal dentro de su respuesta privada (`no-store`). Su CSP permite embeberla exclusivamente en el mismo sitio; el resto de la aplicación sigue sin poder embeberse.

### Composición y campañas

**Composición de la home** permite agregar bloques, cambiar su contenido y moverlos con botones accesibles Subir/Bajar. Hero, catálogo completo y cómo encargar son obligatorios y únicos. La selección destacada puede añadirse aparte. Los grupos toman carteles de una ubicación; un bloque individual tiene prioridad y cada cartel se muestra como máximo una vez. La ubicación manual necesita un bloque individual o grupo manual. Conservar un grupo visible para cada ubicación que se quiera usar. Las fechas, archivo y publicación siempre prevalecen sobre la composición. Los cambios de orden se guardan juntos y se rechazan formularios con revisión obsoleta.

**Campañas** permite nombre, activación, inicio, vencimiento y prioridad. Se asocian carteles desde su editor. Una campaña inactiva o fuera de fecha oculta todos sus carteles; no los elimina. La prioridad mayor aparece antes dentro de cada grupo. No se implementan notificaciones push.

### Identidad, accesibilidad y rendimiento

Playfair Display Italic, peso 700, está alojada en el repositorio y se usa en minúsculas en los títulos editoriales. Archivo y licencia proceden de [Google Fonts](https://github.com/google/fonts/tree/main/ofl/playfairdisplay); licencia en `public/fonts/PlayfairDisplay-OFL.txt`. Administración y textos funcionales mantienen una fuente legible. Los adornos de marca usan símbolos SVG, no emojis.

Las animaciones usan Web Animations y transform/opacity; un IntersectionObserver compartido pausa carteles fuera de pantalla y una sola cola de requestAnimationFrame atiende parallax visible. Una pestaña oculta pausa el movimiento. `prefers-reduced-motion` desactiva el motor y también tiene respaldo CSS. Sin JavaScript/IntersectionObserver, los carteles permanecen estáticos y legibles. Imágenes no críticas: lazy loading, dimensiones reservadas y srcset. No se incorporan librerías de animación.

### Verificación

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
node tests/editorial_motion.cjs
```

Las pruebas automatizadas usan bases temporales y Cloudinary simulado. Cubren migraciones anteriores, fechas y límites, permisos/CSRF, enlaces, publicación incompleta, previsualización sin subida, reemplazo fallido, referencias compartidas, duplicación/archivo/eliminación, campañas y protección de composición. La prueba JavaScript valida efectos, amplitud, intensidad cero, movimiento reducido y pausa por visibilidad. La integración real con Cloudinary debe verificarse aparte desde el panel publicado; una prueba simulada no acredita esa integración.
### Verificación de producción — 8 de octubre de 2026

La versión `b30a4cd` se desplegó correctamente en el servicio existente de Render.
Desde `/admin/posters` se subió el logo original: Cloudinary devolvió una URL remota
en `tentarte/editorial/` y la imagen cargó en el panel y en la home. Se verificaron
los valores iniciales Float/35/publicado, la vista previa móvil y la edición a
Tilt/50, ubicación destacada y enlace a Oreo.

Se ejecutó **Restart service** en Render; tras el reinicio, el registro mantuvo la
misma imagen remota, publicación y configuración. El cartel de verificación quedó
archivado y ya no aparece en la home. Los tres productos se conservaron y el pedido
de Oreo de 12 cm abrió WhatsApp con el número configurado y el precio de $6.200.
No se envió un mensaje. Las 23 pruebas de backend y las comprobaciones JavaScript
del movimiento también pasaron; la comprobación de Cloudinary descrita aquí fue
real, adicional a las pruebas con proveedor simulado.

