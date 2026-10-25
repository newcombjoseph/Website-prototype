from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection, connections, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from PIL import Image
from shop.admin import VariantForm, ImageForm
from shop.images import prepare_image
from shop.models import Product, Variant, Order, OrderEvent, StockMovement, PaymentEvent
from shop.services import reserve_order, release_order, mark_paid, handle_payment_event, StockError


def make_variant(stock=5):
    product = Product.objects.create(name='Healthcare bonnet', slug='healthcare-bonnet', description='Washable sample bonnet.', published=True)
    return Variant.objects.create(product=product, sku='BONNET-M-CLASSIC', size='Medium', style='Classic', price=2500, stock=stock)


@override_settings(PRIVATE_ACCESS_REQUIRED=False)
class CommerceTests(TestCase):
    def setUp(self):
        self.variant = make_variant()
        self.cart = {str(self.variant.pk): 2}

    def test_order_snapshots_survive_price_and_name_changes(self):
        order = reserve_order(self.cart, 'simulated')
        self.variant.price = 9900
        self.variant.save(update_fields=['price'])
        self.variant.product.name = 'Renamed'
        self.variant.product.save()
        item = order.items.get()
        self.assertEqual(item.product_name, 'Healthcare bonnet')
        self.assertEqual(item.unit_price, 2500)
        self.assertEqual(order.total, 5600)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)
        self.assertEqual(order.history.count(), 1)
        self.assertEqual(StockMovement.objects.get(order=order).delta, -2)

    def test_reservation_release_is_idempotent_and_paid_orders_do_not_restock(self):
        order = reserve_order(self.cart, 'simulated')
        self.assertTrue(release_order(order.pk))
        self.assertFalse(release_order(order.pk))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)
        paid = reserve_order(self.cart, 'simulated')
        mark_paid(paid.pk)
        self.assertFalse(release_order(paid.pk))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)

    def test_no_partial_reservations_invalid_quantities_or_unpublished_sales(self):
        for quantity in (True, 0, 6, -1, '1'):
            with self.assertRaises(StockError):
                reserve_order({str(self.variant.pk): quantity}, 'simulated')
        with self.assertRaises(StockError):
            reserve_order({**self.cart, '9999999': 1}, 'simulated')
        self.variant.product.published = False
        self.variant.product.save()
        with self.assertRaises(StockError):
            reserve_order(self.cart, 'simulated')
        self.assertEqual(Order.objects.count(), 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

    def test_both_variant_options_are_visible_and_inventory_is_independent(self):
        other = Variant.objects.create(product=self.variant.product, sku='BONNET-L-ROOMY', size='Large', style='Roomy', price=2800, stock=8)
        response = self.client.get('/products/healthcare-bonnet/', secure=True)
        self.assertContains(response, 'Medium / Classic')
        self.assertContains(response, 'Large / Roomy')
        reserve_order({str(other.pk): 1}, 'simulated')
        self.variant.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((self.variant.stock, other.stock), (5, 7))

    def event(self, order, event_id='evt_test_paid'):
        return {'id': event_id, 'type': 'checkout.session.completed', 'livemode': False,
                'data': {'object': {'id': order.stripe_session_id, 'livemode': False, 'payment_status': 'paid',
                         'client_reference_id': str(order.pk), 'amount_total': order.total, 'currency': 'usd',
                         'customer_details': {'email': 'test@example.com'},
                         'shipping_details': {'name': 'Test customer', 'address': {'country': 'US'}}}}}

    def stripe_order(self):
        order = reserve_order(self.cart, 'stripe_test')
        order.stripe_session_id = 'cs_test_123'
        order.save(update_fields=['stripe_session_id'])
        return order

    def test_duplicate_webhooks_do_not_duplicate_payment_or_stock(self):
        order = self.stripe_order()
        event = self.event(order)
        handle_payment_event(event)
        handle_payment_event(event)
        handle_payment_event(self.event(order, 'evt_test_duplicate_kind'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.email, 'test@example.com')
        self.assertEqual(order.shipping_details['address']['country'], 'US')
        self.assertEqual(order.history.count(), 2)
        self.assertEqual(PaymentEvent.objects.count(), 2)
        self.assertEqual(StockMovement.objects.filter(order=order).count(), 1)

    def test_webhook_links_order_when_provider_response_was_lost(self):
        order = self.stripe_order()
        event = self.event(order)
        order.stripe_session_id = None
        order.save(update_fields=['stripe_session_id'])
        handle_payment_event(event)
        order.refresh_from_db()
        self.assertEqual(order.stripe_session_id, 'cs_test_123')
        self.assertEqual(order.status, 'paid')

    def test_payment_amount_currency_identity_and_live_events_rejected(self):
        order = self.stripe_order()
        for key, value in [('amount_total', 1), ('currency', 'eur'), ('livemode', True), ('id', 'cs_other'), ('client_reference_id', 'other'), ('payment_status', 'unpaid')]:
            event = self.event(order)
            event['data']['object'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                mark_paid(order.pk, event['data']['object'])
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertFalse(PaymentEvent.objects.exists())

    @override_settings(STRIPE_WEBHOOK_SECRET='test-signing-secret-not-a-live-credential', PRIVATE_ACCESS_REQUIRED=True)
    def test_signed_webhook_bypasses_private_gate_only_after_signature_verification(self):
        order = self.stripe_order()
        with patch('stripe.Webhook.construct_event', return_value=self.event(order)):
            self.assertEqual(self.client.post('/payments/stripe/webhook/', data=b'{}', content_type='application/json', secure=True).status_code, 200)
        import stripe
        with patch('stripe.Webhook.construct_event', side_effect=stripe.SignatureVerificationError('invalid', 'bad')):
            self.assertEqual(self.client.post('/payments/stripe/webhook/', data=b'{}', content_type='application/json', secure=True).status_code, 400)
        self.assertEqual(self.client.get('/shop/', secure=True).status_code, 401)

    def test_expiry_releases_stock_once_and_late_payment_requires_reconciliation(self):
        order = self.stripe_order()
        event = self.event(order)
        event['type'] = 'checkout.session.expired'
        handle_payment_event(event)
        handle_payment_event(event)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)
        with self.assertRaises(ValueError):
            handle_payment_event(self.event(order, 'evt_late_payment'))
        order.refresh_from_db()
        self.assertEqual(order.status, 'expired')
        self.assertEqual(order.history.count(), 2)

    def test_scheduled_expiry_does_not_release_stripe_reservations_locally(self):
        demo = reserve_order({str(self.variant.pk): 1}, 'simulated')
        stripe = reserve_order({str(self.variant.pk): 1}, 'stripe_test')
        Order.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        call_command('expire_reservations', verbosity=0)
        demo.refresh_from_db(); stripe.refresh_from_db()
        self.assertEqual(demo.status, 'expired')
        self.assertEqual(stripe.status, 'pending')

    def test_checkout_retry_reuses_same_reservation(self):
        session = self.client.session
        session['cart'] = self.cart
        session.save()
        first = self.client.post('/checkout/start/', secure=True)
        second = self.client.post('/checkout/start/', secure=True)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)

    def test_seed_repeatability_and_bonnet_samples_are_unpublished(self):
        call_command('seed_store', bonnets=True, verbosity=0)
        call_command('seed_store', bonnets=True, verbosity=0)
        product = Product.objects.get(slug='sample-healthcare-bonnet')
        self.assertFalse(product.published)
        self.assertEqual(product.variants.count(), 6)
        self.assertEqual(product.variants.filter(stock=0).count(), 6)


@override_settings(PRIVATE_ACCESS_REQUIRED=False)
class AdminSecurityTests(TestCase):
    def setUp(self):
        self.variant = make_variant()
        self.user = get_user_model().objects.create_superuser('owner', 'owner@example.com', 'unique-test-only-password')
        self.device = TOTPDevice.objects.create(user=self.user, name='Test authenticator', confirmed=True)

    def verified_login(self, user=None, device=None):
        user = user or self.user
        device = device or self.device
        self.client.force_login(user)
        session = self.client.session
        session['otp_device_id'] = device.persistent_id
        session.save()

    def test_password_only_session_cannot_enter_admin(self):
        self.client.force_login(self.user)
        response = self.client.get('/admin/', secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
        self.verified_login()
        self.assertContains(self.client.get('/admin/', secure=True), 'Bonnet store management')

    def test_real_admin_login_requires_authenticator_code(self):
        data = {'username': 'owner', 'password': 'unique-test-only-password', 'next': '/admin/'}
        response = self.client.post('/admin/login/', data, secure=True)
        self.assertEqual(response.status_code, 200)
        data['otp_token'] = str(totp(self.device.bin_key, step=self.device.step, t0=self.device.t0, digits=self.device.digits, drift=self.device.drift)).zfill(6)
        response = self.client.post('/admin/login/', data, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get('/admin/', secure=True).status_code, 200)

    def test_bad_passwords_are_rate_limited(self):
        for _ in range(5):
            self.client.post('/admin/login/', {'username': 'owner', 'password': 'wrong'}, secure=True)
        self.assertEqual(self.client.post('/admin/login/', {'username': 'owner', 'password': 'wrong'}, secure=True).status_code, 429)

    def test_csrf_is_required_for_admin_login(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/admin/login/', {'username': 'owner', 'password': 'wrong'}, secure=True).status_code, 403)

    def test_catalog_staff_cannot_read_orders_or_manage_staff_accounts(self):
        call_command('setup_staff_roles', verbosity=0)
        staff = get_user_model().objects.create_user('catalog', password='separate-staff-test-password', is_staff=True)
        staff.groups.add(Group.objects.get(name='Catalog and inventory staff'))
        device = TOTPDevice.objects.create(user=staff, confirmed=True)
        self.verified_login(staff, device)
        self.assertEqual(self.client.get('/admin/shop/product/', secure=True).status_code, 200)
        self.assertEqual(self.client.get('/admin/shop/order/', secure=True).status_code, 403)
        self.assertEqual(self.client.get('/admin/auth/user/', secure=True).status_code, 403)

    def test_financial_history_is_readonly_even_for_owner(self):
        order = reserve_order({str(self.variant.pk): 1}, 'simulated')
        self.verified_login()
        data = {'status': 'paid', 'total': 1, 'tracking_number': 'TEST-TRACK'}
        page = self.client.get(f'/admin/shop/order/{order.pk}/change/', secure=True)
        for inline in page.context['inline_admin_formsets']:
            formset = inline.formset
            for key, value in formset.management_form.initial.items():
                data[f'{formset.prefix}-{key}'] = value
            for index, form in enumerate(formset.initial_forms):
                data[f'{formset.prefix}-{index}-id'] = form.instance.pk
        response = self.client.post(f'/admin/shop/order/{order.pk}/change/', data, secure=True)
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.total, 3100)
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.tracking_number, 'TEST-TRACK')
        self.assertEqual(self.client.post(f'/admin/shop/order/{order.pk}/delete/', secure=True).status_code, 403)

    def test_staff_price_and_stock_adjustment_are_audited(self):
        self.verified_login()
        payload = {'product': self.variant.product_id, 'sku': self.variant.sku, 'size': 'Medium', 'style': 'Classic',
                   'dollar_price': '27.50', 'active': 'on', 'stock': 8, 'low_stock_threshold': 5,
                   'adjustment_reason': 'Received three new bonnets',
                   'stock_snapshot': signing.dumps({'id': self.variant.pk, 'stock': 5}, salt='admin-stock')}
        response = self.client.post(f'/admin/shop/variant/{self.variant.pk}/change/', payload, secure=True)
        self.assertEqual(response.status_code, 302, response.content.decode()[:200])
        self.variant.refresh_from_db()
        self.assertEqual((self.variant.price, self.variant.stock), (2750, 8))
        movement = StockMovement.objects.get(variant=self.variant)
        self.assertEqual(movement.delta, 3)
        self.assertEqual(movement.actor, self.user)
        # An old form must not put stock back after a sale.
        reserve_order({str(self.variant.pk): 1}, 'simulated')
        response = self.client.post(f'/admin/shop/variant/{self.variant.pk}/change/', payload, secure=True)
        self.assertContains(response, 'Stock changed while editing')
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 7)

    def test_picture_validation_and_reencoding(self):
        image = BytesIO()
        Image.new('RGB', (2400, 100), 'green').save(image, 'PNG')
        upload = SimpleUploadedFile('unsafe-name.png', image.getvalue(), content_type='image/png')
        cleaned = prepare_image(upload)
        self.assertTrue(cleaned.name.endswith('.webp'))
        self.assertNotIn('unsafe', cleaned.name)
        with Image.open(cleaned) as result:
            self.assertEqual(result.format, 'WEBP')
            self.assertLessEqual(result.width, 2000)
        for name, data in [('attack.svg', b'<svg onload="alert(1)"/>'), ('fake.png', b'not an image')]:
            with self.assertRaises(ValidationError):
                prepare_image(SimpleUploadedFile(name, data))
        with self.assertRaises(ValidationError):
            prepare_image(SimpleUploadedFile('huge.png', b'0' * (8 * 1024 * 1024 + 1)))


