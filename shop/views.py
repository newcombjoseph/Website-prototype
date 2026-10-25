from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from .catalog import PRODUCTS, BY_ID, cart_summary, product_cards, order_receipt
from .models import Order
from .services import reserve_order, release_order, mark_paid, handle_payment_event, StockError
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
import logging
logger = logging.getLogger(__name__)


def home(request):
    return render(request, 'shop/home.html', {'products': PRODUCTS[:4], 'page': 'home'})


@ensure_csrf_cookie
def catalog(request):
    cards = product_cards()
    return render(request, 'shop/catalog.html', {'products': cards, 'categories': sorted({p['category'] for p in cards}), 'page': 'catalog'})


def product(request, slug):
    cards = product_cards()
    selected = next((p for p in cards if p['slug'] == slug), None)
    if selected is None:
        raise Http404
    return render(request, 'shop/product.html', {'product': selected, 'products': [p for p in cards if p['slug'] != slug][:3], 'page': 'product'})


def cart(request):
    return render(request, 'shop/cart.html', {'page': 'cart'})


def validated_item(request, allow_zero=False):
    p = BY_ID.get(request.POST.get('product_id', ''))
    try:
        quantity = int(request.POST.get('quantity', '1'))
    except (ValueError, TypeError):
        return None
    if not p or not (0 if allow_zero else 1) <= quantity <= min(9, p['stock']):
        return None
    return p, quantity


@require_POST
def cart_add(request):
    item = validated_item(request)
    if not item:
        return HttpResponseBadRequest('Invalid product or quantity. Quantities must be between 1 and 9.')
    p, quantity = item
    cart = request.session.get('cart', {})
    key = str(p['id'])
    total = cart.get(key, 0) + quantity
    if total > min(9, p['stock']):
        return HttpResponseBadRequest('The maximum quantity is 9 per product.')
    cart[key] = total
    request.session['cart'] = cart
    request.session.pop('checkout_snapshot', None)
    return redirect('cart')


@require_POST
def cart_update(request):
    if request.POST.get('quantity') == '0':
        cart = request.session.get('cart', {})
        cart.pop(request.POST.get('product_id', ''), None)
        request.session['cart'] = cart
        return redirect('cart')
    item = validated_item(request, allow_zero=True)
    if not item:
        return HttpResponseBadRequest('Invalid product or quantity.')
    p, quantity = item
    cart = request.session.get('cart', {})
    key = str(p['id'])
    if quantity:
        cart[key] = quantity
    else:
        cart.pop(key, None)
    request.session['cart'] = cart
    request.session.pop('checkout_snapshot', None)
    return redirect('cart')


def checkout(request):
    return render(request, 'shop/checkout.html', {'page': 'checkout'})


@require_POST
def checkout_start(request):
    cart = request.session.get('cart', {})
    if not cart:
        return redirect('cart')
    # Reuse the same immutable reservation on retries, rather than reserving twice.
    order_id = request.session.get('checkout_order')
    order = Order.objects.filter(pk=order_id, status=Order.Status.PENDING).first() if order_id else None
    if order and (request.session.get('checkout_snapshot') != cart or order.mode != settings.CHECKOUT_MODE):
        return render(request, 'shop/checkout.html', {'page': 'checkout', 'checkout_error': 'An earlier checkout is still pending. Finish or expire it before starting a different checkout.'}, status=409)
    if not order:
        try:
            order = reserve_order(cart, settings.CHECKOUT_MODE)
        except StockError as exc:
            return render(request, 'shop/checkout.html', {'page': 'checkout', 'checkout_error': str(exc)}, status=409)
        request.session['checkout_order'] = str(order.pk)
        request.session['checkout_snapshot'] = cart.copy()
        # Persist ownership before calling the external provider. Retrying the same
        # session uses the same order and provider idempotency key after a timeout.
        request.session.save()
    if order.mode == 'simulated':
        token = signing.dumps({'order': str(order.pk), 'session': request.session.session_key}, salt='demo-checkout')
        return redirect('/checkout/complete/?demo=' + token)
    import stripe
    client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)
    items = [{'price_data': {'currency': order.currency, 'unit_amount': item.unit_price,
             'product_data': {'name': f'{item.product_name} / {item.size} / {item.style}'}}, 'quantity': item.quantity} for item in order.items.all()]
    if order.shipping:
        items.append({'price_data': {'currency': order.currency, 'unit_amount': order.shipping,
                      'product_data': {'name': 'Demo shipping'}}, 'quantity': 1})
    try:
        session = client.v1.checkout.sessions.create(params={'mode': 'payment', 'line_items': items,
            'payment_method_types': ['card'], 'shipping_address_collection': {'allowed_countries': ['US']},
            'expires_at': int(order.expires_at.timestamp()),
            'success_url': settings.PUBLIC_ORIGIN + '/checkout/complete/?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': settings.PUBLIC_ORIGIN + '/checkout/cancel/',
            'client_reference_id': str(order.pk)}, options={'idempotency_key': 'fieldform-test-' + str(order.pk)})
    except stripe.StripeError:
        return render(request, 'shop/checkout.html', {'page': 'checkout', 'checkout_error': 'Sandbox checkout is unavailable. Your reservation is saved; retry this checkout.'}, status=502)
    if session.livemode or not session.url or not session.url.startswith('https://checkout.stripe.com/'):
        logger.error('Unsafe Stripe checkout response blocked for order %s', order.pk)
        return HttpResponse('Unsafe checkout response blocked.', status=502)
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        locked.stripe_session_id = session.id
        locked.save(update_fields=['stripe_session_id'])
    return redirect(session.url)


