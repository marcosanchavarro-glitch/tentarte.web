import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from PIL import Image
from app import create_app
from organize_assets import organize
from database import Catalog, cleanup, products, variants
from sqlalchemy import select, update
from image_storage import CloudinaryStorage


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'ADMIN_PASSWORD': 'test-password'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.config = {'TESTING': True, 'SECRET_KEY': 'test-key',
                       'DATABASE_URL': 'sqlite:///' + (Path(self.tmp.name) / 'test.sqlite3').as_posix()}
        self.storage = Mock()
        self.storage.upload.side_effect = lambda stream, pid: 'https://res.cloudinary.com/test/image/upload/' + pid + '.jpg'
        self.app = create_app(self.config, self.storage)
        self.catalog = self.app.extensions['catalog']
        self.addCleanup(self.catalog.engine.dispose)
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
        restarted = create_app(self.config, self.storage)
        self.addCleanup(restarted.extensions['catalog'].engine.dispose)
        rows = restarted.extensions['catalog'].list()
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(len(p['variants']) for p in rows), 6)
        self.assertTrue(all(v['image'] is None for p in rows for v in p['variants']))

    def test_auth_and_invalid_upload(self):
        self.assertEqual(self.client.get('/admin').status_code, 302)
        token = self.login()
        self.assertEqual(self.client.post('/admin/products/1/image', data={'csrf': token, 'image': (io.BytesIO(b'bad'), 'photo.jpg')}).status_code, 400)
        self.assertEqual(self.client.post('/admin/products', data={'name': 'Fail'}).status_code, 400)
        self.storage.upload.assert_not_called()
        self.assertFalse((Path(self.tmp.name) / 'uploads').exists())

    def test_upload_replace_variant_and_restart(self):
        token = self.login()
        def upload(size=''):
            response = self.client.post('/admin/products/1/image', data={'csrf': token, 'size': size, 'image': (self.photo(), '../../photo.png')})
            self.assertEqual(response.status_code, 302)
        upload()
        first = self.catalog.list()[0]['image_id']
        page = self.client.get('/').text
        self.assertEqual(page.count(first), 2)
        self.assertIn('https://res.cloudinary.com', self.client.get('/').headers['Content-Security-Policy'])
        upload()
        self.storage.delete.assert_called_with(first)
        upload('12')
        restarted = create_app(self.config, self.storage)
        self.addCleanup(restarted.extensions['catalog'].engine.dispose)
        self.assertEqual(restarted.test_client().get('/').text.count('https://res.cloudinary.com'), 2)
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

    def upload(self, token, size=''):
        return self.client.post('/admin/products/1/image', data={
            'csrf': token, 'size': size, 'image': (self.photo(), 'photo.png')})

    def test_remote_failure_preserves_previous_photo_and_retries_cleanup(self):
        token = self.login()
        self.upload(token)
        before = self.catalog.list()[0]['image']
        self.storage.upload.side_effect = RuntimeError('provider unavailable')
        self.storage.delete.side_effect = RuntimeError('provider unavailable')
        self.assertEqual(self.upload(token).status_code, 502)
        self.assertEqual(self.catalog.list()[0]['image'], before)
        with self.catalog.engine.connect() as conn:
            self.assertEqual(len(conn.execute(select(cleanup)).all()), 1)
        self.storage.delete.side_effect = None
        with patch('database.time.time', return_value=4_000_000_000):
            result = self.app.test_cli_runner().invoke(args=['cleanup-images'])
        self.assertEqual(result.exit_code, 0)
        with self.catalog.engine.connect() as conn:
            self.assertEqual(conn.execute(select(cleanup)).all(), [])

    def test_database_failure_cleans_new_remote_upload(self):
        token = self.login()
        before = self.catalog.list()[0]['image']
        with patch.object(self.catalog, 'replace_image', side_effect=RuntimeError('database unavailable')):
            self.assertEqual(self.upload(token).status_code, 502)
        self.assertEqual(self.catalog.list()[0]['image'], before)
        self.storage.delete.assert_called_once()

    def test_delete_variant_falls_back_and_shared_image_is_preserved(self):
        token = self.login()
        self.upload(token)
        product = self.catalog.list()[0]
        self.catalog.replace_image(1, '12', product['image'], product['image_id'])
        self.client.post('/admin/products/1/image/delete', data={'csrf': token, 'size': '12'})
        self.storage.delete.assert_not_called()
        self.assertEqual(self.client.get('/').text.count(product['image']), 2)
        self.client.post('/admin/products/1/image/delete', data={'csrf': token})
        self.storage.delete.assert_called_with(product['image_id'])
        self.assertIsNone(self.catalog.list()[0]['image'])
        self.assertIn('Foto pendiente', self.client.get('/').text)

    def test_static_delete_does_not_delete_repository_file(self):
        token = self.login()
        self.client.post('/admin/products/1/image/delete', data={'csrf': token})
        self.storage.delete.assert_not_called()
        self.assertTrue(Path('public/images/products/oreo/oreo.jpg').is_file())

    def test_cleanup_failure_does_not_undo_replacement(self):
        token = self.login()
        self.upload(token)
        old = self.catalog.list()[0]['image_id']
        self.storage.delete.side_effect = RuntimeError('offline')
        self.assertEqual(self.upload(token).status_code, 302)
        self.assertNotEqual(self.catalog.list()[0]['image_id'], old)
        result = self.app.test_cli_runner().invoke(args=['cleanup-images'])
        self.assertNotEqual(result.exit_code, 0)
        self.storage.delete.side_effect = None
        self.assertEqual(self.catalog.clean(self.storage), 0)

    def test_cloudinary_adapter_uses_stream_and_invalidates_deletions(self):
        with patch.dict(os.environ, {'CLOUDINARY_CLOUD_NAME': 'test', 'CLOUDINARY_API_KEY': 'key', 'CLOUDINARY_API_SECRET': 'secret'}):
            storage = CloudinaryStorage()
        with patch('cloudinary.uploader.upload', return_value={'public_id': 'tentarte/test', 'secure_url': 'https://res.cloudinary.com/test/photo.jpg'}) as upload:
            stream = self.photo()
            self.assertTrue(storage.upload(stream, 'tentarte/test').startswith('https://'))
            self.assertIs(upload.call_args.args[0], stream)
            self.assertFalse(upload.call_args.kwargs['overwrite'])
        with patch('cloudinary.uploader.destroy', return_value={'result': 'not found'}) as destroy:
            storage.delete('tentarte/test')
            self.assertTrue(destroy.call_args.kwargs['invalidate'])

    def test_configuration_requires_external_database_and_stable_key(self):
        with patch.dict(os.environ, {'SECRET_KEY': '', 'DATABASE_URL': ''}):
            with self.assertRaisesRegex(RuntimeError, 'SECRET_KEY'):
                create_app(storage=self.storage)
        with patch.dict(os.environ, {'SECRET_KEY': 'test', 'DATABASE_URL': 'sqlite:///:memory:'}):
            with self.assertRaisesRegex(RuntimeError, 'PostgreSQL'):
                create_app(storage=self.storage)

if __name__ == '__main__':
    unittest.main()
