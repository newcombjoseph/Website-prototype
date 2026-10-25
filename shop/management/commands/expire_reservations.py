from django.core.management.base import BaseCommand
from django.utils import timezone
from shop.models import Order
from shop.services import release_order

class Command(BaseCommand):
    help = 'Release expired simulated reservations. Stripe stock is released ONLY by verified provider expiry/failure events.'
    def handle(self, *args, **options):
        count = 0
        for pk in Order.objects.filter(mode='simulated', status='pending', expires_at__lte=timezone.now()).values_list('pk', flat=True):
            count += bool(release_order(pk, Order.Status.EXPIRED))
        self.stdout.write(f'Released {count} simulated reservations. Monitor pending Stripe orders and webhook delivery separately.')
