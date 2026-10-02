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

Valen sigue seleccionando un archivo y presionando **Guardar fotografía**. Se validan JPG/PNG/WebP (8 MB, 25 megapíxeles), se corrige orientación y se recodifica en memoria a JPEG de hasta 2400 px. La subida va directamente a Cloudinary con un identificador aleatorio. PostgreSQL guarda `image` (URL HTTPS) e `image_id` (public ID), para producto y variante. No se guardan imágenes ni claves de sesión en disco local. La CSP permite `res.cloudinary.com`.

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
