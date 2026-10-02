# Tentarte

Base de catálogo con Flask, SQLite y subidas persistentes. El repositorio original estaba vacío; esta implementación no incluye checkout, pagos ni gestión de pedidos.

## Ejecutar en PowerShell

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:ADMIN_PASSWORD = 'elegí-una-contraseña-larga'
.venv\Scripts\python app.py
```

Abrir http://127.0.0.1:5000 y `/admin`. El panel queda deshabilitado si no hay contraseña configurada. Para un despliegue público, usar un servidor WSGI de producción detrás de HTTPS, establecer `HTTPS=1` y limitar intentos de login en el proxy.

## Imágenes iniciales

Dejar los archivos recibidos en la raíz o en una subcarpeta del proyecto y ejecutar `python organize_assets.py`. También se organizan al arrancar. El organizador mueve los archivos, elimina copias idénticas y conserva los archivos diferentes si existe un conflicto, que se informa en consola. No examina entornos virtuales, dependencias ni almacenamiento de subidas. No busca fuera del proyecto.

| Archivo | Destino |
|---|---|
| oreo.jpg | public/images/products/oreo/oreo.jpg |
| banoffee.jpg | public/images/products/banoffee/banoffee.jpg |
| toffee.jpg | public/images/products/toffee/toffee.jpg |
| tentarte-logo.png | public/images/branding/tentarte-logo.png |
| banner-tentarte.jpg | public/images/banners/banner-tentarte.jpg |

Las URLs públicas empiezan en `/images/`, sin `public`. Los seeds son idempotentes y no reemplazan cambios del panel. Cada producto tiene variantes de 28 y 12 cm. Una variante sin fotografía propia usa la principal; las tres fotos iniciales se identifican como referencias de 28 cm. No se generan fotografías. Cuando falta una foto se muestra texto; logo y banner son opcionales.

## Almacenamiento del panel

Valen puede crear productos y cargar imágenes principales o por tamaño desde `/admin`. Las imágenes se validan por contenido y se recodifican como JPEG, con nombres aleatorios y sin metadatos originales. Al reemplazar una subida se elimina la anterior si ya no está referenciada.

SQLite, clave de sesión y fotos se guardan en `instance/`, fuera de los assets iniciales y de Git. `TENTARTE_DATA_DIR` permite elegir un directorio o volumen persistente. Respaldar ese directorio completo. En hosting con disco efímero es obligatorio montar almacenamiento persistente; esta versión está pensada para una sola instancia del servidor y no incluye un proveedor de almacenamiento remoto.

## Publicación en Render

El archivo `render.yaml` configura un servicio Python con Gunicorn y un disco persistente de 1 GB para SQLite, fotografías y clave de sesión. Requiere un plan pago (Starter); revisar y aprobar el costo en Render antes de crear el servicio. No desplegar esta configuración sobre disco efímero.

Con el repositorio subido a GitHub, crear un Blueprint en Render conectado a ese repositorio. Render genera `ADMIN_PASSWORD`; consultarla desde las variables de entorno del servicio para ingresar a `/admin`. No guardar esa contraseña en Git. Las siguientes publicaciones del repositorio se despliegan según la configuración de actualización automática de Render.

## Verificación local

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```
