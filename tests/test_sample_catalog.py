import json
from pathlib import Path
from django.core.management import call_command
from django.test import TestCase, override_settings
from shop.models import Product, Variant, Order, StockMovement
from shop.services import reserve_order, release_order

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['name', 'category', 'description', 'materials', 'dimensions', 'care', 'note', 'badge']


@override_settings(PRIVATE_ACCESS_REQUIRED=False)
class SampleCatalogTests(TestCase):
    def original_sample(self):
        original = json.loads((ROOT / 'shop/legacy_samples.json').read_text())[0]
        product = Product.objects.create(slug=original['slug'], published=True,
                                         **{field: original[field] for field in FIELDS})
        variant = Variant.objects.create(product=product, sku=f'DEMO-{original["id"]}', size='One size',
                                         style=original['color'], price=original['price'], stock=original['stock'])
        return original, product, variant

    def test_fresh_catalog_has_eight_caps_and_selectable_sizes(self):
        call_command('seed_store', verbosity=0)
        self.assertEqual(Product.objects.filter(published=True).count(), 8)
        self.assertEqual(Variant.objects.count(), 24)
        for product in Product.objects.all():
            self.assertIn('Cap', product.name)
            self.assertEqual(set(product.variants.values_list('size', flat=True)), {'Small', 'Medium', 'Large'})
            self.assertTrue(all(v.stock > 0 for v in product.variants.all()))
            response = self.client.get(f'/products/{product.slug}/', secure=True)
            self.assertContains(response, 'Small /')
            self.assertContains(response, 'Medium /')
            self.assertContains(response, 'Large /')

    def test_household_sample_is_archived_without_deleting_order_history(self):
        original, product, variant = self.original_sample()
        order = reserve_order({str(variant.pk): 1}, 'simulated')
        release_order(order.pk)
        history_before = list(order.history.values_list('message', flat=True))
        stock_before = list(StockMovement.objects.values_list('delta', flat=True))
        call_command('seed_store', verbosity=0)
        product.refresh_from_db(); variant.refresh_from_db(); order.refresh_from_db()
        self.assertFalse(product.published)
        self.assertEqual(variant.stock, original['stock'])
        self.assertEqual(order.items.get().product_name, original['name'])
        self.assertEqual(list(order.history.values_list('message', flat=True)), history_before)
        self.assertEqual(list(StockMovement.objects.filter(variant=variant).values_list('delta', flat=True)), stock_before)
        self.assertNotContains(self.client.get('/shop/', secure=True), original['name'])
        self.assertEqual(Order.objects.count(), 1)

    def test_edited_household_and_scrub_cap_records_are_not_overwritten(self):
        original, product, variant = self.original_sample()
        variant.price = 4100
        variant.stock = 11
        variant.save(update_fields=['price', 'stock'])
        call_command('seed_store', verbosity=0)
        cap = Product.objects.get(slug='classic-tie-back-scrub-cap')
        cap.name = 'My actual scrub cap'
        cap.save(update_fields=['name'])
        cap_variant = cap.variants.get(size='Medium')
        cap_variant.price = 3700
        cap_variant.stock = 3
        cap_variant.save(update_fields=['price', 'stock'])
        count = Variant.objects.count()
        call_command('seed_store', verbosity=0)
        product.refresh_from_db(); variant.refresh_from_db(); cap.refresh_from_db(); cap_variant.refresh_from_db()
        self.assertTrue(product.published)
        self.assertEqual((variant.price, variant.stock), (4100, 11))
        self.assertEqual(cap.name, 'My actual scrub cap')
        self.assertEqual((cap_variant.price, cap_variant.stock), (3700, 3))
        self.assertEqual(Variant.objects.count(), count)
