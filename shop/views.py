import secrets
from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from .catalog import PRODUCTS, BY_SLUG, BY_ID, cart_summary


def home(request):
    return render(request, 'shop/home.html', {'products': PRODUCTS[:4], 'page': 'home'})


def catalog(request):
    return render(request, 'shop/catalog.html', {'products': PRODUCTS, 'page': 'catalog'})


def product(request, slug):
    if slug not in BY_SLUG:
        raise Http404
    return render(request, 'shop/product.html', {'product': BY_SLUG[slug], 'products': [p for p in PRODUCTS if p['slug'] != slug][:3], 'page': 'product'})


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
    summary = cart_summary(request.session.get('cart', {}))
    if not summary['lines']:
        return redirect('cart')
    nonce = secrets.token_urlsafe(24)
    request.session['checkout_nonce'] = nonce
    request.session['checkout_snapshot'] = request.session.get('cart', {}).copy()
    if settings.CHECKOUT_MODE == 'simulated':
        # This creates no order and makes no payment request. The reference is a demo receipt only.
        token = signing.dumps({'nonce': nonce, 'amount': summary['total']}, salt='demo-checkout')
        return redirect('/checkout/complete/?demo=' + token)
    import stripe
    client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)
    line_items = [{'price_data': {'currency': 'usd', 'unit_amount': x['product']['price'],
                    'product_data': {'name': x['product']['name']}}, 'quantity': x['quantity']} for x in summary['lines']]
    if summary['shipping']:
        line_items.append({'price_data': {'currency': 'usd', 'unit_amount': summary['shipping'],
                           'product_data': {'name': 'Demo shipping'}}, 'quantity': 1})
    try:
        session = client.v1.checkout.sessions.create(params={'mode': 'payment', 'line_items': line_items,
            'success_url': settings.PUBLIC_ORIGIN + '/checkout/complete/?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': settings.PUBLIC_ORIGIN + '/checkout/cancel/',
            'client_reference_id': nonce}, options={'idempotency_key': 'fieldform-test-' + nonce})
    except stripe.StripeError:
        return render(request, 'shop/checkout.html', {'page': 'checkout', 'checkout_error': 'Sandbox checkout is unavailable. Your bag is saved; please try again.'}, status=502)
    if session.livemode or not session.url or not session.url.startswith('https://checkout.stripe.com/'):
        return HttpResponse('Unsafe checkout response blocked.', status=502)
    request.session['stripe_checkout_id'] = session.id
    return redirect(session.url)


def checkout_complete(request):
    verified = False
    nonce = request.session.get('checkout_nonce')
    if settings.CHECKOUT_MODE == 'simulated':
        try:
            data = signing.loads(request.GET.get('demo', ''), salt='demo-checkout', max_age=1800)
            verified = bool(nonce) and secrets.compare_digest(data['nonce'], nonce)
        except (signing.BadSignature, KeyError, TypeError):
            pass
    elif nonce and request.GET.get('session_id') == request.session.get('stripe_checkout_id'):
        import stripe
        try:
            session = stripe.StripeClient(settings.STRIPE_SECRET_KEY).v1.checkout.sessions.retrieve(request.GET['session_id'])
            verified = (not session.livemode and session.payment_status == 'paid' and
                        session.client_reference_id == nonce and session.amount_total ==
                        cart_summary(request.session.get('checkout_snapshot', {}))['total'])
        except stripe.StripeError:
            pass
    if not verified:
        return redirect('checkout')
    receipt = cart_summary(request.session.get('checkout_snapshot', {}))
    # Preserve a bag modified in another tab while checkout was open.
    if request.session.get('cart', {}) == request.session.get('checkout_snapshot'):
        request.session['cart'] = {}
    for key in ('checkout_nonce', 'checkout_snapshot', 'stripe_checkout_id'):
        request.session.pop(key, None)
    return render(request, 'shop/complete.html', {'page': 'complete', 'receipt': receipt})


def checkout_cancel(request):
    return render(request, 'shop/cancel.html', {'page': 'cancel'})


def about(request):
    return render(request, 'shop/info.html', {'page': 'about', 'info': 'about'})


def shipping(request):
    return render(request, 'shop/info.html', {'page': 'shipping', 'info': 'shipping'})


def robots(request):
    return HttpResponse('User-agent: *\nDisallow: /\n', content_type='text/plain')
