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

La experiencia mejora automáticamente según el contenido disponible:

1. Principal: presentación y composición.
2. Principal + corte: botón para revelar el interior.
3. Principal + corte + imágenes de todas las capas, con experiencia avanzada habilitada: separación, nombres, reconstrucción y corte.

Las capas se ordenan desde la base hacia arriba y aceptan PNG transparente. Sin todos los assets, se muestra el nivel disponible. Las fotos de corte y capas no están inventadas ni incluidas en los productos iniciales.

`forms.py` valida los formularios; `presentation.py` arma las vistas y enlaces; `uploads.py` procesa archivos en memoria. Las imágenes de Cloudinary usan transformaciones de tamaño/calidad/formato y `srcset`. Las fotos fuera del hero cargan de forma diferida. Se usa el logo transparente actualizado del repositorio, sin agregar fondos ni contenedores visibles.

## Migraciones de esta versión

`migrations.py` aplica cambios **aditivos y transaccionales** al inicio. Agrega columnas a `products` y `variants` y crea `product_components`, `product_visual_layers`, `product_images`, `product_options`, `banners`, `site_settings` y `schema_migrations`. Conserva identificadores, URLs, public IDs, nombres y descripciones anteriores. PostgreSQL usa un bloqueo asesor para evitar carreras entre procesos al migrar. La cuenta necesita permisos de `CREATE` y `ALTER`.

La composición inicial se deriva de la descripción existente una vez. Las futuras ejecuciones no recrean componentes o variantes eliminadas. Los formularios usan revisión para evitar que una pestaña vieja sobrescriba una edición nueva. Las fotografías se conservan al editar los metadatos y las referencias compartidas se comprueban antes de borrar un recurso remoto.

Antes de actualizar producción, conservar un respaldo/restauración disponible del proveedor PostgreSQL. El despliegue se hace mediante el repositorio y servicio Render existentes; no requiere nuevas variables, comandos ni disco. Una reversión del código no necesita borrar las nuevas columnas o tablas.

El plan gratuito de Render puede suspender el servicio y demorar la primera visita. Es una limitación de infraestructura: no se agregan pings artificiales ni procesos para evitar la suspensión.

Las pruebas de evolución cubren también migración desde el esquema anterior, precios y contacto persistentes, alta/edición/publicación, formularios obsoletos, banners, generación de WhatsApp, transparencia y los tres niveles de experiencia. Los datos de prueba se crean en bases temporales y no se publican.
