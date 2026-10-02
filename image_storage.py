import os
from urllib.parse import urlsplit
import cloudinary.uploader

def is_remote_image(url):
    parsed = urlsplit(url or '')
    return parsed.scheme == 'https' and parsed.netloc == 'res.cloudinary.com'

class CloudinaryStorage:
    def __init__(self):
        names = ('CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET')
        if not all(os.environ.get(name) for name in names):
            raise RuntimeError('Configurá CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY y CLOUDINARY_API_SECRET.')
        self.options = dict(zip(('cloud_name', 'api_key', 'api_secret'), (os.environ[name] for name in names)))

    def upload(self, stream, public_id):
        result = cloudinary.uploader.upload(stream, public_id=public_id, resource_type='image',
            overwrite=False, timeout=60, **self.options)
        if result.get('public_id') != public_id or not is_remote_image(result.get('secure_url')):
            raise ValueError('Respuesta de almacenamiento inválida.')
        return result['secure_url']

    def delete(self, public_id):
        result = cloudinary.uploader.destroy(public_id, resource_type='image', invalidate=True,
                                            timeout=30, **self.options)
        if result.get('result') not in ('ok', 'not found'):
            raise RuntimeError('No se pudo eliminar la imagen remota.')
