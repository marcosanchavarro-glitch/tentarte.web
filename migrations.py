"""Additive, transactional schema upgrades. Never drops production data."""
from sqlalchemy import inspect, text

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
    for name, columns in (('products', PRODUCT_COLUMNS), ('variants', VARIANT_COLUMNS)):
        existing = {c['name'] for c in inspect(conn).get_columns(name)}
        for column, ddl in columns.items():
            if column not in existing:
                conn.execute(text(f'ALTER TABLE {name} ADD COLUMN {column} {ddl}'))
    conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)'))
    return conn.execute(text('SELECT version FROM schema_migrations WHERE version=1')).first() is None
