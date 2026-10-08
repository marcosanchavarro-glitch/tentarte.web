"""Owner-approved illustrative package; original files retained in resources/oreo-source."""
ROOT = '/images/products/oreo/experience/'
WHOLE = ROOT + 'web/oreo_tarta_transparente.webp'
CUT = ROOT + 'web/oreo_corte_transparente.webp'
CUT_FALLBACK = ROOT + 'web/oreo_corte.webp'
HERO = ROOT + 'web/oreo_hero.webp'
SUPERIOR = ROOT + 'web/oreo_superior.webp'
# Base to top, preserving the original proportions of each independent file.
LAYERS = (
    ('Base sablée de chocolate', '04_base_sablee_chocolate.webp', 'base'),
    ('Relleno de chocolate', '03_relleno_chocolate.webp', 'chocolate'),
    ('Crema Oreo', '02_crema_oreo.webp', 'cream'),
    ('Decoración superior', '01_decoracion_oreo.webp', 'decoration'),
)


def seed_oreo(conn, products, layers, gallery):
    from sqlalchemy import select, update, insert, text
    if conn.execute(text('SELECT version FROM schema_migrations WHERE version=4')).first():
        return
    oreo = conn.execute(select(products).where(products.c.slug == 'oreo')).mappings().first()
    if oreo:
        pid = oreo['id']
        values = {}
        if oreo['image'] == '/images/products/oreo/oreo.jpg':
            values.update(image=WHOLE, photo_reference='Imagen ilustrativa · presentación de 28 cm')
        if not oreo['cut_image']: values['cut_image'] = CUT
        if values:
            conn.execute(update(products).where(products.c.id == pid).values(**values, revision=products.c.revision + 1))
        if not conn.execute(select(layers.c.id).where(layers.c.product_id == pid)).first():
            for position, (name, filename, slot) in enumerate(LAYERS):
                conn.execute(insert(layers).values(product_id=pid, name=name, description='Recurso ilustrativo aprobado · ' + slot,
                    position=position, image=ROOT + 'capas/' + filename))
        for name, path in [('Fotografía de referencia · 28 cm', '/images/products/oreo/oreo.jpg'),
                           ('Vista superior · ilustrativa', SUPERIOR), ('Vista ambientada · ilustrativa', HERO)]:
            if not conn.execute(select(gallery.c.id).where((gallery.c.product_id == pid) & (gallery.c.image == path))).first():
                last = conn.execute(select(gallery.c.position).where(gallery.c.product_id == pid).order_by(gallery.c.position.desc())).scalar()
                conn.execute(insert(gallery).values(product_id=pid, name=name, image=path, position=(last + 1 if last is not None else 0)))
    conn.execute(text('INSERT INTO schema_migrations(version) VALUES(4)'))
