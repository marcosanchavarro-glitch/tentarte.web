"""Small SQLAlchemy Core layer; PostgreSQL in production, in-memory SQLite in tests."""
import json
import time
from pathlib import Path
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, Text,
                        ForeignKey, Boolean, select, insert, update, delete, text)
from migrations import migrate
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

metadata = MetaData()
products = Table('products', metadata,
    Column('id', Integer, primary_key=True), Column('slug', Text, unique=True, nullable=False),
    Column('name', Text, nullable=False), Column('description', Text, nullable=False),
    Column('image', Text), Column('image_id', Text),
    Column('short_description', Text, nullable=False, server_default=''),
    Column('cut_image', Text), Column('cut_image_id', Text),
    Column('published', Boolean, nullable=False, server_default=text('true')),
    Column('featured', Boolean, nullable=False, server_default=text('false')),
    Column('show_in_experience', Boolean, nullable=False, server_default=text('true')),
    Column('visual_experience_enabled', Boolean, nullable=False, server_default=text('true')),
    Column('photo_reference', Text, nullable=False, server_default=''),
    Column('revision', Integer, nullable=False, server_default='1'))
variants = Table('variants', metadata,
    Column('product_id', Integer, ForeignKey('products.id'), primary_key=True),
    Column('size_cm', Integer, primary_key=True), Column('image', Text), Column('image_id', Text),
    Column('name', Text, nullable=False, server_default=''), Column('price_cents', Integer),
    Column('active', Boolean, nullable=False, server_default=text('true')))
components = Table('product_components', metadata,
    Column('id', Integer, primary_key=True), Column('product_id', Integer, ForeignKey('products.id'), nullable=False),
    Column('name', Text, nullable=False), Column('position', Integer, nullable=False))
layers = Table('product_visual_layers', metadata,
    Column('id', Integer, primary_key=True), Column('product_id', Integer, ForeignKey('products.id'), nullable=False),
    Column('name', Text, nullable=False), Column('description', Text, nullable=False, server_default=''),
    Column('position', Integer, nullable=False), Column('image', Text), Column('image_id', Text))
gallery = Table('product_images', metadata,
    Column('id', Integer, primary_key=True), Column('product_id', Integer, ForeignKey('products.id'), nullable=False),
    Column('name', Text, nullable=False, server_default=''), Column('position', Integer, nullable=False),
    Column('image', Text), Column('image_id', Text))
options = Table('product_options', metadata,
    Column('id', Integer, primary_key=True), Column('product_id', Integer, ForeignKey('products.id'), nullable=False),
    Column('name', Text, nullable=False), Column('choices', Text, nullable=False, server_default='[]'),
    Column('position', Integer, nullable=False))
banners = Table('banners', metadata,
    Column('id', Integer, primary_key=True), Column('title', Text, nullable=False),
    Column('subtitle', Text, nullable=False, server_default=''), Column('cta', Text, nullable=False, server_default=''),
    Column('link', Text, nullable=False, server_default=''), Column('location', Text, nullable=False),
    Column('position', Integer, nullable=False, server_default='0'), Column('active', Boolean, nullable=False, server_default=text('true')),
    Column('image', Text), Column('image_id', Text), Column('revision', Integer, nullable=False, server_default='1'))
settings = Table('site_settings', metadata, Column('key', Text, primary_key=True), Column('value', Text, nullable=False))
cleanup = Table('image_cleanup', metadata, Column('public_id', Text, primary_key=True),
                Column('after_time', Integer, nullable=False, default=0))

