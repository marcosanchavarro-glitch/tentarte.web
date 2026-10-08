"""Editorial validation and persistence, reusing the banners/media lifecycle."""
import time
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from sqlalchemy import select, insert, update, delete
from database import banners, campaigns, home_blocks, settings, products
from forms import string, integer, safe_link
from presentation import image_available

BUSINESS_TZ = ZoneInfo(os.environ.get('BUSINESS_TIMEZONE', 'America/Argentina/Buenos_Aires'))
ANIMATIONS = {'float':'Flotar', 'scroll-reveal':'Revelar al recorrer', 'parallax':'Parallax suave', 'tilt':'Inclinación editorial', 'fade':'Aparecer', 'none':'Sin movimiento'}
PLACEMENTS = {'hero':'Después del hero', 'between':'Entre secciones', 'catalog':'En el catálogo', 'featured':'Home destacado', 'overlay':'Sobre la fotografía editorial', 'manual':'Bloque de la composición'}
BLOCK_KINDS = {'hero':'Hero', 'experience':'Experiencia de tartas', 'catalog':'Catálogo completo', 'featured_catalog':'Selección destacada', 'poster':'Cartel individual', 'poster_group':'Grupo de carteles', 'text':'Texto editorial', 'how':'Cómo encargar', 'ribbon':'Franja de marca', 'share':'Llega, se comparte…', 'reminder':'Recordatorio', 'cta':'Invitación final'}
REQUIRED_BLOCKS = {'hero','catalog','how'}


def choice(value, allowed, label):
    if value not in allowed:
        raise ValueError('Revisá ' + label + '.')
    return value


def parse_date(value):
    if not value:
        return None
    try:
        date = datetime.fromisoformat(value)
        if date.tzinfo is not None or not 2000 <= date.year <= 2100:
            raise ValueError
        return int(date.replace(tzinfo=BUSINESS_TZ).timestamp())
    except (ValueError, OverflowError):
        raise ValueError('Ingresá una fecha válida en horario de Buenos Aires.') from None


def local_date(value):
    return datetime.fromtimestamp(value, BUSINESS_TZ).strftime('%Y-%m-%dT%H:%M') if value else ''


def schedule(form):
    start, end = parse_date(form.get('starts_at')), parse_date(form.get('ends_at'))
    if start is not None and end is not None and end <= start:
        raise ValueError('El vencimiento debe ser posterior al inicio.')
    return {'starts_at':start, 'ends_at':end}


def live(row, now):
    return row['active'] and not row.get('archived', False) and (row['starts_at'] is None or row['starts_at'] <= now) and (row['ends_at'] is None or now < row['ends_at'])


def poster_status(row, campaign=None, now=None):
    now = int(time.time()) if now is None else now
    if row['archived']: return 'Archivado'
    if not row['active']: return 'Borrador'
    if row['ends_at'] is not None and now >= row['ends_at']: return 'Vencido'
    if row['starts_at'] is not None and now < row['starts_at']: return 'Programado'
    if campaign and not live(campaign, now): return 'En espera de campaña'
    return 'Publicado'


def resolve_link(kind, target, product_rows):
    if kind == 'none': return ''
    if kind == 'catalog': return '/#tartas'
    if kind == 'section':
        return '/#' + choice(target, ('tartas','experiencia','como-encargar'), 'la sección de destino')
    if kind == 'product':
        match = next((p for p in product_rows if str(p['id']) == target), None)
        if not match: raise ValueError('El producto de destino no existe.')
        return '/tartas/' + match['slug'] if match['published'] else ''
    if kind == 'internal_url':
        allowed = {'/', '/#tartas', '/#experiencia', '/#como-encargar'} | {'/tartas/' + p['slug'] for p in product_rows if p['published']}
        return choice(target, allowed, 'la ruta interna; usá una sección o un producto publicado')
    if kind == 'external_url':
        url = safe_link(target)
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('El enlace externo debe ser HTTPS, sin credenciales.')
        return url
    if kind == 'legacy': return safe_link(target)
    raise ValueError('Tipo de enlace inválido.')