class ConcurrentInventoryTests(TransactionTestCase):
    def test_two_buyers_cannot_purchase_the_same_last_bonnet(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Row-lock concurrency requires PostgreSQL; SQLite is not production validation.')
        variant = make_variant(stock=1)
        def buy():
            close_old_connections()
            try:
                reserve_order({str(variant.pk): 1}, 'simulated')
                return 'reserved'
            except StockError:
                return 'out-of-stock'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: buy(), range(2)))
        self.assertCountEqual(results, ['reserved', 'out-of-stock'])
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 0)
        self.assertEqual(Order.objects.count(), 1)

@override_settings(PRIVATE_ACCESS_REQUIRED=False)
class AdditionalSecurityTests(TestCase):
    def test_production_checks_reject_sqlite_missing_storage_and_bad_rds_tls(self):
        from shop.checks import production_checks
        import os
        with patch.dict(os.environ, {'APP_ENV': 'production'}):
            with override_settings(AWS_STORAGE_BUCKET_NAME='', PRIVATE_ACCESS_REQUIRED=False):
                with patch.dict(settings.DATABASES, {'default': {'ENGINE': 'django.db.backends.sqlite3'}}):
                    self.assertTrue({'shop.E002', 'shop.E003'} <= {e.id for e in production_checks(None)})
            with override_settings(AWS_STORAGE_BUCKET_NAME='example-bonnet-images', PRIVATE_ACCESS_REQUIRED=False):
                with patch.dict(settings.DATABASES, {'default': {'ENGINE': 'django.db.backends.postgresql', 'HOST': 'example.rds.amazonaws.com', 'OPTIONS': {'sslmode': 'require'}}}):
                    self.assertIn('shop.E004', {e.id for e in production_checks(None)})

    @override_settings(STRIPE_WEBHOOK_SECRET='local-test-only-signature-secret')
    def test_actual_signature_verification_rejects_forged_payload(self):
        import hashlib
        import hmac
        import json
        import time
        variant = make_variant()
        order = reserve_order({str(variant.pk): 1}, 'stripe_test')
        order.stripe_session_id = 'cs_test_signed'
        order.save(update_fields=['stripe_session_id'])
        event = {'id': 'evt_signed', 'type': 'checkout.session.completed', 'livemode': False,
                 'data': {'object': {'id': order.stripe_session_id, 'livemode': False, 'payment_status': 'paid',
                          'client_reference_id': str(order.pk), 'amount_total': order.total, 'currency': 'usd'}}}
        payload = json.dumps(event).encode()
        timestamp = int(time.time())
        digest = hmac.new(settings.STRIPE_WEBHOOK_SECRET.encode(), str(timestamp).encode() + b'.' + payload, hashlib.sha256).hexdigest()
        headers = {'HTTP_STRIPE_SIGNATURE': f't={timestamp},v1={digest}'}
        self.assertEqual(self.client.post('/payments/stripe/webhook/', payload + b' ', content_type='application/json', secure=True, **headers).status_code, 400)
        self.assertEqual(self.client.post('/payments/stripe/webhook/', payload, content_type='application/json', secure=True, **headers).status_code, 200)
        self.assertEqual(self.client.post('/payments/stripe/webhook/', payload, content_type='application/json', secure=True, **headers).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(PaymentEvent.objects.count(), 1)

    def test_recovery_code_is_one_time_only(self):
        from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
        user = get_user_model().objects.create_superuser('recovery-owner', 'owner@example.com', 'unique-recovery-test-password')
        device = StaticDevice.objects.create(user=user, name='Recovery', confirmed=True)
        token = StaticToken.random_token()
        StaticToken.objects.create(device=device, token=token)
        data = {'username': user.username, 'password': 'unique-recovery-test-password', 'otp_token': token, 'otp_device': device.persistent_id, 'next': '/admin/'}
        self.assertEqual(self.client.post('/admin/login/', data, secure=True).status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.post('/admin/login/', data, secure=True).status_code, 200)
        self.assertEqual(self.client.get('/admin/', secure=True).status_code, 302)
