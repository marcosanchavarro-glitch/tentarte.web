import hmac
import os
from pathlib import Path
import secrets
import uuid

from flask import Flask, abort, redirect, render_template, request, session, url_for, flash
from database import Catalog
from image_storage import CloudinaryStorage, is_remote_image
import click
from forms import product_form, string, integer, safe_link, phone_number
from presentation import image_available, image_url, money, product_view, whatsapp_link
from uploads import prepare_image

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

    app.jinja_env.globals.update(csrf=csrf, image_available=image_available, image_url=image_url, money=money)

    @app.context_processor
    def site_context():
        site = catalog.settings()
        return {'site': site, 'contact_link': whatsapp_link(site.get('whatsapp', ''))}

    @app.before_request
    def protect():
        if request.path.startswith('/admin'):
            if not os.environ.get('ADMIN_PASSWORD'):
                abort(503, 'Configurá ADMIN_PASSWORD para habilitar el panel.')
            if request.method == 'POST' and not hmac.compare_digest(request.form.get('csrf', '').encode(), session.get('csrf', '-').encode()):
                abort(400, 'Formulario vencido. Recargá la página.')
            if request.path != '/admin/login' and not session.get('admin'):
                return redirect(url_for('login'))

    @app.get('/')
    def index():
        items = [product_view(p) for p in catalog.list(public=True)]
        return render_template('index.html', products=items, experiences=[p for p in items if p['show_in_experience']], banners=catalog.banner_list(public=True))

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
        return render_template('admin.html', products=catalog.list(), banners=catalog.banner_list())

    @app.get('/tartas/<slug>')
    def product_detail(slug):
        product = catalog.get(slug=slug, public=True)
        if not product:
            abort(404)
        product = product_view(product)
        return render_template('product.html', product=product)

    @app.get('/tartas/<slug>/encargar')
    def order(slug):
        product = catalog.get(slug=slug, public=True)
        if not product:
            abort(404)
        variant = next((v for v in product['variants'] if str(v['size_cm']) == request.args.get('size')), None)
        if not variant:
            abort(400, 'Elegí un tamaño disponible para encargar.')
        choices = []
        for option in product['options']:
            try:
                value = string(request.args.get('option_' + str(option['id'])), 200)
            except ValueError as error:
                abort(400, str(error))
            if option['choices'] and value and value not in option['choices']:
                abort(400)
            if value:
                choices.append(option['name'] + ': ' + value)
        link = whatsapp_link(catalog.settings().get('whatsapp'), product, variant, choices)
        if not link:
            abort(503, 'El contacto para encargos todavía no está configurado.')
        return redirect(link)

    @app.get('/admin/products/new')
    def new_product():
        return render_template('product_edit.html', product=None)

    @app.get('/admin/products/<int:pid>')
    def edit_product(pid):
        product = catalog.get(pid=pid)
        if not product:
            abort(404)
        return render_template('product_edit.html', product=product)

    @app.post('/admin/products')
    @app.post('/admin/products/<int:pid>')
    def save_product(pid=None):
        try:
            if pid and not catalog.exists(pid):
                abort(404)
            if 'editor' not in request.form:
                # Preserve the original create endpoint for existing callers.
                pid = catalog.add(uuid.uuid4().hex, string(request.form.get('name'), 150, True), string(request.form.get('description'), 2000))
            else:
                values, children = product_form(request.form)
                pid = catalog.save_product(pid, values, children, integer(request.form.get('revision', 1), 1, 1000000000))
            photo = request.files.get('image')
            if photo and photo.filename:
                persist_upload('main', pid, None, photo)
            catalog.clean(storage)
            flash('Producto guardado.')
            return redirect(url_for('edit_product', pid=pid))
        except ValueError as error:
            abort(400, str(error))

    def persist_upload(kind, owner, item, file):
        if not catalog.has_media_target(kind, owner, item):
            abort(404)
        try:
            stream = prepare_image(file)
        except ValueError as error:
            abort(400, str(error))
        public_id = 'tentarte/' + uuid.uuid4().hex
        catalog.queue_cleanup(public_id, delay=86400)
        uploaded = False
        try:
            url = storage.upload(stream, public_id)
            uploaded = True
            if kind == 'main':
                catalog.replace_image(owner, '', url, public_id)
            elif kind == 'variant':
                catalog.replace_image(owner, str(item), url, public_id)
            else:
                catalog.save_media(kind, owner, item, url, public_id)
        except Exception:
            if uploaded:
                catalog.queue_cleanup(public_id)
                catalog.clean(storage)
            abort(502, 'No se pudo guardar la imagen. Los datos del producto se conservaron; reintentá la foto desde su edición.')
        catalog.clean(storage)

    @app.post('/admin/products/<int:pid>/image/delete')
    @app.post('/admin/products/<int:pid>/image')
    def product_media(pid):
        kind = request.form.get('kind', 'main')
        size = request.form.get('size', '')
        if size:
            kind = 'variant'
        try:
            item = integer(size or request.form.get('item'), 1, 1000000000) if kind in ('variant', 'layer', 'gallery') else None
            if kind not in ('main', 'cut', 'variant', 'layer', 'gallery') or not catalog.has_media_target(kind, pid, item):
                abort(404)
            if request.path.endswith('/delete'):
                catalog.save_media(kind, pid, item, None, None)
                catalog.clean(storage)
            else:
                file = request.files.get('image')
                if not file or not file.filename:
                    abort(400, 'Seleccioná una imagen.')
                persist_upload(kind, pid, item, file)
            flash('Fotografía actualizada.')
            return redirect(url_for('edit_product', pid=pid))
        except ValueError as error:
            abort(400, str(error))

    @app.post('/admin/settings')
    def site_settings():
        try:
            catalog.save_settings({'whatsapp': phone_number(request.form.get('whatsapp'))})
        except ValueError as error:
            abort(400, str(error))
        flash('Contacto actualizado.')
        return redirect(url_for('admin'))

    @app.get('/admin/banners/new')
    @app.get('/admin/banners/<int:bid>')
    def edit_banner(bid=None):
        banner = next((b for b in catalog.banner_list() if b['id'] == bid), None)
        if bid and not banner:
            abort(404)
        return render_template('banner_edit.html', banner=banner)

    @app.post('/admin/banners')
    @app.post('/admin/banners/<int:bid>')
    def save_banner(bid=None):
        try:
            location = request.form.get('location')
            if location not in ('hero', 'between', 'catalog', 'featured'):
                raise ValueError('Elegí una ubicación válida.')
            values = {k: string(request.form.get(k), limit, k == 'title') for k, limit in
                      (('title', 150), ('subtitle', 300), ('cta', 60))}
            values.update(location=location, link=safe_link(request.form.get('link')), position=integer(request.form.get('position', 0)), active=request.form.get('active') == 'on')
            bid = catalog.save_banner(bid, values, integer(request.form.get('revision', 1), 1, 1000000000))
            file = request.files.get('image')
            if file and file.filename:
                persist_upload('banner', bid, None, file)
            flash('Banner guardado.')
            return redirect(url_for('edit_banner', bid=bid))
        except ValueError as error:
            abort(400, str(error))

    @app.post('/admin/banners/<int:bid>/image/delete')
    def delete_banner_image(bid):
        if not catalog.has_media_target('banner', bid):
            abort(404)
        catalog.save_media('banner', bid, None, None, None)
        catalog.clean(storage)
        return redirect(url_for('edit_banner', bid=bid))

    @app.errorhandler(400)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(502)
    @app.errorhandler(503)
    def friendly_error(error):
        return render_template('error.html', error=error), error.code

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' https://res.cloudinary.com; style-src 'self'; script-src 'self'; form-action 'self' https://wa.me https://api.whatsapp.com; frame-ancestors 'none'"
        return response

    return app

if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5000)
