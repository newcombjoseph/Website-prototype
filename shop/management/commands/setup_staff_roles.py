from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Create additive catalog and order staff groups; users and MFA are provisioned separately.'
    def handle(self, *args, **kwargs):
        catalog, _ = Group.objects.get_or_create(name='Catalog and inventory staff')
        orders, _ = Group.objects.get_or_create(name='Order staff')
        catalog.permissions.add(*Permission.objects.filter(content_type__app_label='shop', codename__in=[
            'view_product', 'add_product', 'change_product', 'view_variant', 'add_variant', 'change_variant',
            'view_productimage', 'add_productimage', 'change_productimage', 'delete_productimage', 'view_stockmovement']))
        orders.permissions.add(*Permission.objects.filter(content_type__app_label='shop', codename__in=[
            'view_order', 'change_order', 'view_orderitem', 'view_orderevent', 'view_paymentevent']))
        self.stdout.write('Staff groups configured; assign only the permissions each person needs.')
