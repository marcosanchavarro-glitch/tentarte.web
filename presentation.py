"""Public view models, responsive media and WhatsApp links. No secrets leave here."""
from pathlib import Path
from urllib.parse import quote
from image_storage import is_remote_image

ROOT = Path(__file__).resolve().parent

def image_available(path):
    if not path:
        return None
    if is_remote_image(path):
        return path
    if path.startswith('/images/'):
        target = (ROOT / 'public' / path.lstrip('/')).resolve()
        return path if target.is_relative_to(ROOT / 'public') and target.is_file() else None
    return None

def image_url(path, width=900):
    if not image_available(path):
        return None
    if is_remote_image(path) and '/image/upload/' in path:
        return path.replace('/image/upload/', f'/image/upload/f_auto,q_auto,c_limit,w_{width}/', 1)
    return path

def money(cents):
    if cents is None:
        return 'Consultar precio'
    whole, fraction = divmod(cents, 100)
    return '$' + f'{whole:,}'.replace(',', '.') + (f',{fraction:02}' if fraction else '')

def product_view(product):
    result = dict(product)
    result['main_image'] = image_available(product['image'])
    result['cut_image'] = image_available(product['cut_image'])
    result['layers'] = [dict(layer, image=image_available(layer['image'])) for layer in product['layers']]
    active_prices = [v['price_cents'] for v in product['variants'] if v['active'] and v['price_cents'] is not None]
    result['from_price'] = min(active_prices) if active_prices else None
    result['composition'] = ' · '.join(c['name'] for c in product['components'])
    result['experience_level'] = 1
    result['oreo_experience'] = product['slug'] == 'oreo' and bool(product['visual_experience_enabled'])
    from oreo_assets import ROOT as OREO_ROOT, LAYERS, WHOLE, CUT, CUT_FALLBACK, HERO
    result['oreo_illustrative'] = product['slug'] == 'oreo' and (product['image'] == WHOLE or product['cut_image'] == CUT)
    result['hero_image'] = HERO if product['image'] == WHOLE and image_available(HERO) else product['image']
    result['oreo_cut_fallback'] = image_available(CUT_FALLBACK) if product['cut_image'] == CUT else None
    approved = {OREO_ROOT + 'capas/' + filename: slot for _, filename, slot in LAYERS}
    result['oreo_layers'] = [dict(layer, slot=approved[layer['image']]) for layer in result['layers'] if layer['image'] in approved]
    # Only this inspected RGBA package is approved; replacements must be checked separately.
    if not result['oreo_experience'] or len(result['oreo_layers']) != 4 or len({l['slot'] for l in result['oreo_layers']}) != 4:
        result['oreo_layers'] = []
    if result['main_image'] and result['cut_image']:
        result['experience_level'] = 2
        if product['visual_experience_enabled'] and result['layers'] and all(l['image'] for l in result['layers']):
            result['experience_level'] = 3
    return result

def whatsapp_link(phone, product=None, variant=None, choices=None):
    if not phone:
        return None
    message = '¡Hola Tentarte! Quiero consultar por un encargo.'
    if product and variant:
        message = f"¡Hola Tentarte! Quiero encargar una {product['name']}.\n\nTamaño: {variant['size_cm']} cm\nPrecio: {money(variant['price_cents'])}"
        if choices:
            message += '\nOpciones: ' + '; '.join(choices)
        message += '\n\n¿Podemos coordinar el pedido?'
    return 'https://wa.me/' + phone + '?text=' + quote(message, safe='')
