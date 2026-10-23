import json
from pathlib import Path

PRODUCTS = json.loads((Path(__file__).with_name('products.json')).read_text())
BY_SLUG = {p['slug']: p for p in PRODUCTS}
BY_ID = {str(p['id']): p for p in PRODUCTS}


def money(cents):
    return f'${cents / 100:,.2f}'


for p in PRODUCTS:
    p['price_display'] = money(p['price'])


def cart_summary(cart):
    lines = []
    for product_id, quantity in cart.items():
        p = BY_ID.get(str(product_id))
        if p and type(quantity) is int and 1 <= quantity <= min(9, p['stock']):
            lines.append({'product': p, 'quantity': quantity, 'total': p['price'] * quantity,
                          'total_display': money(p['price'] * quantity)})
    subtotal = sum(x['total'] for x in lines)
    shipping = 0 if subtotal == 0 or subtotal >= 7500 else 600
    return {'lines': lines, 'count': sum(x['quantity'] for x in lines), 'subtotal': subtotal,
            'shipping': shipping, 'total': subtotal + shipping, 'subtotal_display': money(subtotal),
            'shipping_display': 'Free' if not shipping else money(shipping),
            'total_display': money(subtotal + shipping), 'free_shipping_remaining': money(max(0, 7500 - subtotal))}
