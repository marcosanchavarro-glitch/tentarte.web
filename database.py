"""Small SQLAlchemy Core layer; PostgreSQL in production, in-memory SQLite in tests."""
import json
import time
from pathlib import Path
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, Text,
                        ForeignKey, select, insert, update, delete)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

metadata = MetaData()
products = Table('products', metadata,
    Column('id', Integer, primary_key=True), Column('slug', Text, unique=True, nullable=False),
    Column('name', Text, nullable=False), Column('description', Text, nullable=False),
    Column('image', Text), Column('image_id', Text))
variants = Table('variants', metadata,
    Column('product_id', Integer, ForeignKey('products.id'), primary_key=True),
    Column('size_cm', Integer, primary_key=True), Column('image', Text), Column('image_id', Text))
cleanup = Table('image_cleanup', metadata, Column('public_id', Text, primary_key=True),
                Column('after_time', Integer, nullable=False, default=0))

class Catalog:
    def __init__(self, url):
        if url.startswith(('postgres://', 'postgresql://')):
            url = 'postgresql+psycopg://' + url.split('://', 1)[1]
        self.engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
        metadata.create_all(self.engine)
        self.upsert = pg_insert if self.engine.dialect.name == 'postgresql' else sqlite_insert
        with self.engine.begin() as conn:
            for product in json.loads((Path(__file__).parent / 'seeds/products.json').read_text(encoding='utf-8')):
                values = {key: product[key] for key in ('slug', 'name', 'description', 'image')}
                conn.execute(self.upsert(products).values(**values).on_conflict_do_nothing())
                pid = conn.execute(select(products.c.id).where(products.c.slug == product['slug'])).scalar_one()
                for variant in product['variants']:
                    conn.execute(self.upsert(variants).values(product_id=pid, **variant).on_conflict_do_nothing())

    def list(self):
        with self.engine.connect() as conn:
            result = [dict(row) for row in conn.execute(select(products).order_by(products.c.id)).mappings()]
            for product in result:
                product['variants'] = [dict(row) for row in conn.execute(select(variants).where(
                    variants.c.product_id == product['id']).order_by(variants.c.size_cm.desc())).mappings()]
            return result

    def exists(self, pid):
        with self.engine.connect() as conn:
            return conn.execute(select(products.c.id).where(products.c.id == pid)).first() is not None

    def add(self, slug, name, description):
        with self.engine.begin() as conn:
            pid = conn.execute(insert(products).values(slug=slug, name=name, description=description).returning(products.c.id)).scalar_one()
            conn.execute(insert(variants), [{'product_id': pid, 'size_cm': size} for size in (28, 12)])

    def replace_image(self, pid, size, url, public_id):
        table = variants if size else products
        condition = ((variants.c.product_id == pid) & (variants.c.size_cm == int(size))) if size else products.c.id == pid
        with self.engine.begin() as conn:
            # Serialize concurrent replacements so each superseded asset is queued.
            old = conn.execute(select(table.c.image_id).where(condition).with_for_update()).scalar_one()
            conn.execute(update(table).where(condition).values(image=url, image_id=public_id))
            if public_id:
                conn.execute(delete(cleanup).where(cleanup.c.public_id == public_id))
            if old:
                conn.execute(self.upsert(cleanup).values(public_id=old).on_conflict_do_nothing())

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
                used = (conn.execute(select(products.c.id).where(products.c.image_id == public_id)).first()
                        or conn.execute(select(variants.c.product_id).where(variants.c.image_id == public_id)).first())
                if used:
                    continue
                try:
                    storage.delete(public_id)
                except Exception:
                    failures += 1
                    continue
                conn.execute(delete(cleanup).where(cleanup.c.public_id == public_id))
        return failures
