import hmac
import io
import os
from pathlib import Path
import secrets
import uuid
import warnings

from flask import Flask, abort, redirect, render_template, request, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
from database import Catalog
from image_storage import CloudinaryStorage, is_remote_image
import click

ROOT = Path(__file__).resolve().parent

def create_app(test_config=None, storage=None):
    app = Flask(__name__, static_folder='public', static_url_path='')
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY'),
                      DATABASE_URL=os.environ.get('DATABASE_URL'),
                      MAX_CONTENT_LENGTH=9 * 1024 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('HTTPS') == '1')
    if test_config:
        app.config.update(test_config)
    if not app.config['SECRET_KEY']:
        raise RuntimeError('Configurá SECRET_KEY con una clave aleatoria estable.')
    database_url = app.config['DATABASE_URL'] or ''
    if not app.testing and not database_url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        raise RuntimeError('Configurá DATABASE_URL con una base PostgreSQL externa.')
    storage = storage or CloudinaryStorage()
    catalog = Catalog(database_url)
    app.extensions['catalog'] = catalog

    @app.cli.command('cleanup-images')
    def cleanup_images():
        failures = catalog.clean(storage)
        if failures:
            raise click.ClickException(f'{failures} imágenes pendientes; reintentá más tarde.')
        click.echo('Limpieza de imágenes completada.')

    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        return session['csrf']

    def image_available(path):
        if not path:
            return None
        if is_remote_image(path):
            return path
        if path.startswith('/images/'):
            candidate = (ROOT / 'public' / path.lstrip('/')).resolve()
            return path if candidate.is_relative_to(ROOT / 'public') and candidate.is_file() else None
        return None

    app.jinja_env.globals.update(csrf=csrf, image_available=image_available)

    @app.before_request
    def protect():
        if request.path.startswith('/admin'):
            if not os.environ.get('ADMIN_PASSWORD'):
                abort(503, 'Configurá ADMIN_PASSWORD para habilitar el panel.')
            if request.method == 'POST' and not hmac.compare_digest(request.form.get('csrf', ''), session.get('csrf', '-') ):
                abort(400, 'Formulario vencido. Recargá la página.')
            if request.path != '/admin/login' and not session.get('admin'):
                return redirect(url_for('login'))

    @app.get('/')
    def index():
        return render_template('index.html', products=catalog.list())

    @app.route('/admin/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            if not hmac.compare_digest(request.form.get('password', '').encode(), os.environ['ADMIN_PASSWORD'].encode()):
                abort(401, 'Contraseña incorrecta.')
            session.clear()
            session['admin'] = True
            return redirect(url_for('admin'))
        return render_template('login.html')

    @app.post('/admin/logout')
    def logout():
        session.clear()
        return redirect(url_for('index'))

    @app.get('/admin')
    def admin():
        return render_template('admin.html', products=catalog.list())

    @app.post('/admin/products')
    def add_product():
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        if not name or len(name) > 150 or len(description) > 2000:
            abort(400, 'Revisá el nombre y la descripción.')
        catalog.add(uuid.uuid4().hex, name, description)
        return redirect(url_for('admin'))

    @app.post('/admin/products/<int:pid>/image')
    def upload(pid):
        size = request.form.get('size', '')
        if size not in ('', '12', '28'):
            abort(400)
        if not catalog.exists(pid):
            abort(404)
        file = request.files.get('image')
        if not file:
            abort(400, 'Seleccioná una imagen.')
        raw = file.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            abort(413)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as original:
                    if original.format not in ('JPEG', 'PNG', 'WEBP') or original.width * original.height > 25_000_000:
                        abort(400, 'Usá JPG, PNG o WebP de hasta 25 megapíxeles.')
                    photo = ImageOps.exif_transpose(original).convert('RGB')
                    photo.thumbnail((2400, 2400))
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            abort(400, 'El archivo no es una imagen válida.')
        stream = io.BytesIO()
        photo.save(stream, 'JPEG', quality=90)
        stream.seek(0)
        public_id = 'tentarte/' + uuid.uuid4().hex
        # Record the intent before the remote call, including ambiguous timeouts.
        catalog.queue_cleanup(public_id, delay=86400)
        uploaded = False
        try:
            url = storage.upload(stream, public_id)
            uploaded = True
            catalog.replace_image(pid, size, url, public_id)
        except Exception:
            # A timed-out upload can still complete remotely. Keep its grace
            # period instead of deleting too early and losing the retry record.
            if uploaded:
                catalog.queue_cleanup(public_id)
                catalog.clean(storage)
            abort(502, 'No se pudo guardar la imagen. La foto anterior se conserva; reintentá más tarde.')
        catalog.clean(storage)
        return redirect(url_for('admin'))

    @app.post('/admin/products/<int:pid>/image/delete')
    def delete_image(pid):
        size = request.form.get('size', '')
        if size not in ('', '12', '28'):
            abort(400)
        if not catalog.exists(pid):
            abort(404)
        catalog.replace_image(pid, size, None, None)
        catalog.clean(storage)
        return redirect(url_for('admin'))

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' https://res.cloudinary.com; style-src 'self'; form-action 'self'; frame-ancestors 'none'"
        return response

    return app

if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5000)
