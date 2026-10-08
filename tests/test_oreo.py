import unittest
from urllib.parse import unquote
from sqlalchemy import update
import test_assets
from database import products
from database import Catalog, layers
from presentation import product_view
from PIL import Image
from pathlib import Path


class OreoTests(unittest.TestCase):
    setUp = test_assets.CatalogTests.setUp
    login = test_assets.CatalogTests.login
    photo = test_assets.CatalogTests.photo

    def test_package_layers_transparency_and_restart_preserves_admin_changes(self):
        product = self.catalog.get(slug='oreo')
        view = product_view(product)
        self.assertEqual(len(view['oreo_layers']), 4)
        self.assertEqual(len({l['image'] for l in view['oreo_layers']}), 4)
        for layer in view['oreo_layers']:
            with Image.open(Path('public') / layer['image'].lstrip('/')) as image:
                self.assertEqual(image.getchannel('A').getextrema(), (0, 255))
        self.assertIn('data-oreo-photo="layers"', self.client.get('/').text)
        with self.catalog.engine.begin() as conn:
            conn.execute(update(products).where(products.c.id == product['id']).values(image='/images/products/oreo/oreo.jpg'))
            conn.execute(update(layers).where(layers.c.id == product['layers'][0]['id']).values(image=None))
        restarted = Catalog(self.config['DATABASE_URL'])
        self.addCleanup(restarted.engine.dispose)
        after = restarted.get(slug='oreo')
        self.assertEqual(after['image'], '/images/products/oreo/oreo.jpg')
        self.assertEqual(len(after['gallery']), len(product['gallery']))
        self.assertEqual(product_view(after)['oreo_layers'], [])

    def test_exclusive_component_missing_cut_and_orders_unchanged(self):
        with self.catalog.engine.begin() as conn:
            conn.execute(update(products).where(products.c.slug == 'oreo').values(cut_image=None))
        home = self.client.get('/').text
        self.assertEqual(home.count('data-oreo-experience'), 1)
        self.assertNotIn('data-explode', home)
        self.assertIn('disabled aria-describedby="oreo-home-pending"', home)
        self.assertNotIn('data-oreo-photo="interior"', home)
        self.assertIn('data-oreo-photo="whole"', home)
        for slug, price in [('oreo', '$6.200'), ('banoffee', '$5.500'), ('toffee', '$5.000')]:
            page = self.client.get('/tartas/' + slug).text
            self.assertEqual('data-oreo-experience' in page, slug == 'oreo')
            self.assertIn(price, page)
            order = self.client.get('/tartas/' + slug + '/encargar?size=12')
            self.assertIn('https://wa.me/5491166452510?', order.location)
            self.assertIn(price, unquote(order.location))
        self.assertIn('href="#oreo-experience"', self.client.get('/tartas/oreo').text)

    def test_admin_cut_upload_enables_both_views_without_enabling_layers(self):
        token = self.login()
        response = self.client.post('/admin/products/1/image', data={
            'csrf': token, 'kind': 'cut', 'image': (self.photo(), 'cut.png')})
        self.assertEqual(response.status_code, 302)
        for url in ('/', '/tartas/oreo'):
            page = self.client.get(url).text
            self.assertIn('data-oreo-photo="interior"', page)
            self.assertIn('Vista del interior de Oreo', page)
            self.assertNotIn('disabled aria-describedby="oreo-', page)
            self.assertNotIn('data-explode', page)
            self.assertIn('https://res.cloudinary.com/test/', page)

    def test_publication_controls_and_missing_asset_fallback(self):
        with self.catalog.engine.begin() as conn:
            conn.execute(update(products).where(products.c.slug == 'oreo').values(cut_image='/images/missing-cut.jpg'))
        self.assertNotIn('data-oreo-photo="interior"', self.client.get('/').text)
        with self.catalog.engine.begin() as conn:
            conn.execute(update(products).where(products.c.slug == 'oreo').values(visual_experience_enabled=False))
        self.assertNotIn('data-oreo-experience', self.client.get('/').text)
        self.assertNotIn('data-oreo-experience', self.client.get('/tartas/oreo').text)
        self.assertIn('Tarta Oreo', self.client.get('/').text)
