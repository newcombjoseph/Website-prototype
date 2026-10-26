from types import SimpleNamespace
from django.contrib.admin.models import LogEntry, DELETION
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice
from shop.admin import site
from shop.catalog import BY_ID
from shop.models import Product, Variant, ProductImage, Order, StockMovement
from shop.services import reserve_order, release_order, mark_paid, StockError


@override_settings(PRIVATE_ACCESS_REQUIRED=False)
class ProductDeletionTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(name='Scrub cap to remove', slug='cap-to-remove', description='Test cap', published=True)
        self.variant = Variant.objects.create(product=self.product, sku='REMOVE-M', size='Medium', style='Navy', price=2500, stock=8)
        StockMovement.objects.create(variant=self.variant, delta=8, reason='Opening stock')
        self.image = ProductImage.objects.create(product=self.product, image='products/retained.webp', alt_text='Retained cap picture')
        self.user = get_user_model().objects.create_superuser('delete-owner', 'owner@example.com', 'unique-product-deletion-test-password')
        self.sign_in(self.user)

    def sign_in(self, user):
        device = TOTPDevice.objects.create(user=user, name='Delete test authenticator', confirmed=True)
        self.client.force_login(user)
        session = self.client.session
        session['otp_device_id'] = device.persistent_id
        session.save()

    def delete_product(self):
        return self.client.post(f'/admin/shop/product/{self.product.pk}/delete/', {'post': 'yes'}, secure=True)

    def test_delete_button_confirmation_and_paid_history_preservation(self):
        order = reserve_order({str(self.variant.pk): 2}, 'simulated')
        mark_paid(order.pk)
        history = list(order.history.values_list('message', flat=True))
        stock = list(StockMovement.objects.filter(variant=self.variant).values_list('delta', flat=True))
        change_page = self.client.get(f'/admin/shop/product/{self.product.pk}/change/', secure=True)
        self.assertContains(change_page, f'/admin/shop/product/{self.product.pk}/delete/')
        confirmation = self.client.get(f'/admin/shop/product/{self.product.pk}/delete/', secure=True)
        self.assertContains(confirmation, 'Delete from the catalog')
        self.product.refresh_from_db()
        self.assertIsNone(self.product.deleted_at)  # Visiting confirmation never deletes.
        response = self.delete_product()
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db(); self.variant.refresh_from_db(); order.refresh_from_db()
        self.assertIsNotNone(self.product.deleted_at)
        self.assertFalse(self.product.published)
        self.assertEqual(self.variant.stock, 6)
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.items.get().product_name, 'Scrub cap to remove')
        self.assertEqual(list(order.history.values_list('message', flat=True)), history)
        self.assertEqual(list(StockMovement.objects.filter(variant=self.variant).values_list('delta', flat=True)), stock)
        self.assertTrue(ProductImage.objects.filter(pk=self.image.pk).exists())
        self.assertTrue(LogEntry.objects.filter(user=self.user, object_id=str(self.product.pk), action_flag=DELETION).exists())
        self.assertNotContains(self.client.get('/shop/', secure=True), 'Scrub cap to remove')
        product_list = self.client.get('/admin/shop/product/', secure=True)
        self.assertFalse(product_list.context['cl'].queryset.filter(pk=self.product.pk).exists())
        self.assertNotContains(self.client.get('/admin/shop/variant/', secure=True), 'REMOVE-M')
        self.assertEqual(self.client.get('/products/cap-to-remove/', secure=True).status_code, 404)
        self.assertIsNone(BY_ID.get(self.variant.pk))
        with self.assertRaises(StockError):
            reserve_order({str(self.variant.pk): 1}, 'simulated')

    def test_bulk_delete_requires_confirmation_and_keeps_related_records(self):
        other = Product.objects.create(name='Second cap', slug='second-cap', description='Sample', published=True)
        data = {'action': 'delete_selected', '_selected_action': [str(self.product.pk), str(other.pk)]}
        response = self.client.post('/admin/shop/product/', data, secure=True)
        self.assertContains(response, 'Delete from the catalog')
        self.assertEqual(Product.objects.filter(deleted_at__isnull=True).count(), 2)
        response = self.client.post('/admin/shop/product/', {**data, 'post': 'yes'}, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.filter(deleted_at__isnull=False).count(), 2)
        self.assertTrue(Variant.objects.filter(pk=self.variant.pk).exists())
        self.assertTrue(StockMovement.objects.filter(variant=self.variant).exists())

    def test_catalog_permission_can_delete_but_change_only_staff_cannot(self):
        staff = get_user_model().objects.create_user('edit-only', password='staff-deletion-test-password', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_product'), Permission.objects.get(codename='change_product'))
        self.sign_in(staff)
        self.assertEqual(self.delete_product().status_code, 403)
        self.product.refresh_from_db()
        self.assertIsNone(self.product.deleted_at)
        call_command('setup_staff_roles', verbosity=0)
        from django.contrib.auth.models import Group
        staff.groups.add(Group.objects.get(name='Catalog and inventory staff'))
        self.assertEqual(self.delete_product().status_code, 302)
        self.product.refresh_from_db()
        self.assertIsNotNone(self.product.deleted_at)

    def test_csrf_and_mfa_remain_required_for_deletion(self):
        self.client.logout()
        self.client.force_login(self.user)  # Password-only session has no verified device.
        self.assertEqual(self.delete_product().status_code, 302)
        self.product.refresh_from_db()
        self.assertIsNone(self.product.deleted_at)
        self.client = Client(enforce_csrf_checks=True)
        self.sign_in(self.user)
        self.assertEqual(self.delete_product().status_code, 403)
        self.product.refresh_from_db()
        self.assertIsNone(self.product.deleted_at)

    def test_deleted_product_pending_order_can_still_release_reserved_stock(self):
        order = reserve_order({str(self.variant.pk): 2}, 'simulated')
        self.assertEqual(self.delete_product().status_code, 302)
        self.assertTrue(release_order(order.pk))
        self.variant.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)
        self.assertIsNotNone(self.product.deleted_at)
        self.assertIsNone(BY_ID.get(self.variant.pk))
        self.assertEqual(Order.objects.get(pk=order.pk).status, 'cancelled')

    def test_deleted_samples_are_not_recreated_by_setup(self):
        call_command('seed_store', verbosity=0)
        sample = Product.objects.get(slug='classic-tie-back-scrub-cap')
        response = self.client.post(f'/admin/shop/product/{sample.pk}/delete/', {'post': 'yes'}, secure=True)
        self.assertEqual(response.status_code, 302)
        original_pk = sample.pk
        call_command('seed_store', verbosity=0)
        sample.refresh_from_db()
        self.assertEqual(sample.pk, original_pk)
        self.assertIsNotNone(sample.deleted_at)
        self.assertFalse(sample.published)
        self.assertEqual(sample.variants.count(), 3)

    def test_stale_edit_cannot_clear_the_deletion_marker(self):
        stale = Product.objects.get(pk=self.product.pk)
        self.assertEqual(self.delete_product().status_code, 302)
        stale.name = 'Late edit from an already open form'
        stale.published = True
        site._registry[Product].save_model(SimpleNamespace(user=self.user), stale,
                                          SimpleNamespace(fields={'name': None, 'published': None}), change=True)
        self.product.refresh_from_db()
        self.assertIsNotNone(self.product.deleted_at)
        self.assertFalse(self.product.published)
        self.assertIsNone(BY_ID.get(self.variant.pk))
        self.assertEqual(self.client.get('/products/cap-to-remove/', secure=True).status_code, 404)