def checkout_complete(request):
    order_id = request.session.get('checkout_order')
    order = Order.objects.filter(pk=order_id).first() if order_id else None
    if not order:
        return redirect('checkout')
    if order.mode == 'simulated':
        try:
            data = signing.loads(request.GET.get('demo', ''), salt='demo-checkout', max_age=1800)
            if data != {'order': str(order.pk), 'session': request.session.session_key}:
                return redirect('checkout')
            order = mark_paid(order.pk)
        except (signing.BadSignature, ValueError):
            return redirect('checkout')
    else:
        # Provider notifications, never browser return parameters, authorize payment.
        if request.GET.get('session_id') != order.stripe_session_id:
            return redirect('checkout')
        if order.status not in (Order.Status.PAID, Order.Status.SHIPPED):
            return render(request, 'shop/payment_pending.html', {'page': 'checkout'}, status=202)
    if request.session.get('cart', {}) == request.session.get('checkout_snapshot'):
        request.session['cart'] = {}
    for key in ('checkout_order', 'checkout_snapshot'):
        request.session.pop(key, None)
    return render(request, 'shop/complete.html', {'page': 'complete', 'receipt': order_receipt(order)})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    import stripe
    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse('Webhook is not configured.', status=503)
    if len(request.body) > 1024 * 1024:
        return HttpResponseBadRequest('Payload too large.')
    try:
        event = stripe.Webhook.construct_event(request.body, request.headers.get('Stripe-Signature', ''), settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponseBadRequest('Invalid signature.')
    if event.get('livemode') is not False:
        return HttpResponseBadRequest('Live events are disabled.')
    if event['type'] not in {'checkout.session.completed', 'checkout.session.async_payment_succeeded', 'checkout.session.expired', 'checkout.session.async_payment_failed'}:
        return HttpResponse(status=200)
    try:
        handle_payment_event(event)
    except Order.DoesNotExist:
        # Retry: notification may race the response that stores the session ID.
        return HttpResponse('Order is not linked yet.', status=503)
    except (ValueError, KeyError):
        logger.error('Payment event requires reconciliation: %s', event.get('id'))
        return HttpResponse('Payment event requires reconciliation.', status=409)
    return HttpResponse(status=200)


def checkout_cancel(request):
    order_id = request.session.get('checkout_order')
    order = Order.objects.filter(pk=order_id, mode='simulated').first() if order_id else None
    if order and release_order(order.pk):
        request.session.pop('checkout_order', None)
    return render(request, 'shop/cancel.html', {'page': 'cancel'})


def about(request):
    return render(request, 'shop/info.html', {'page': 'about', 'info': 'about'})


def shipping(request):
    return render(request, 'shop/info.html', {'page': 'shipping', 'info': 'shipping'})


def robots(request):
    return HttpResponse('User-agent: *\nDisallow: /\n', content_type='text/plain')
