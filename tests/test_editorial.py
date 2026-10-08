import io
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text, select
from werkzeug.datastructures import MultiDict
import test_assets
from database import Catalog, banners
from editorial import Editorial, parse_date, local_date


class EditorialTests(unittest.TestCase):
    setUp=test_assets.CatalogTests.setUp
    login=test_assets.CatalogTests.login
    photo=test_assets.CatalogTests.photo

    def form(self, **overrides):
        result={'csrf':self.token,'internal_name':'Cartel de prueba','alt_text':'Diseño de prueba accesible',
                'animation_type':'float','animation_intensity':'35','animation_enabled':'on',
                'animation_delay_ms':'0','location':'between','position':'0','alignment':'center',
                'visual_size':'medium','image_fit':'contain','link_type':'none','active':'on','revision':'1'}
        result.update(overrides)
        return result

    def create(self,**overrides):
        data=self.form(**overrides)
        data['image']=(self.photo(),'poster.png')
        response=self.client.post('/admin/posters',data=data)
        self.assertEqual(response.status_code,302,response.text)
        return self.app.extensions['editorial'].get(int(response.location.rsplit('/',1)[-1]))

    def test_create_defaults_publish_edit_and_restart(self):
        self.token=self.login()
        page=self.client.get('/admin/posters/new')
        self.assertEqual(page.status_code,200)
        self.assertIn('value="35"',page.text)
        self.assertIn('value="float" selected',page.text)
        self.assertEqual(self.client.post('/admin/posters',data=self.form()).status_code,400)
        self.storage.upload.assert_not_called()
        p=self.create()
        self.assertEqual((p['animation_type'],p['animation_intensity'],p['active']),('float',35,True))
        self.assertEqual(p['image_width'],10)
        self.assertIn(p['image_id'],self.client.get('/').text)
        for effect in ('parallax','tilt','scroll-reveal','fade','none'):
            data=self.form(revision=str(p['revision']),animation_type=effect,animation_intensity='80',location='hero',position='5')
            self.assertEqual(self.client.post(f"/admin/posters/{p['id']}",data=data).status_code,302)
            p=self.app.extensions['editorial'].get(p['id'])
            self.assertEqual(p['animation_type'],effect)
        data=self.form(revision=str(p['revision']),animation_enabled='',active='')
        self.assertEqual(self.client.post(f"/admin/posters/{p['id']}",data=data).status_code,302)
        self.assertNotIn(p['image_id'],self.client.get('/').text)
        restarted=Catalog(self.config['DATABASE_URL'])
        self.addCleanup(restarted.engine.dispose)
        persisted=Editorial(restarted).get(p['id'])
        self.assertFalse(persisted['active'])
        self.assertFalse(persisted['animation_enabled'])
        self.assertEqual(persisted['image_id'],p['image_id'])

    def test_preview_never_uploads_and_uses_shared_markup(self):
        self.token=self.login()
        data=self.form(image=(self.photo(),'preview.png'))
        response=self.client.post('/admin/posters/preview',data=data)
        self.assertEqual(response.status_code,200)
        self.assertIn('data:image/jpeg;base64,',response.text)
        self.assertIn('data-animation="float"',response.text)
        self.assertIn("frame-ancestors 'self'",response.headers['Content-Security-Policy'])
        self.storage.upload.assert_not_called()
        self.assertEqual(self.app.extensions['editorial'].posters(),[])

    def test_schedule_timezone_campaign_and_priority(self):
        self.token=self.login()
        editor=self.app.extensions['editorial']
        start=parse_date('2030-01-01T12:00')
        self.assertEqual(datetime.fromtimestamp(start,timezone.utc).hour,15)
        self.assertEqual(local_date(start),'2030-01-01T12:00')
        p=self.create(starts_at='2030-01-01T12:00',ends_at='2030-01-02T12:00')
        self.assertEqual(editor.posters(public=True,now=start-1),[])
        self.assertEqual(len(editor.posters(public=True,now=start)),1)
        self.assertEqual(editor.posters(public=True,now=start+86400),[])
        data=self.form(starts_at='2030-01-02T12:00',ends_at='2030-01-01T12:00')
        self.assertEqual(self.client.post('/admin/posters',data=data).status_code,400)
        cid=editor.save_campaign(None,dict(name='Campaña',active=False,starts_at=None,ends_at=None,priority=100),1)
        data=self.form(revision=str(p['revision']),campaign_id=str(cid))
        self.assertEqual(self.client.post(f"/admin/posters/{p['id']}",data=data).status_code,302)
        self.assertEqual(editor.posters(public=True),[])
        editor.save_campaign(cid,dict(name='Campaña',active=True,starts_at=None,ends_at=None,priority=100),1)
        other=self.create(internal_name='Segundo',position='0')
        self.assertEqual([r['id'] for r in editor.posters(public=True)],[p['id'],other['id']])

    def test_links_validation_security_and_permissions(self):
        self.assertEqual(self.client.get('/admin/posters').status_code,302)
        self.assertEqual(self.client.post('/admin/posters',data={}).status_code,400)
        self.token=self.login()
        for target in ('javascript:alert(1)','http://unsafe.test','//unsafe.test','https://user:secret@example.com'):
            self.assertEqual(self.client.post('/admin/posters',data=self.form(link_type='external_url',link_target=target)).status_code,400)
        p=self.create(link_type='product',link_target='1')
        self.assertEqual(p['href'],'/tartas/oreo')
        data=self.form(revision=str(p['revision']),link_type='external_url',link_target='https://example.com/art',open_in_new_tab='on')
        self.assertEqual(self.client.post(f"/admin/posters/{p['id']}",data=data).status_code,302)
        self.assertIn('rel="noopener noreferrer"',self.client.get('/').text)
        for field,value in [('animation_intensity','101'),('animation_intensity','-1'),('animation_delay_ms','50000'),('animation_type','<script>'),('starts_at','bad'),('location','invalid')]:
            self.assertEqual(self.client.post('/admin/posters',data=self.form(**{field:value})).status_code,400)
        self.assertEqual(self.client.post('/admin/posters',data=self.form(image=(io.BytesIO(b'<svg/>'),'fake.png'))).status_code,400)

    def test_duplicate_archive_shared_image_cleanup_and_atomic_failure(self):
        self.token=self.login()
        editor=self.app.extensions['editorial']
        p=self.create()
        response=self.client.post(f"/admin/posters/{p['id']}/duplicate",data={'csrf':self.token,'revision':p['revision']})
        duplicate=editor.get(int(response.location.rsplit('/',1)[-1]))
        self.assertFalse(duplicate['active'])
        self.assertEqual(duplicate['image_id'],p['image_id'])
        self.assertEqual(self.client.post(f"/admin/posters/{p['id']}/delete",data={'csrf':self.token,'revision':p['revision'],'confirm':'delete'}).status_code,302)
        self.storage.delete.assert_not_called()
        self.client.post(f"/admin/posters/{duplicate['id']}/archive",data={'csrf':self.token,'revision':duplicate['revision']})
        archived=editor.get(duplicate['id'])
        self.assertTrue(archived['archived'])
        self.assertEqual(self.client.post(f"/admin/posters/{archived['id']}",data=self.form(revision=str(archived['revision']))).status_code,400)
        self.client.post(f"/admin/posters/{archived['id']}/delete",data={'csrf':self.token,'revision':archived['revision'],'confirm':'delete'})
        self.storage.delete.assert_called_with(p['image_id'])
        p=self.create()
        before=p['image_id']
        with patch.object(editor,'save',side_effect=ValueError('stale')):
            response=self.client.post(f"/admin/posters/{p['id']}",data=self.form(revision=str(p['revision']),image=(self.photo(),'replace.png')))
        self.assertEqual(response.status_code,400)
        self.assertEqual(editor.get(p['id'])['image_id'],before)
        self.assertNotEqual(self.storage.delete.call_args.args[0],before)

    def test_composition_reorder_protection_and_text_escaping(self):
        self.token=self.login()
        editor=self.app.extensions['editorial']
        rows=editor.blocks()
        original=[r['kind'] for r in rows]
        rows[0],rows[1]=rows[1],rows[0]
        data=MultiDict({'csrf':self.token,'revision':'1'})
        for row in rows:
            for key in ('kind','target','title','body'): data.add(key,row[key])
            data.add('active','1' if row['active'] else '0')
        self.assertEqual(self.client.post('/admin/composition',data=data).status_code,302)
        self.assertEqual(editor.blocks()[0]['kind'],'ribbon')
        self.assertEqual(self.client.post('/admin/composition',data=data).status_code,400)
        invalid=[{k:v for k,v in r.items() if k!='id'} for r in editor.blocks() if r['kind']!='catalog']
        with self.assertRaises(ValueError): editor.save_blocks(invalid,2)
        self.assertEqual(len(editor.blocks()),len(original))
        self.assertEqual(self.client.get('/admin/composition').status_code,200)
        self.assertEqual(self.client.get('/admin/campaigns').status_code,200)
        self.assertEqual(self.client.get('/admin/campaigns/new').status_code,200)
        self.create(alt_text='<script>alert(1)</script>')
        self.assertNotIn('<script>alert(1)</script>',self.client.get('/').text)

    def test_legacy_banner_migration_preserves_content(self):
        url='sqlite:///' + (Path(self.tmp.name)/'legacy-banners.sqlite').as_posix()
        engine=create_engine(url)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE banners (id INTEGER PRIMARY KEY,title TEXT NOT NULL,subtitle TEXT NOT NULL DEFAULT '',cta TEXT NOT NULL DEFAULT '',link TEXT NOT NULL DEFAULT '',location TEXT NOT NULL,position INTEGER NOT NULL DEFAULT 0,active BOOLEAN NOT NULL DEFAULT TRUE,image TEXT,image_id TEXT,revision INTEGER NOT NULL DEFAULT 1)"))
            conn.execute(text("INSERT INTO banners(id,title,location,image,image_id,link) VALUES(1,'Conservar','between','https://res.cloudinary.com/test/image/upload/original.png','original','/#tartas')"))
        engine.dispose()
        migrated=Catalog(url)
        self.addCleanup(migrated.engine.dispose)
        p=Editorial(migrated).get(1)
        self.assertEqual(p['title'],'Conservar')
        self.assertEqual(p['image_id'],'original')
        self.assertEqual(p['content_kind'],'legacy')
        self.assertFalse(p['animation_enabled'])
        self.assertEqual(p['href'],'/#tartas')
