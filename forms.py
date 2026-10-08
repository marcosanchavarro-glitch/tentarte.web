"""Validation shared by admin forms and tests. Prices use integer centavos."""
from decimal import Decimal, InvalidOperation
import json
import re
from urllib.parse import urlsplit

def string(value, limit, required=False):
    value = (value or '').strip()
    if len(value) > limit or (required and not value):
        raise ValueError('Completá los campos obligatorios y respetá su longitud máxima.')
    return value

def integer(value, low=0, high=10000):
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValueError('Revisá los valores numéricos.') from None
    if not low <= result <= high:
        raise ValueError('Hay un número fuera del rango permitido.')
    return result

def price(value):
    if not (value or '').strip():
        return None
    try:
        amount = Decimal(value.replace(',', '.'))
        if not amount.is_finite() or amount < 0 or amount > 20000000 or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError
        return int(amount * 100)
    except (ValueError, InvalidOperation):
        raise ValueError('Ingresá un precio válido, sin separador de miles y con hasta dos decimales.') from None

def safe_link(value):
    value = string(value, 500)
    if not value:
        return ''
    parsed = urlsplit(value)
    if '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError('El enlace no es válido.')
    if (value.startswith('/') and not value.startswith('//')) or value.startswith('#'):
        return value
    if parsed.scheme == 'https' and parsed.netloc and not parsed.username:
        return value
    raise ValueError('Usá un enlace HTTPS o una ruta del sitio.')

def rows(form, prefix, fields):
    count = len(form.getlist(prefix + '_name'))
    if count > 40:
        raise ValueError('El máximo es de 40 elementos por sección.')
    result = []
    for i in range(count):
        row = {}
        for field in fields:
            values = form.getlist(prefix + '_' + field)
            row[field] = values[i] if i < len(values) else ''
        result.append(row)
    return result

def product_form(form):
    product = {k: string(form.get(k), limit, k == 'name') for k, limit in
               (('name', 150), ('description', 2000), ('short_description', 240), ('photo_reference', 150))}
    for key in ('published', 'featured', 'show_in_experience', 'visual_experience_enabled'):
        product[key] = form.get(key) == 'on'
    children = {}
    children['variants'] = []
    for row in rows(form, 'variant', ('name', 'size', 'price', 'active', 'original')):
        children['variants'].append(dict(name=string(row['name'], 80), size_cm=integer(row['size'], 1, 150),
            price_cents=price(row['price']), active=row['active'] == '1', original=row['original']))
    if not children['variants'] or len({v['size_cm'] for v in children['variants']}) != len(children['variants']):
        raise ValueError('Agregá al menos un tamaño; los diámetros no se pueden repetir.')
    for key, prefix in (('components', 'component'), ('layers', 'layer'), ('gallery', 'gallery'), ('options', 'option')):
        children[key] = []
        for position, row in enumerate(rows(form, prefix, ('id', 'name', 'description', 'choices'))):
            item = {'id': integer(row['id'], 1, 2147483647) if row['id'] else None,
                    'name': string(row['name'], 150, key != 'gallery'), 'position': position}
            if key == 'layers':
                item['description'] = string(row['description'], 240)
            if key == 'options':
                choices = [string(c, 100, True) for c in row['choices'].split('|') if c.strip()]
                if len(choices) > 30:
                    raise ValueError('Demasiadas opciones.')
                item['choices'] = json.dumps(choices, ensure_ascii=False)
            children[key].append(item)
    return product, children

def phone_number(value):
    phone = re.sub(r'[\s+()-]', '', value or '')
    if phone and not re.fullmatch(r'[1-9][0-9]{7,14}', phone):
        raise ValueError('Ingresá el WhatsApp con código de país, solo números.')
    return phone
