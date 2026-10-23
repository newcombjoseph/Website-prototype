from django.conf import settings
from .catalog import cart_summary, PRODUCTS

def store(request):
    return {'bag': cart_summary(request.session.get('cart', {})), 'catalog_data': PRODUCTS,
            'checkout_mode': settings.CHECKOUT_MODE, 'preview': False}
