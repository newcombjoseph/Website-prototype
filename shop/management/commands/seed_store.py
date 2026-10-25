import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from shop.models import Product, Variant, StockMovement

class Command(BaseCommand):
    help = 'Import original placeholder catalog, or sample bonnet variants. Never overwrites existing products or stock.'
    def add_arguments(self, parser):
        parser.add_argument('--bonnets', action='store_true', help='Add clearly marked sample bonnets in small/medium/large and two styles, as drafts.')
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
            data = json.loads((Path(__file__).resolve().parents[2] / 'products.json').read_text())
            for item in data:
                product, created = Product.objects.get_or_create(slug=item['slug'], defaults={
                    **{k: item[k] for k in ['name', 'category', 'description', 'materials', 'dimensions', 'care', 'note', 'badge']}, 'published': True})
                if created:
                    variant = Variant.objects.create(product=product, sku=f'DEMO-{item["id"]}', size='One size', style=item['color'], price=item['price'], stock=item['stock'])
                    StockMovement.objects.create(variant=variant, delta=item['stock'], reason='Imported original placeholder stock')
        self.stdout.write(self.style.SUCCESS('Seed complete. Existing products and inventory were preserved.'))