def poster_form(form, product_rows, existing=None):
    kind = 'legacy' if existing and existing['content_kind'] == 'legacy' else 'poster'
    name = string(form.get('internal_name'),150,True)
    link_type = choice(form.get('link_type','none'), ('none','product','catalog','section','internal_url','external_url') + (('legacy',) if kind=='legacy' else ()), 'el tipo de enlace')
    target = string(form.get('link_target'),500)
    if link_type in ('none','catalog'): target = ''
    link = resolve_link(link_type,target,product_rows)
    values = dict(internal_name=name, title=string(form.get('title') or name,150,True),
        subtitle=string(form.get('subtitle'),300), cta=string(form.get('cta'),60),
        alt_text=string(form.get('alt_text'),300,kind=='poster'), content_kind=kind,
        animation_type=choice(form.get('animation_type','float'),ANIMATIONS,'la animación'),
        animation_intensity=integer(form.get('animation_intensity','35'),0,100),
        animation_enabled=form.get('animation_enabled')=='on', animation_delay_ms=integer(form.get('animation_delay_ms',0),0,3000),
        location=choice(form.get('location'),PLACEMENTS,'la ubicación'), position=integer(form.get('position',0)),
        alignment=choice(form.get('alignment','center'),('left','center','right'),'la alineación'),
        visual_size=choice(form.get('visual_size','medium'),('small','medium','large','full'),'el tamaño visual'),
        image_fit=choice(form.get('image_fit','contain'),('contain','cover'),'el ajuste de imagen'),
        link_type=link_type,link_target=target,link=link,
        open_in_new_tab=form.get('open_in_new_tab')=='on' and link_type=='external_url',
        active=form.get('active')=='on', campaign_id=integer(form.get('campaign_id'),1,2147483647) if form.get('campaign_id') else None)
    values.update(schedule(form))
    return values


