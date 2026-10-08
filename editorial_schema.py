"""Additive editorial fields on the existing banners table."""
from sqlalchemy import Table, Column, Integer, BigInteger, Text, Boolean, ForeignKey, text

POSTER_COLUMNS = {
    'internal_name': "TEXT NOT NULL DEFAULT ''", 'alt_text': "TEXT NOT NULL DEFAULT ''",
    'content_kind': "TEXT NOT NULL DEFAULT 'legacy'",
    'animation_type': "TEXT NOT NULL DEFAULT 'float'", 'animation_intensity': 'INTEGER NOT NULL DEFAULT 35',
    'animation_enabled': 'BOOLEAN NOT NULL DEFAULT TRUE', 'animation_delay_ms': 'INTEGER NOT NULL DEFAULT 0',
    'alignment': "TEXT NOT NULL DEFAULT 'center'", 'visual_size': "TEXT NOT NULL DEFAULT 'medium'",
    'image_fit': "TEXT NOT NULL DEFAULT 'contain'", 'image_width': 'INTEGER', 'image_height': 'INTEGER',
    'link_type': "TEXT NOT NULL DEFAULT 'none'", 'link_target': "TEXT NOT NULL DEFAULT ''",
    'open_in_new_tab': 'BOOLEAN NOT NULL DEFAULT FALSE', 'starts_at': 'BIGINT', 'ends_at': 'BIGINT',
    'archived': 'BOOLEAN NOT NULL DEFAULT FALSE', 'created_at': 'BIGINT NOT NULL DEFAULT 0',
    'updated_at': 'BIGINT NOT NULL DEFAULT 0', 'campaign_id': 'INTEGER REFERENCES editorial_campaigns(id)',
}
DEFAULT_BLOCKS = [
    ('hero', '', 'Hero'), ('ribbon', '', 'Franja de marca'), ('poster_group', 'hero', 'Carteles después del hero'),
    ('experience', '', 'Experiencia de tartas'), ('poster_group', 'between', 'Carteles entre secciones'),
    ('share', '', 'Llega, se comparte y desaparece'), ('catalog', '', 'Catálogo'),
    ('poster_group', 'featured', 'Carteles destacados'), ('reminder', '', 'Recordatorio del día'),
    ('how', '', 'Cómo encargar'), ('cta', '', 'Invitación final'),
]
def extend_schema(metadata, banners):
    campaigns = Table('editorial_campaigns', metadata,
        Column('id', Integer, primary_key=True), Column('name', Text, nullable=False),
        Column('active', Boolean, nullable=False, server_default=text('true')),
        Column('starts_at', BigInteger), Column('ends_at', BigInteger),
        Column('priority', Integer, nullable=False, server_default='0'),
        Column('revision', Integer, nullable=False, server_default='1'))
    for name, ddl in POSTER_COLUMNS.items():
        dtype = Boolean if ddl.startswith('BOOLEAN') else BigInteger if ddl.startswith('BIGINT') else Integer if ddl.startswith('INTEGER') else Text
        default = ddl.split(' DEFAULT ', 1)[1] if ' DEFAULT ' in ddl else None
        args = [ForeignKey('editorial_campaigns.id')] if name == 'campaign_id' else []
        banners.append_column(Column(name, dtype, *args, nullable='NOT NULL' not in ddl,
                                     server_default=text(default) if default else None))
    blocks = Table('home_blocks', metadata,
        Column('id', Integer, primary_key=True), Column('kind', Text, nullable=False),
        Column('target', Text, nullable=False, server_default=''), Column('title', Text, nullable=False, server_default=''),
        Column('body', Text, nullable=False, server_default=''), Column('position', Integer, nullable=False),
        Column('active', Boolean, nullable=False, server_default=text('true')))
    return campaigns, blocks
