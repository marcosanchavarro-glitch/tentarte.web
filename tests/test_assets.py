import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from PIL import Image
from app import create_app
from organize_assets import organize


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'ADMIN_PASSWORD': 'test-password'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = create_app(self.tmp.name)
        self.app.testing = True
        self.client = self.app.test_client()

    def login(self):
        self.client.get('/admin/login')
        with self.client.session_transaction() as session:
            token = session['csrf']
        self.assertEqual(self.client.post('/admin/login', data={'csrf': token, 'password': 'test-password'}).status_code, 302)
        self.client.get('/admin')
        with self.client.session_transaction() as session:
            return session['csrf']

    def photo(self):
        # Synthetic test fixture only, never saved as a product asset.
        buffer = io.BytesIO()
        Image.new('RGB', (10, 10), 'white').save(buffer, 'PNG')
        buffer.seek(0)
        return buffer

    def test_missing_assets_and_seed_idempotence(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Tarta Banoffee', response.text)
        create_app(self.tmp.name)
        with closing(sqlite3.connect(Path(self.tmp.name) / 'catalog.sqlite3')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM products').fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT count(*) FROM variants').fetchone()[0], 6)
            self.assertEqual(conn.execute('SELECT count(*) FROM variants WHERE image IS NOT NULL').fetchone()[0], 0)

    def test_auth_and_invalid_upload(self):
        self.assertEqual(self.client.get('/admin').status_code, 302)
        token = self.login()
        self.assertEqual(self.client.post('/admin/products/1/image', data={'csrf': token, 'image': (io.BytesIO(b'bad'), 'photo.jpg')}).status_code, 400)
        self.assertEqual(self.client.post('/admin/products', data={'name': 'Fail'}).status_code, 400)
        self.assertEqual(list((Path(self.tmp.name) / 'uploads').iterdir()), [])

    def test_upload_replace_variant_and_restart(self):
        token = self.login()
        def upload(size=''):
            response = self.client.post('/admin/products/1/image', data={'csrf': token, 'size': size, 'image': (self.photo(), '../../photo.png')})
            self.assertEqual(response.status_code, 302)
        upload()
        first = next((Path(self.tmp.name) / 'uploads').iterdir())
        page = self.client.get('/').text
        self.assertEqual(page.count('/uploads/' + first.name), 2)
        response = self.client.get('/uploads/' + first.name)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/jpeg')
        response.close()
        upload()
        self.assertFalse(first.exists())
        upload('12')
        self.assertEqual(len(list((Path(self.tmp.name) / 'uploads').iterdir())), 2)
        restarted = create_app(self.tmp.name).test_client()
        self.assertEqual(restarted.get('/').text.count('/uploads/'), 2)
        self.assertEqual(self.client.post('/admin/products', data={'csrf': token, 'name': 'Nueva tarta', 'description': 'Prueba'}).status_code, 302)
        self.assertIn('Nueva tarta', self.client.get('/').text)

    def test_organizer_moves_deduplicates_and_preserves_conflicts(self):
        root = Path(self.tmp.name)
        (root / 'incoming').mkdir()
        (root / 'oreo.jpg').write_bytes(b'original')
        (root / 'incoming/oreo.jpg').write_bytes(b'original')
        organize(root)
        target = root / 'public/images/products/oreo/oreo.jpg'
        self.assertEqual(target.read_bytes(), b'original')
        self.assertFalse((root / 'oreo.jpg').exists())
        self.assertFalse((root / 'incoming/oreo.jpg').exists())
        (root / 'oreo.jpg').write_bytes(b'different')
        organize(root)
        self.assertEqual((root / 'oreo.jpg').read_bytes(), b'different')
        self.assertEqual(target.read_bytes(), b'original')

if __name__ == '__main__':
    unittest.main()