class Editorial:
    def __init__(self,catalog):
        self.catalog=catalog
        self.engine=catalog.engine

    def posters(self, public=False, now=None):
        now=int(time.time()) if now is None else now
        with self.engine.connect() as conn:
            rows=[dict(r) for r in conn.execute(select(banners)).mappings()]
            campaign_map={r['id']:dict(r) for r in conn.execute(select(campaigns)).mappings()}
            product_rows=[dict(r) for r in conn.execute(select(products.c.id,products.c.slug,products.c.published)).mappings()]
        result=[]
        for row in rows:
            campaign=campaign_map.get(row['campaign_id'])
            row['status']=poster_status(row,campaign,now)
            row['priority']=campaign['priority'] if campaign else 0
            try: row['href']=resolve_link(row['link_type'],row['link_target'],product_rows)
            except ValueError: row['href']=''
            if public and (not live(row,now) or (campaign and not live(campaign,now)) or (row['content_kind']=='poster' and not image_available(row['image']))):
                continue
            result.append(row)
        return sorted(result,key=lambda r:(-r['priority'],r['position'],r['id']))

    def get(self,pid):
        return next((r for r in self.posters() if r['id']==pid),None)

    def save(self,pid,values,revision):
        values=dict(values)
        now=int(time.time())
        with self.engine.begin() as conn:
            old=conn.execute(select(banners).where(banners.c.id==pid).with_for_update()).mappings().first() if pid else None
            if pid and (not old or old['revision']!=revision):
                raise ValueError('El cartel cambió. Recargá la página antes de guardar.')
            candidate=dict(old or {}) | values
            if old and old['archived'] and values['active']:
                raise ValueError('Restaurá el cartel archivado antes de publicarlo.')
            if values['active'] and candidate['content_kind']=='poster' and not image_available(candidate.get('image')):
                raise ValueError('Para publicar, cargá una imagen válida.')
            if values.get('campaign_id') and not conn.execute(select(campaigns.c.id).where(campaigns.c.id==values['campaign_id'])).first():
                raise ValueError('La campaña seleccionada no existe.')
            values['updated_at']=now
            if pid:
                conn.execute(update(banners).where(banners.c.id==pid).values(**values,revision=revision+1))
            else:
                pid=conn.execute(insert(banners).values(**values,created_at=now).returning(banners.c.id)).scalar_one()
            if values.get('image_id'):
                conn.execute(delete(self._cleanup).where(self._cleanup.c.public_id==values['image_id']))
                if old and old['image_id']!=values['image_id']: self.catalog._queue(conn,old['image_id'])
        return pid

    @property
    def _cleanup(self):
        from database import cleanup
        return cleanup

    def action(self,pid,action,revision):
        with self.engine.begin() as conn:
            row=conn.execute(select(banners).where(banners.c.id==pid).with_for_update()).mappings().first()
            if not row or row['revision']!=revision: raise ValueError('El cartel cambió. Recargá antes de continuar.')
            if action=='duplicate':
                values={k:v for k,v in row.items() if k not in ('id','revision')}
                values.update(internal_name=(row['internal_name'] or row['title'])[:135]+' (copia)',active=False,archived=False,created_at=int(time.time()),updated_at=int(time.time()))
                return conn.execute(insert(banners).values(**values).returning(banners.c.id)).scalar_one()
            if action in ('archive','restore'):
                conn.execute(update(banners).where(banners.c.id==pid).values(archived=action=='archive',active=False,revision=revision+1,updated_at=int(time.time())))
            elif action=='delete':
                conn.execute(delete(banners).where(banners.c.id==pid))
                self.catalog._queue(conn,row['image_id'])
                conn.execute(update(home_blocks).where((home_blocks.c.kind=='poster')&(home_blocks.c.target==str(pid))).values(active=False))
            else: raise ValueError('Acción inválida.')
        return pid

    def campaign_list(self):
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(select(campaigns).order_by(campaigns.c.priority.desc(),campaigns.c.id)).mappings()]

    def save_campaign(self,cid,values,revision):
        with self.engine.begin() as conn:
            if cid:
                result=conn.execute(update(campaigns).where((campaigns.c.id==cid)&(campaigns.c.revision==revision)).values(**values,revision=revision+1))
                if not result.rowcount: raise ValueError('La campaña cambió. Recargá antes de guardar.')
                return cid
            return conn.execute(insert(campaigns).values(**values).returning(campaigns.c.id)).scalar_one()

    def blocks(self):
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(select(home_blocks).order_by(home_blocks.c.position,home_blocks.c.id)).mappings()]

    def save_blocks(self,rows,revision):
        if not 3<=len(rows)<=40: raise ValueError('La home admite de 3 a 40 bloques.')
        for required in REQUIRED_BLOCKS:
            matches=[r for r in rows if r['kind']==required]
            if len(matches)!=1 or not matches[0]['active']: raise ValueError('Hero, catálogo y cómo encargar deben permanecer activos una sola vez.')
        singleton=[r['kind'] for r in rows if r['kind'] not in ('poster','poster_group','text','featured_catalog')]
        if len(set(singleton))!=len(singleton): raise ValueError('No repitas las secciones principales.')
        groups=[r['target'] for r in rows if r['kind']=='poster_group']
        if len(set(groups))!=len(groups): raise ValueError('No repitas un mismo grupo de carteles.')
        with self.engine.begin() as conn:
            conn.execute(self.catalog.upsert(settings).values(key='home_revision',value='1').on_conflict_do_nothing())
            current=conn.execute(select(settings.c.value).where(settings.c.key=='home_revision').with_for_update()).scalar_one()
            if str(revision)!=current: raise ValueError('La composición cambió. Recargá antes de guardar.')
            ids=set(conn.execute(select(banners.c.id)).scalars())
            for row in rows:
                if row['kind']=='poster' and integer(row['target'],1,2147483647) not in ids: raise ValueError('El cartel seleccionado ya no existe.')
            conn.execute(delete(home_blocks))
            conn.execute(insert(home_blocks),rows)
            conn.execute(update(settings).where(settings.c.key=='home_revision').values(value=str(int(current)+1)))

    def home(self):
        posters=self.posters(public=True)
        all_blocks=self.blocks()
        blocks=[r for r in all_blocks if r['active']]
        singles={r['target'] for r in blocks if r['kind']=='poster'}
        groups={r['target'] for r in all_blocks if r['kind']=='poster_group'}
        assigned=set()
        for block in blocks:
            if block['kind']=='poster': candidates=[p for p in posters if str(p['id'])==block['target']]
            elif block['kind']=='poster_group': candidates=[p for p in posters if p['location']==block['target'] and str(p['id']) not in singles]
            else: candidates=[]
            block['posters']=[p for p in candidates if p['id'] not in assigned]
            assigned.update(p['id'] for p in block['posters'])
        auto=[p for p in posters if p['location'] not in groups and str(p['id']) not in singles]
        return blocks, auto
