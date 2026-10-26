import json
from pathlib import Path
from django.templatetags.static import static
SAMPLE_IMAGES = {item["slug"]: item["image"]
                 for filename in ("legacy_samples.json", "products.json")
                 for item in json.loads(Path(__file__).with_name(filename).read_text())}
from .models import Product, Variant


def money(cents):
    return f'${cents / 100:,.2f}'


def variant_data(variant):
    p = variant.product
    image = next(iter(p.images.all()), None)
    return {'id': variant.pk, 'slug': p.slug, 'name': p.name, 'category': p.category,
            'price': variant.price, 'price_display': money(variant.price), 'stock': variant.stock,
            'color': f'{variant.size} / {variant.style}', 'size': variant.size, 'style': variant.style,
            'image_url': image.image.url if image else static('shop/images/' + SAMPLE_IMAGES.get(p.slug, 'bonnet.svg')),
            'image': SAMPLE_IMAGES.get(p.slug, 'bonnet.svg'),
            'image_alt': image.alt_text if image else p.name,
            **{key: getattr(p, key) for key in ['description', 'materials', 'dimensions', 'care', 'note', 'badge']}}


def product_data(product):
    variants = [variant_data(v) for v in product.variants.all() if v.active]
    if not variants:
        return None
    data = dict(min(variants, key=lambda v: v['price']))
    data['variants'] = variants
    data['images'] = [{'url': image.image.url, 'alt': image.alt_text} for image in product.images.all()]
    data['multiple_variants'] = len(variants) > 1
    return data


def product_cards():
    products = Product.objects.filter(published=True, deleted_at__isnull=True).prefetch_related('images', 'variants__product__images').order_by('id')
    return [data for p in products if (data := product_data(p)) is not None]


class Catalog:
    def __iter__(self):
        return iter(product_cards())
    def __getitem__(self, key):
        return product_cards()[key]


class VariantLookup:
    def get(self, key, default=None):
        try:
            variant = Variant.objects.select_related('product').prefetch_related('product__images').get(pk=int(key), active=True, product__published=True, product__deleted_at__isnull=True)
        except (ValueError, TypeError, Variant.DoesNotExist):
            return default
        return variant_data(variant)


PRODUCTS = Catalog()
BY_ID = VariantLookup()


def cart_summary(cart):
    lines = []
    for variant_id, quantity in cart.items():
        p = BY_ID.get(variant_id)
        if p and type(quantity) is int and 1 <= quantity <= min(9, p['stock']):
            lines.append({'product': p, 'quantity': quantity, 'total': p['price'] * quantity,
                          'total_display': money(p['price'] * quantity)})
    subtotal = sum(x['total'] for x in lines)
    shipping = 0 if subtotal == 0 or subtotal >= 7500 else 600
    return {'lines': lines, 'count': sum(x['quantity'] for x in lines), 'subtotal': subtotal,
            'shipping': shipping, 'total': subtotal + shipping, 'subtotal_display': money(subtotal),
            'shipping_display': 'Free' if not shipping else money(shipping),
            'total_display': money(subtotal + shipping), 'free_shipping_remaining': money(max(0, 7500 - subtotal))}


def order_receipt(order):
    return {'total_display': money(order.total), 'order_id': str(order.pk)}
