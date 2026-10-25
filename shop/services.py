"""All stock/order transitions lock records in a consistent order (PostgreSQL)."""
from datetime import timedelta
from uuid import UUID
from django.db import transaction
from django.utils import timezone
from .models import Order, OrderItem, OrderEvent, PaymentEvent, StockMovement, Variant


class StockError(ValueError):
    pass


@transaction.atomic
def reserve_order(cart, mode):
    if not cart or len(cart) > 100:
        raise StockError('Your bag is empty or too large.')
    try:
        ids = sorted(int(k) for k in cart)
    except (TypeError, ValueError):
        raise StockError('Your bag contains an invalid item.')
    variants = list(Variant.objects.select_for_update(of=('self',)).select_related('product').filter(pk__in=ids).order_by('pk'))
    if len(variants) != len(cart):
        raise StockError('A product is no longer available.')
    subtotal = 0
    for variant in variants:
        quantity = cart[str(variant.pk)]
        if type(quantity) is not int or not 1 <= quantity <= min(9, variant.stock) or not variant.active or not variant.product.published:
            raise StockError('Stock changed. Please review your bag before checking out.')
        subtotal += quantity * variant.price
    shipping = 0 if subtotal >= 7500 else 600
    order = Order.objects.create(mode=mode, subtotal=subtotal, shipping=shipping, total=subtotal + shipping,
                                 expires_at=timezone.now() + timedelta(minutes=35))
    for variant in variants:
        quantity = cart[str(variant.pk)]
        OrderItem.objects.create(order=order, variant=variant, product_name=variant.product.name,
                                 sku=variant.sku, size=variant.size, style=variant.style,
                                 unit_price=variant.price, quantity=quantity)
        variant.stock -= quantity
        variant.save(update_fields=['stock'])
        StockMovement.objects.create(variant=variant, order=order, delta=-quantity, reason='Checkout reservation')
    OrderEvent.objects.create(order=order, message='Test order created; stock reserved for 35 minutes.')
    return order


@transaction.atomic
def release_order(order_id, status=Order.Status.CANCELLED, actor=None):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PENDING:
        return False
    items = list(order.items.order_by('variant_id'))
    variants = {v.pk: v for v in Variant.objects.select_for_update().filter(pk__in=[i.variant_id for i in items]).order_by('pk')}
    for item in items:
        variant = variants[item.variant_id]
        variant.stock += item.quantity
        variant.save(update_fields=['stock'])
        StockMovement.objects.create(variant=variant, order=order, delta=item.quantity, reason='Reservation released', actor=actor)
    order.status = status
    order.save(update_fields=['status'])
    OrderEvent.objects.create(order=order, actor=actor, message=f'Order {status}; reserved stock restored.')
    return True


@transaction.atomic
def mark_paid(order_id, session=None):
    order = Order.objects.select_for_update().get(pk=order_id)
    if session is not None:
        if (order.mode != 'stripe_test' or session.get('livemode') is not False or
            session.get('id') != order.stripe_session_id or session.get('client_reference_id') != str(order.pk) or
            session.get('amount_total') != order.total or session.get('currency') != order.currency or
            session.get('payment_status') != 'paid'):
            raise ValueError('Payment does not match the stored order.')
    elif order.mode != 'simulated':
        raise ValueError('Stripe orders require a verified payment.')
    if order.status in (Order.Status.PAID, Order.Status.SHIPPED):
        return order
    if order.status != Order.Status.PENDING:
        raise ValueError('Payment arrived after reservation release. Manual reconciliation required.')
    order.status = Order.Status.PAID
    order.paid_at = timezone.now()
    if session is not None:
        details = session.get('customer_details') or {}
        order.email = details.get('email') or ''
        order.shipping_details = (session.get('collected_information') or {}).get('shipping_details') or session.get('shipping_details') or {}
    order.save(update_fields=['status', 'paid_at', 'email', 'shipping_details'])
    OrderEvent.objects.create(order=order, message='Test payment verified (simulated for demo orders); no live charge.')
    return order


@transaction.atomic
def handle_payment_event(event):
    session = event['data']['object']
    try:
        order_id = UUID(session.get('client_reference_id', ''))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Invalid order reference.') from exc
    order = Order.objects.select_for_update().get(pk=order_id, mode='stripe_test')
    if (session.get('livemode') is not False or session.get('amount_total') != order.total or
        session.get('currency') != order.currency or not session.get('id')):
        raise ValueError('Payment event does not match the saved order.')
    if order.stripe_session_id is None:
        # Verified webhooks may arrive before the API response, including when
        # that response times out. The signed order reference repairs the link.
        order.stripe_session_id = session['id']
        order.save(update_fields=['stripe_session_id'])
    elif order.stripe_session_id != session['id']:
        raise ValueError('Unexpected checkout session for this order.')
    if PaymentEvent.objects.filter(event_id=event['id']).exists():
        return
    kind = event['type']
    if kind in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
        mark_paid(order.pk, session)
    elif kind in ('checkout.session.expired', 'checkout.session.async_payment_failed'):
        if session.get('livemode') is not False or session.get('client_reference_id') != str(order.pk):
            raise ValueError('Invalid payment event.')
        release_order(order.pk, Order.Status.EXPIRED)
    PaymentEvent.objects.create(event_id=event['id'], order=order, kind=kind)


@transaction.atomic
def ship_order(order_id, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PAID:
        raise ValueError('Only paid test orders can be marked shipped.')
    order.status = Order.Status.SHIPPED
    order.save(update_fields=['status'])
    OrderEvent.objects.create(order=order, actor=actor, message=f'Marked shipped (test). Tracking: {order.tracking_number or "not supplied"}')
