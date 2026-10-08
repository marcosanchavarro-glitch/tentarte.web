import io
import json
from pathlib import Path
from urllib.parse import unquote
from unittest.mock import patch
from PIL import Image
from sqlalchemy import create_engine, text, update, delete
from werkzeug.datastructures import MultiDict, FileStorage
import unittest
import test_assets
from database import Catalog, products, variants
from presentation import product_view
from uploads import prepare_image


class EvolutionTests(unittest.TestCase):
    setUp = test_assets.CatalogTests.setUp
    login = test_assets.CatalogTests.login
    photo = test_assets.CatalogTests.photo
    def form(self, product=None, **changes):
        data = MultiDict({'editor': '1', 'name': 'Tarta de prueba', 'description': 'Descripción real',
                          'published': 'on', 'show_in_experience': 'on', 'visual_experience_enabled': 'on',
                          'revision': str(product['revision'] if product else 1)})
        for key, values in {'variant_name':['Mini','Grande'], 'variant_size':['12','28'],
                            'variant_price':['5100','20100'], 'variant_active':['1','1'],
                            'variant_original':['12','28'] if product else ['',''],
                            'component_name':['Base','Crema'], 'component_id':['','']}.items():
            data.setlist(key, values)
        for key, value in changes.items():
            data.setlist(key, value if isinstance(value, list) else [value])
        return data

    def save(self, data, pid=None):
        data['csrf'] = self.token
        return self.client.post('/admin/products' + ('/' + str(pid) if pid else ''), data=data)

    def test_full_product_lifecycle_and_progressive_experience(self):
        self.token = self.login()
        self.assertEqual(self.client.get('/admin/products/new').status_code, 200)
        data = self.form()
        data['image'] = (self.photo(), 'main.png')
        response = self.save(data)
        self.assertEqual(response.status_code, 302)
        pid = int(response.location.rsplit('/', 1)[1])
        product = self.catalog.get(pid=pid)
        self.assertEqual(product_view(product)['experience_level'], 1)
        self.assertIn(product['name'], self.client.get('/').text)
        detail = self.client.get('/tartas/' + product['slug'])
        self.assertEqual(detail.status_code, 200)
        self.assertIn('$5.100', detail.text)
        self.assertIn('$20.100', detail.text)
        self.assertIn(f'action="/admin/products/{pid}/image"', self.client.get(response.location).text)
        order = self.client.get('/tartas/' + product['slug'] + '/encargar?size=12&price=1')
        self.assertIn('https://wa.me/5491166452510?', order.location)
        self.assertIn('Precio: $5.100', unquote(order.location))
        self.assertEqual(self.client.get('/tartas/' + product['slug'] + '/encargar?size=99').status_code, 400)
        self.assertEqual(self.client.post(f'/admin/products/{pid}/image', data={'csrf':self.token, 'kind':'cut', 'image':(self.photo(),'cut.png')}).status_code, 302)
        product = self.catalog.get(pid=pid)
        self.assertEqual(product_view(product)['experience_level'], 2)
        data = self.form(product, layer_name=['Base','Crema'], layer_id=['',''], layer_description=['',''], option_name=['Mensaje'], option_id=[''], option_choices=[''])
        self.assertEqual(self.save(data, pid).status_code, 302)
        product = self.catalog.get(pid=pid)
        for layer in product['layers']:
            self.assertEqual(self.client.post(f'/admin/products/{pid}/image', data={'csrf':self.token,'kind':'layer','item':str(layer['id']),'image':(self.photo(),'layer.png')}).status_code, 302)
        product = self.catalog.get(pid=pid)
        self.assertEqual(product_view(product)['experience_level'], 3)
        page = self.client.get('/').text
        self.assertIn('data-explode', page)
        option = product['options'][0]['id']
        order = self.client.get('/tartas/' + product['slug'] + f'/encargar?size=28&option_{option}=Feliz%20cumple')
        self.assertIn('Mensaje: Feliz cumple', unquote(order.location))
        self.assertEqual(self.client.get('/tartas/' + product['slug'] + f'/encargar?size=28&option_{option}=' + 'a'*201).status_code, 400)
        data = self.form(product, published='')
        self.assertEqual(self.save(data, pid).status_code, 302)
        self.assertEqual(self.client.get('/tartas/' + product['slug']).status_code, 404)
        self.assertNotIn(product['name'], self.client.get('/').text)
        self.assertGreaterEqual(self.storage.delete.call_count, 2)

    def test_prices_settings_and_edits_survive_restart(self):
        self.token = self.login()
        p = self.catalog.get(pid=1)
        self.assertEqual({v['size_cm']:v['price_cents'] for v in p['variants']}, {28:2500000,12:620000})
        data = self.form(p, variant_name=['Mini','Grande','Especial'],variant_size=['12','28','20'],variant_price=['7000','27000','15000'],variant_active=['1','1','0'],variant_original=['12','28',''])
        self.assertEqual(self.save(data, 1).status_code, 302)
        self.assertEqual(self.save(data, 1).status_code, 400)  # stale form cannot overwrite
        self.catalog.save_settings({'whatsapp':'5491100000000'})
        restart = Catalog(self.config['DATABASE_URL'])
        self.addCleanup(restart.engine.dispose)
        self.assertEqual(restart.get(pid=1)['name'], 'Tarta de prueba')
        self.assertEqual(restart.get(pid=1)['variants'][0]['price_cents'], 2700000)
        self.assertEqual(restart.settings()['whatsapp'], '5491100000000')
        self.assertEqual(len(restart.get(pid=1,public=True)['variants']), 2)
        self.assertEqual(self.client.get('/tartas/oreo/encargar?size=20').status_code, 400)

    def test_banners_validation_and_remote_cleanup(self):
        token = self.login()
        self.assertEqual(self.client.get('/admin/banners/new', follow_redirects=True).status_code, 200)
        values = {'csrf':token,'title':'Una pausa dulce','subtitle':'Por encargo','cta':'Ver tartas','link':'/#tartas','location':'between','position':'2','active':'on','image':(self.photo(),'banner.png')}
        response = self.client.post('/admin/banners', data=values)
        self.assertEqual(response.status_code, 302)
        banner = self.catalog.banner_list()[0]
        self.assertIn('Una pausa dulce', self.client.get('/').text)
        self.assertEqual(self.client.get(response.location, follow_redirects=True).status_code, 200)
        values.pop('image')
        values.update(revision=str(banner['revision']),active='',link='javascript:alert(1)')
        self.assertEqual(self.client.post(response.location,data=values).status_code,400)
        values['link'] = '/#tartas'
        self.assertEqual(self.client.post(response.location,data=values).status_code,302)
        self.assertNotIn('Una pausa dulce', self.client.get('/').text)
        self.client.post(response.location + '/image/delete',data={'csrf':token})
        self.storage.delete.assert_called_with(banner['image_id'])

    def test_transparency_survives_memory_upload(self):
        buffer = io.BytesIO()
        Image.new('RGBA',(5,5),(255,0,0,0)).save(buffer,'PNG')
        buffer.seek(0)
        output = prepare_image(FileStorage(buffer,filename='transparent.png'))
        with Image.open(output) as image:
            self.assertEqual(image.format,'PNG')
            self.assertEqual(image.getpixel((0,0))[3],0)

    def test_migration_preserves_legacy_data_and_does_not_reseed_later(self):
        url = 'sqlite:///' + (Path(self.tmp.name)/'legacy.db').as_posix()
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE products (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL, image TEXT, image_id TEXT)'))
            conn.execute(text('CREATE TABLE variants (product_id INTEGER NOT NULL, size_cm INTEGER NOT NULL, image TEXT, image_id TEXT, PRIMARY KEY(product_id,size_cm))'))
            conn.execute(text("INSERT INTO products VALUES(1,'oreo','Nombre editado','Base + Crema','https://res.cloudinary.com/demo/image/upload/original.png','tentarte/original')"))
            conn.execute(text("INSERT INTO variants VALUES(1,12,NULL,NULL)"))
        engine.dispose()
        catalog = Catalog(url)
        self.addCleanup(catalog.engine.dispose)
        p = catalog.get(pid=1)
        self.assertEqual(p['name'],'Nombre editado')
        self.assertEqual(p['image_id'],'tentarte/original')
        self.assertEqual([c['name'] for c in p['components']],['Base','Crema'])
        with catalog.engine.begin() as conn:
            conn.execute(delete(variants).where((variants.c.product_id==1)&(variants.c.size_cm==28)))
        restarted = Catalog(url)
        self.addCleanup(restarted.engine.dispose)
        self.assertEqual(len(restarted.get(pid=1)['variants']),1)
        self.assertEqual(len(restarted.get(pid=1)['components']),2)
