import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from shop.models import Product, Variant, StockMovement

PRODUCT_FIELDS = ['name', 'category', 'description', 'materials', 'dimensions', 'care', 'note', 'badge']
DATA_ROOT = Path(__file__).resolve().parents[2]


def archive_original_samples():
    """Hide untouched household fixtures without deleting records or changing stock.

    Customized products (including stock/price edits and uploaded images) remain
    under the owner's control. Historical order items retain their snapshots.
    """
    for original in json.loads((DATA_ROOT / 'legacy_samples.json').read_text()):
        product = Product.objects.select_for_update().filter(slug=original['slug'], published=True).first()
        if not product or product.images.exists() or any(getattr(product, field) != original[field] for field in PRODUCT_FIELDS):
            continue
        variants = list(product.variants.select_for_update().order_by('id'))
        if len(variants) != 1:
            continue
        variant = variants[0]
        expected = {'sku': f'DEMO-{original["id"]}', 'size': 'One size', 'style': original['color'],
                    'price': original['price'], 'stock': original['stock'], 'active': True,
                    'low_stock_threshold': 5}
        if all(getattr(variant, field) == value for field, value in expected.items()):
            product.published = False
            product.updated_at = timezone.now()
            product.save(update_fields=['published', 'updated_at'])


class Command(BaseCommand):
    help = 'Add the sample scrub cap collection and archive untouched household samples; preserve edited products, stock and orders.'

    def add_arguments(self, parser):
        parser.add_argument('--bonnets', action='store_true', help='Add the original draft bonnet fitting examples with zero stock; preserved for compatibility.')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['bonnets']:
            product, created = Product.objects.get_or_create(slug='sample-healthcare-bonnet', defaults={
                'name': 'Sample healthcare bonnet', 'description': 'Sample only. Replace with your actual fabric, sizing, price and care information before publishing.',
                'category': 'Healthcare bonnets', 'published': False})
            if created:
                for size in ['Small', 'Medium', 'Large']:
                    for style in ['Classic', 'Roomy']:
                        variant = Variant.objects.create(product=product, sku=f'SAMPLE-{size.upper()}-{style.upper()}', size=size, style=style, price=2500, stock=0)
                        StockMovement.objects.create(variant=variant, delta=0, reason='Sample variant; add real inventory before publishing')
        else:
            archive_original_samples()
            for item in json.loads((DATA_ROOT / 'products.json').read_text()):
                product, created = Product.objects.get_or_create(slug=item['slug'], defaults={
                    **{key: item[key] for key in PRODUCT_FIELDS}, 'published': True})
                if created:
                    for size in ['Small', 'Medium', 'Large']:
                        variant = Variant.objects.create(product=product, sku=f'CAP-{item["id"]:02}-{size[0]}', size=size,
                                                         style=item['color'], price=item['price'], stock=item['stock'])
                        StockMovement.objects.create(variant=variant, delta=item['stock'], reason='Sample scrub cap opening stock')
        self.stdout.write(self.style.SUCCESS('Sample caps ready. Edited products, stock, orders and history were preserved.'))
