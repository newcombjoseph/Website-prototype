import base64
import json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from django.test import TestCase, Client, override_settings
from django.contrib.auth.hashers import make_password
from django.conf import settings
from shop.catalog import PRODUCTS

@override_settings(PRIVATE_ACCESS_REQUIRED=False)
class BrowsingAndCartTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command('seed_store', verbosity=0)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        from shop.models import Variant
        samples = json.loads((Path(__file__).resolve().parents[1] / 'shop/products.json').read_text())
        self.ids = [Variant.objects.get(product__slug=item['slug'], size='Small').pk for item in samples]

    def post(self, path, data=None):
        self.client.get('/shop/', secure=True)
        return self.client.post(path, data or {}, secure=True, HTTP_ORIGIN='https://testserver', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def test_all_browsing_pages_and_images(self):
        for path in ['/', '/shop/', '/cart/', '/checkout/', '/about/', '/shipping/'] + [f'/products/{p["slug"]}/' for p in PRODUCTS]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, secure=True).status_code, 200)
        self.assertEqual(self.client.get('/products/missing/', secure=True).status_code, 404)
        for p in PRODUCTS:
            path = settings.STATIC_ROOT / 'shop/images' / p['image']
            self.assertTrue(path.exists())

    def test_cart_totals_update_remove_and_persistence(self):
        self.assertEqual(self.post('/cart/add/', {'product_id':str(self.ids[0]),'quantity':'2','price':'1'}).status_code,302)
        page = self.client.get('/cart/',secure=True)
        self.assertContains(page, '$56.00'); self.assertContains(page, '$62.00')
        self.post('/cart/add/', {'product_id':str(self.ids[1]),'quantity':'1'})
        page = self.client.get('/cart/',secure=True)
        self.assertContains(page, '$80.00'); self.assertContains(page, 'Free')
        self.post('/cart/update/', {'product_id':str(self.ids[0]),'quantity':'1'})
        self.assertContains(self.client.get('/cart/',secure=True),'$58.00')
        self.post('/cart/update/', {'product_id':str(self.ids[0]),'quantity':'0'})
        self.post('/cart/update/', {'product_id':str(self.ids[1]),'quantity':'0'})
        self.assertContains(self.client.get('/cart/',secure=True),'Your bag is empty')

    def test_invalid_mutations_and_csrf(self):
        for quantity in ('-1','0','10','1.5','abc'):
            with self.subTest(quantity=quantity):
                self.assertEqual(self.post('/cart/add/', {'product_id':str(self.ids[0]),'quantity':quantity}).status_code,400)
        self.assertEqual(self.post('/cart/add/', {'product_id':'999','quantity':'1'}).status_code,400)
        self.post('/cart/add/', {'product_id':str(self.ids[0]),'quantity':'9'})
        self.assertEqual(self.post('/cart/add/', {'product_id':str(self.ids[0]),'quantity':'1'}).status_code,400)
        self.assertEqual(self.client.post('/cart/add/',{'product_id':str(self.ids[0]),'quantity':'1'},secure=True).status_code,403)
        self.assertEqual(self.client.get('/cart/add/',secure=True).status_code,405)

    def test_cancel_preserves_cart_and_signed_confirmation(self):
        self.post('/cart/add/', {'product_id':str(self.ids[2]),'quantity':'1'})
        self.assertContains(self.client.get('/checkout/cancel/',secure=True),'Your bag is still here')
        self.assertEqual(self.client.session['cart'], {str(self.ids[2]):1})
        self.assertRedirects(self.client.get('/checkout/complete/?demo=forged',secure=True),'/checkout/',fetch_redirect_response=False)
        result = self.post('/checkout/start/')
        self.assertIn('/checkout/complete/?demo=',result.url)
        receipt = self.client.get(result.url,secure=True)
        self.assertContains(receipt,'$38.00')
        self.assertContains(receipt,'A test order was saved')
        self.assertEqual(self.client.session['cart'],{})
        self.assertRedirects(self.client.get(result.url,secure=True),'/checkout/',fetch_redirect_response=False)

    def test_empty_checkout_and_security_headers(self):
        self.assertRedirects(self.post('/checkout/start/'),'/cart/',fetch_redirect_response=False)
        response=self.client.get('/',secure=True)
        self.assertIn("object-src 'none'",response['Content-Security-Policy'])
        self.assertEqual(response['X-Frame-Options'],'DENY')
        self.assertEqual(response['X-Robots-Tag'],'noindex, nofollow, noarchive')
        self.assertEqual(response['Cache-Control'],'no-store')
        self.assertIn('max-age=31536000',response['Strict-Transport-Security'])
        self.assertEqual(self.client.get('/').status_code,301)
        self.assertEqual(self.client.get('/',secure=True,HTTP_HOST='evil.invalid').status_code,400)
        self.assertTrue(self.client.cookies['csrftoken']['secure'])

    @override_settings(CHECKOUT_MODE='stripe_test',STRIPE_SECRET_KEY='sk_test_fake_not_a_credential')
    def test_stripe_test_handoff_and_verified_return(self):
        self.post('/cart/add/',{'product_id':str(self.ids[0]),'quantity':'1'})
        session=SimpleNamespace(id='cs_test_demo',url='https://checkout.stripe.com/c/pay/cs_test_demo',livemode=False)
        with patch('stripe.StripeClient') as stripe_client:
            stripe_client.return_value.v1.checkout.sessions.create.return_value=session
            response=self.post('/checkout/start/')
            self.assertEqual(response.url,session.url)
            params=stripe_client.return_value.v1.checkout.sessions.create.call_args.kwargs['params']
            self.assertEqual(params['line_items'][0]['price_data']['unit_amount'],2800)
            self.assertEqual(params['payment_method_types'], ['card'])
            self.assertNotIn('card_number', json.dumps(params))
            from shop.models import Order
            from shop.services import mark_paid
            order = Order.objects.get(pk=self.client.session['checkout_order'])
            mark_paid(order.pk, {'id': session.id, 'livemode': False, 'payment_status': 'paid', 'client_reference_id': str(order.pk), 'amount_total': 3400, 'currency': 'usd'})
            receipt=self.client.get('/checkout/complete/?session_id=cs_test_demo',secure=True)
            self.assertContains(receipt,'$34.00')

    @override_settings(CHECKOUT_MODE='stripe_test',STRIPE_SECRET_KEY='sk_test_fake_not_a_credential')
    def test_stripe_live_response_and_unpaid_return_blocked(self):
        self.post('/cart/add/',{'product_id':str(self.ids[0]),'quantity':'1'})
        with patch('stripe.StripeClient') as stripe_client:
            stripe_client.return_value.v1.checkout.sessions.create.return_value=SimpleNamespace(id='cs_live_bad',url='https://checkout.stripe.com/evil',livemode=True)
            self.assertEqual(self.post('/checkout/start/').status_code,502)
            stripe_client.return_value.v1.checkout.sessions.create.return_value=SimpleNamespace(id='cs_test_demo',url='https://checkout.stripe.com/c/pay/cs_test_demo',livemode=False)
            self.post('/checkout/start/')
            stripe_client.return_value.v1.checkout.sessions.retrieve.return_value=SimpleNamespace(payment_status='unpaid')
            self.assertEqual(self.client.get('/checkout/complete/?session_id=cs_test_demo',secure=True).status_code,202)
            self.assertEqual(self.client.session['cart'],{str(self.ids[0]):1})

class PrivateAccessTests(TestCase):
    def test_fail_closed_and_owner_authentication(self):
        self.assertEqual(self.client.get('/',secure=True).status_code,401)
        self.assertEqual(self.client.get('/static/shop/css/store.css',secure=True).status_code,401)
        with override_settings(PRIVATE_USERNAME='owner',PRIVATE_PASSWORD_HASH=make_password('test-only-private-password')):
            invalid=base64.b64encode(b'owner:wrong').decode()
            self.assertEqual(self.client.get('/',secure=True,HTTP_AUTHORIZATION='Basic '+invalid).status_code,401)
            valid=base64.b64encode(b'owner:test-only-private-password').decode()
            self.assertEqual(self.client.get('/',secure=True,HTTP_AUTHORIZATION='Basic '+valid).status_code,200)
            asset=self.client.get('/static/shop/css/store.css',secure=True,HTTP_AUTHORIZATION='Basic '+valid)
            self.assertEqual(asset.status_code,200)
            self.assertTrue(asset['Content-Type'].startswith('text/css'))
            bad_unicode=base64.b64encode('é:invalid'.encode()).decode()
            self.assertEqual(self.client.get('/',secure=True,HTTP_AUTHORIZATION='Basic '+bad_unicode).status_code,401)