class Catalog:
    def __init__(self, url):
        if url.startswith(('postgres://', 'postgresql://')):
            url = 'postgresql+psycopg://' + url.split('://', 1)[1]
        self.engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
        self.upsert = pg_insert if self.engine.dialect.name == 'postgresql' else sqlite_insert
        with self.engine.begin() as conn:
            initial = migrate(conn, metadata)
            if not initial:
                self._business_seed(conn)
                return
            for product in json.loads((Path(__file__).parent / 'seeds/products.json').read_text(encoding='utf-8')):
                values = {key: product[key] for key in ('slug', 'name', 'description', 'image')}
                conn.execute(self.upsert(products).values(**values).on_conflict_do_nothing())
                pid = conn.execute(select(products.c.id).where(products.c.slug == product['slug'])).scalar_one()
                for variant in product['variants']:
                    conn.execute(self.upsert(variants).values(product_id=pid, **variant).on_conflict_do_nothing())
            for row in conn.execute(select(products)).mappings().all():
                names = [part.strip().rstrip('.') for part in row['description'].split('+') if part.strip()]
                for position, name in enumerate(names):
                    conn.execute(insert(components).values(product_id=row['id'], name=name, position=position))
                if row['image'] and row['image'].startswith('/images/'):
                    conn.execute(update(products).where(products.c.id == row['id']).values(photo_reference='Presentación de 28 cm'))
            conn.execute(text('INSERT INTO schema_migrations(version) VALUES(1)'))
            self._business_seed(conn)

    def _business_seed(self, conn):
        if conn.execute(text('SELECT version FROM schema_migrations WHERE version=2')).first():
            return
        # Confirmed by the owner on 2026-10-08. Never overwrite later admin prices.
        for slug, prices in {'toffee': {28: 2000000, 12: 500000}, 'banoffee': {28: 2200000, 12: 550000}, 'oreo': {28: 2500000, 12: 620000}}.items():
            pid = conn.execute(select(products.c.id).where(products.c.slug == slug)).scalar()
            if pid:
                for size, cents in prices.items():
                    conn.execute(update(variants).where((variants.c.product_id == pid) & (variants.c.size_cm == size) & variants.c.price_cents.is_(None)).values(price_cents=cents, name='Mini' if size == 12 else 'Grande'))
        conn.execute(self.upsert(settings).values(key='whatsapp', value='5491166452510').on_conflict_do_nothing())
        conn.execute(text('INSERT INTO schema_migrations(version) VALUES(2)'))

    def list(self, public=False):
        with self.engine.connect() as conn:
            result = [dict(row) for row in conn.execute(select(products).where(products.c.published == True) .order_by(products.c.id) if public else select(products).order_by(products.c.id)).mappings()]
            by_id = {p['id']: p for p in result}
            for key, table in (('variants', variants), ('components', components), ('layers', layers), ('gallery', gallery), ('options', options)):
                for product in result:
                    product[key] = []
                if not by_id:
                    continue
                query = select(table).where(table.c.product_id.in_(by_id))
                query = query.order_by(table.c.size_cm.desc()) if key == 'variants' else query.order_by(table.c.position, table.c.id)
                for row in conn.execute(query).mappings():
                    by_id[row['product_id']][key].append(dict(row))
            for product in result:
                if public:
                    product['variants'] = [v for v in product['variants'] if v['active']]
                for option in product['options']:
                    option['choices'] = json.loads(option['choices'])
            return result

    def exists(self, pid):
        with self.engine.connect() as conn:
            return conn.execute(select(products.c.id).where(products.c.id == pid)).first() is not None

    def add(self, slug, name, description):
        with self.engine.begin() as conn:
            pid = conn.execute(insert(products).values(slug=slug, name=name, description=description).returning(products.c.id)).scalar_one()
            conn.execute(insert(variants), [{'product_id': pid, 'size_cm': size} for size in (28, 12)])
            return pid

    def replace_image(self, pid, size, url, public_id):
        self.save_media('variant' if size else 'main', pid, int(size) if size else None, url, public_id)

    def queue_cleanup(self, public_id, delay=0):
        with self.engine.begin() as conn:
            after_time = int(time.time()) + delay
            conn.execute(self.upsert(cleanup).values(public_id=public_id, after_time=after_time)
                         .on_conflict_do_update(index_elements=['public_id'], set_={'after_time': after_time}))

    def clean(self, storage):
        failures = 0
        with self.engine.connect() as conn:
            pending = list(conn.execute(select(cleanup.c.public_id).where(cleanup.c.after_time <= int(time.time()))).scalars())
        for public_id in pending:
            with self.engine.begin() as conn:
                used = any(conn.execute(select(table).where(table.c[column] == public_id)).first() is not None
                           for table, column in ((products, 'image_id'), (products, 'cut_image_id'), (variants, 'image_id'), (layers, 'image_id'), (gallery, 'image_id'), (banners, 'image_id')))
                if used:
                    continue
                try:
                    storage.delete(public_id)
                except Exception:
                    failures += 1
                    continue
                conn.execute(delete(cleanup).where(cleanup.c.public_id == public_id))
        return failures
    def get(self, pid=None, slug=None, public=False):
        return next((p for p in self.list(public) if (p['id'] == pid if pid is not None else p['slug'] == slug)), None)

    def settings(self):
        with self.engine.connect() as conn:
            return dict(conn.execute(select(settings.c.key, settings.c.value)).all())

    def save_settings(self, values):
        with self.engine.begin() as conn:
            for key, value in values.items():
                conn.execute(self.upsert(settings).values(key=key, value=value).on_conflict_do_update(index_elements=['key'], set_={'value': value}))

    def banner_list(self, public=False):
        with self.engine.connect() as conn:
            query = select(banners).order_by(banners.c.position, banners.c.id)
            if public:
                query = query.where(banners.c.active == True)
            return [dict(row) for row in conn.execute(query).mappings()]

    def save_banner(self, bid, values, revision=None):
        with self.engine.begin() as conn:
            if bid:
                result = conn.execute(update(banners).where((banners.c.id == bid) & (banners.c.revision == revision))
                                      .values(**values, revision=banners.c.revision + 1))
                if not result.rowcount:
                    raise ValueError('Este banner cambió. Recargá antes de guardar.')
                return bid
            return conn.execute(insert(banners).values(**values).returning(banners.c.id)).scalar_one()

    def _queue(self, conn, image_id):
        if image_id:
            conn.execute(self.upsert(cleanup).values(public_id=image_id).on_conflict_do_nothing())

    def save_product(self, pid, values, children, revision=None):
        with self.engine.begin() as conn:
            if pid:
                row = conn.execute(select(products).where(products.c.id == pid).with_for_update()).mappings().one()
                if row['revision'] != revision:
                    raise ValueError('El producto cambió en otra ventana. Recargá antes de guardar.')
                conn.execute(update(products).where(products.c.id == pid).values(**values, revision=revision + 1))
            else:
                import uuid
                pid = conn.execute(insert(products).values(**values, slug=uuid.uuid4().hex).returning(products.c.id)).scalar_one()
            old_variants = {v['size_cm']: dict(v) for v in conn.execute(select(variants).where(variants.c.product_id == pid)).mappings()}
            kept_images = set()
            variant_values = []
            for item in children['variants']:
                item = dict(item)
                original = item.pop('original', '')
                previous = old_variants.get(int(original)) if original else None
                item.update(image=None, image_id=None)
                if original and not previous:
                    raise ValueError('Tamaño inválido para este producto.')
                if previous:
                    item.update(image=previous['image'], image_id=previous['image_id'])
                    kept_images.add(previous['image_id'])
                variant_values.append(dict(product_id=pid, **item))
            for old in old_variants.values():
                if old['image_id'] not in kept_images:
                    self._queue(conn, old['image_id'])
            conn.execute(delete(variants).where(variants.c.product_id == pid))
            conn.execute(insert(variants), variant_values)
            for key, table in (('components', components), ('layers', layers), ('gallery', gallery), ('options', options)):
                existing = {row['id']: dict(row) for row in conn.execute(select(table).where(table.c.product_id == pid)).mappings()}
                kept = set()
                for item in children[key]:
                    values = dict(item)
                    iid = values.pop('id')
                    if iid:
                        if iid not in existing or iid in kept:
                            raise ValueError('Elemento inválido para este producto.')
                        conn.execute(update(table).where(table.c.id == iid).values(**values))
                        kept.add(iid)
                    else:
                        conn.execute(insert(table).values(product_id=pid, **values))
                for iid, old in existing.items():
                    if iid not in kept:
                        self._queue(conn, old.get('image_id'))
                        conn.execute(delete(table).where(table.c.id == iid))
            return pid

    def media_target(self, kind, owner, item=None):
        if kind in ('main', 'cut'):
            return products, products.c.id == owner, 'cut_image' if kind == 'cut' else 'image', 'cut_image_id' if kind == 'cut' else 'image_id'
        if kind == 'variant':
            return variants, (variants.c.product_id == owner) & (variants.c.size_cm == item), 'image', 'image_id'
        if kind in ('layer', 'gallery'):
            table = layers if kind == 'layer' else gallery
            return table, (table.c.product_id == owner) & (table.c.id == item), 'image', 'image_id'
        if kind == 'banner':
            return banners, banners.c.id == owner, 'image', 'image_id'
        raise ValueError('Tipo de imagen inválido.')

    def has_media_target(self, kind, owner, item=None):
        table, condition, _, _ = self.media_target(kind, owner, item)
        with self.engine.connect() as conn:
            return conn.execute(select(table).where(condition)).first() is not None

    def save_media(self, kind, owner, item, url, public_id):
        table, condition, column, id_column = self.media_target(kind, owner, item)
        with self.engine.begin() as conn:
            # Same parent lock as metadata editing: no lost update or removed-child race.
            parent = banners if kind == 'banner' else products
            conn.execute(select(parent.c.id).where(parent.c.id == owner).with_for_update()).one()
            old = conn.execute(select(table.c[id_column]).where(condition).with_for_update()).scalar_one()
            conn.execute(update(table).where(condition).values(**{column: url, id_column: public_id}))
            conn.execute(update(parent).where(parent.c.id == owner).values(revision=parent.c.revision + 1))
            if public_id:
                conn.execute(delete(cleanup).where(cleanup.c.public_id == public_id))
            self._queue(conn, old)
