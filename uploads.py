import io
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

def prepare_image(file):
    raw = file.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('La imagen debe pesar menos de 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in ('JPEG', 'PNG', 'WEBP') or original.width * original.height > 25_000_000:
                    raise ValueError('Usá JPG, PNG o WebP de hasta 25 megapíxeles.')
                photo = ImageOps.exif_transpose(original)
                transparent = photo.mode in ('RGBA', 'LA') or 'transparency' in photo.info
                photo = photo.convert('RGBA' if transparent else 'RGB')
                photo.thumbnail((2400, 2400))
                stream = io.BytesIO()
                photo.save(stream, 'PNG' if transparent else 'JPEG', **({} if transparent else {'quality': 88}))
                stream.seek(0)
                return stream
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('El archivo no es una imagen válida.') from None
