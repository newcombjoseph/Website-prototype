from django.conf import settings
from .catalog import cart_summary, product_cards

def store(request):
    return {'bag': cart_summary(request.session.get('cart', {})), 'catalog_data': product_cards(),
            'checkout_mode': settings.CHECKOUT_MODE, 'preview': False}
