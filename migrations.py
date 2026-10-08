"""Additive, transactional schema upgrades. Never drops production data."""
from sqlalchemy import inspect, text
from editorial_schema import POSTER_COLUMNS, DEFAULT_BLOCKS

PRODUCT_COLUMNS = {
    'short_description': "TEXT NOT NULL DEFAULT ''",
    'cut_image': 'TEXT', 'cut_image_id': 'TEXT',
    'published': 'BOOLEAN NOT NULL DEFAULT TRUE',
    'featured': 'BOOLEAN NOT NULL DEFAULT FALSE',
    'show_in_experience': 'BOOLEAN NOT NULL DEFAULT TRUE',
    'visual_experience_enabled': 'BOOLEAN NOT NULL DEFAULT TRUE',
    'photo_reference': "TEXT NOT NULL DEFAULT ''",
    'revision': 'INTEGER NOT NULL DEFAULT 1',
}
VARIANT_COLUMNS = {
    'name': "TEXT NOT NULL DEFAULT ''",
    'price_cents': 'INTEGER', 'active': 'BOOLEAN NOT NULL DEFAULT TRUE',
}

def migrate(conn, metadata):
    if conn.dialect.name == 'postgresql':
        conn.execute(text('SELECT pg_advisory_xact_lock(781242009)'))
    metadata.create_all(conn)
    for name, columns in (('products', PRODUCT_COLUMNS), ('variants', VARIANT_COLUMNS), ('banners', POSTER_COLUMNS)):
        existing = {c['name'] for c in inspect(conn).get_columns(name)}
        for column, ddl in columns.items():
            if column not in existing:
                conn.execute(text(f'ALTER TABLE {name} ADD COLUMN {column} {ddl}'))
    conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)'))
    if not conn.execute(text('SELECT version FROM schema_migrations WHERE version=3')).first():
        conn.execute(text("UPDATE banners SET internal_name=title, alt_text=title, animation_type='none', animation_enabled=FALSE, link_type=CASE WHEN link='' THEN 'none' ELSE 'legacy' END, link_target=link"))
        for position, (kind, target, title) in enumerate(DEFAULT_BLOCKS):
            conn.execute(text("INSERT INTO home_blocks(kind,target,title,body,position,active) VALUES(:kind,:target,:title,'',:position,TRUE)"),
                         dict(kind=kind, target=target, title=title, position=position))
        conn.execute(text('INSERT INTO schema_migrations(version) VALUES(3)'))
    return conn.execute(text('SELECT version FROM schema_migrations WHERE version=1')).first() is None
