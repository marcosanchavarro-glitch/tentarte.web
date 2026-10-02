import hmac
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import uuid
import warnings
from contextlib import contextmanager

from flask import Flask, abort, redirect, render_template, request, send_from_directory, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
from organize_assets import organize

ROOT = Path(__file__).resolve().parent

def create_app(data_dir=None):
    app = Flask(__name__, static_folder='public', static_url_path='')
    data = Path(data_dir or os.environ.get('TENTARTE_DATA_DIR', ROOT / 'instance')).resolve()
    uploads = data / 'uploads'
    uploads.mkdir(parents=True, exist_ok=True)
    key = data / 'session.key'
    if not key.exists():
        try:
            with key.open('x') as file:
                file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    app.config.update(SECRET_KEY=key.read_text(), MAX_CONTENT_LENGTH=9 * 1024 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('HTTPS') == '1')
    organize()

    @contextmanager
    def db():
        conn = sqlite3.connect(data / 'catalog.sqlite3')
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    with db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS products (
              id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
              description TEXT NOT NULL, image TEXT);
            CREATE TABLE IF NOT EXISTS variants (
              product_id INTEGER REFERENCES products(id), size_cm INTEGER NOT NULL,
              image TEXT, PRIMARY KEY(product_id, size_cm));
        ''')
        for product in json.loads((ROOT / 'seeds/products.json').read_text(encoding='utf-8')):
            conn.execute('INSERT OR IGNORE INTO products(slug,name,description,image) VALUES(?,?,?,?)',
                         tuple(product[k] for k in ('slug', 'name', 'description', 'image')))
            pid = conn.execute('SELECT id FROM products WHERE slug=?', (product['slug'],)).fetchone()['id']
            for variant in product['variants']:
                conn.execute('INSERT OR IGNORE INTO variants VALUES(?,?,?)', (pid, variant['size_cm'], variant['image']))

    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        return session['csrf']

    def image_available(path):
        if not path:
            return None
        if path.startswith('/uploads/'):
            return path if (uploads / Path(path).name).is_file() else None
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

    def products():
        with db() as conn:
            result = [dict(row) for row in conn.execute('SELECT * FROM products ORDER BY id')]
            for product in result:
                product['variants'] = [dict(row) for row in conn.execute('SELECT * FROM variants WHERE product_id=? ORDER BY size_cm DESC', (product['id'],))]
            return result

    @app.get('/')
    def index():
        return render_template('index.html', products=products())

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
        return render_template('admin.html', products=products())

    @app.post('/admin/products')
    def add_product():
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        if not name or len(name) > 150 or len(description) > 2000:
            abort(400, 'Revisá el nombre y la descripción.')
        with db() as conn:
            cursor = conn.execute('INSERT INTO products(slug,name,description) VALUES(?,?,?)', (uuid.uuid4().hex, name, description))
            conn.executemany('INSERT INTO variants VALUES(?,?,NULL)', [(cursor.lastrowid, 28), (cursor.lastrowid, 12)])
        return redirect(url_for('admin'))

    @app.post('/admin/products/<int:pid>/image')
    def upload(pid):
        size = request.form.get('size', '')
        if size not in ('', '12', '28'):
            abort(400)
        with db() as conn:
            if not conn.execute('SELECT id FROM products WHERE id=?', (pid,)).fetchone():
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
        filename = uuid.uuid4().hex + '.jpg'
        target = uploads / filename
        photo.save(target, 'JPEG', quality=90)
        try:
            with db() as conn:
                if size:
                    old = conn.execute('SELECT image FROM variants WHERE product_id=? AND size_cm=?', (pid, int(size))).fetchone()['image']
                    conn.execute('UPDATE variants SET image=? WHERE product_id=? AND size_cm=?', ('/uploads/' + filename, pid, int(size)))
                else:
                    old = conn.execute('SELECT image FROM products WHERE id=?', (pid,)).fetchone()['image']
                    conn.execute('UPDATE products SET image=? WHERE id=?', ('/uploads/' + filename, pid))
        except Exception:
            target.unlink(missing_ok=True)
            raise
        if old and old.startswith('/uploads/'):
            with db() as conn:
                used = conn.execute('SELECT image FROM products WHERE image=? UNION ALL SELECT image FROM variants WHERE image=?', (old, old)).fetchone()
            if not used:
                (uploads / Path(old).name).unlink(missing_ok=True)
        return redirect(url_for('admin'))

    @app.get('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(uploads, filename, mimetype='image/jpeg', max_age=31536000)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'"
        return response

    return app

if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5000)
