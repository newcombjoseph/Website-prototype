from decimal import Decimal
from django import forms
from django.core import signing
from django.contrib import admin, messages
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.db import transaction
from django.db.models import F
from django.utils.html import format_html
from django.utils import timezone
from django_otp.admin import OTPAdminSite
from .images import prepare_image
from .models import Product, Variant, ProductImage, Order, OrderItem, OrderEvent, StockMovement, PaymentEvent
from .services import release_order, ship_order

site = OTPAdminSite(name='store_admin')
site.site_header = 'Bonnet store management'
site.site_title = 'Store management'
site.index_title = 'Products, inventory and orders'
class StaffAccountAdmin(UserAdmin):
    def has_delete_permission(self, request, obj=None):
        return False  # Deactivate accounts to preserve actor identity in audit history.

site.register(User, StaffAccountAdmin)
site.register(Group, GroupAdmin)


class VariantForm(forms.ModelForm):
    dollar_price = forms.DecimalField(label='Price ($ USD)', min_value=Decimal('0.01'), max_value=Decimal('100000.00'), decimal_places=2, help_text='For example, 24.99.')
    stock_snapshot = forms.CharField(required=False, widget=forms.HiddenInput)
    adjustment_reason = forms.CharField(required=False, label='Reason for stock change', help_text='Required when changing existing stock, e.g. delivery received or damaged item.')

    class Meta:
        model = Variant
        exclude = ['price']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(deleted_at__isnull=True)
        if self.instance.pk:
            self.fields['dollar_price'].initial = Decimal(self.instance.price) / 100
            self.fields['stock_snapshot'].initial = signing.dumps({'id': self.instance.pk, 'stock': self.instance.stock}, salt='admin-stock')

    def clean(self):
        data = super().clean()
        if data.get('dollar_price') is not None:
            self.instance.price = int(data['dollar_price'] * 100)
        if self.instance.pk and 'stock' in self.changed_data and not data.get('adjustment_reason', '').strip():
            self.add_error('adjustment_reason', 'Please explain this stock adjustment.')
        if self.instance.pk and 'stock' in self.changed_data:
            try:
                snapshot = signing.loads(data.get('stock_snapshot', ''), salt='admin-stock', max_age=86400)
                current = Variant.objects.select_for_update().get(pk=self.instance.pk)
                if snapshot != {'id': current.pk, 'stock': current.stock}:
                    self.add_error('stock', 'Stock changed while editing. Reload this page before changing stock.')
            except signing.BadSignature:
                self.add_error('stock', 'Reload this page before changing stock.')
        return data


class ImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = '__all__'

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and 'image' in self.changed_data:
            return prepare_image(image)
        return image


class ImageInline(admin.TabularInline):
    model = ProductImage
    form = ImageForm
    extra = 1
    fields = ['image', 'alt_text', 'position', 'thumbnail']
    readonly_fields = ['thumbnail']

    @admin.display(description='Picture')
    def thumbnail(self, obj):
        return format_html('<img src="{}" alt="{}" width="80" height="80">', obj.image.url, obj.alt_text) if obj.image else 'Save to see picture'


@admin.register(Product, site=site)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'published', 'updated_at']
    list_filter = ['published', 'category']
    search_fields = ['name', 'description', 'variants__sku']
    prepopulated_fields = {'slug': ['name']}
    inlines = [ImageInline]
    fieldsets = [('Product information', {'fields': ('name', 'slug', 'category', 'description', 'published')}),
                 ('Details for customers', {'fields': ('materials', 'dimensions', 'care', 'badge', 'note')})]

    delete_confirmation_template = 'admin/shop/product/delete_confirmation.html'
    delete_selected_confirmation_template = 'admin/shop/product/delete_selected_confirmation.html'

    def get_queryset(self, request):
        return super().get_queryset(request).filter(deleted_at__isnull=True)

    def get_deleted_objects(self, objs, request):
        # The admin deletes active catalog entries, not historical database rows.
        # Related variants/orders/movements must not be presented as cascades.
        objects = list(objs)
        return [str(obj) for obj in objects], {str(self.opts.verbose_name_plural): len(objects)}, set(), []

    def delete_model(self, request, obj):
        self.delete_queryset(request, Product.objects.filter(pk=obj.pk))

    def delete_queryset(self, request, queryset):
        now = timezone.now()
        queryset.filter(deleted_at__isnull=True).update(deleted_at=now, published=False, updated_at=now)

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        # A form opened before deletion must never clear a later deletion marker.
        current = Product.objects.select_for_update().get(pk=obj.pk)
        if current.deleted_at is not None:
            obj.published = False
        obj.updated_at = timezone.now()
        obj.save(update_fields=[*form.fields, 'updated_at'])


class LowStockFilter(admin.SimpleListFilter):
    title = 'stock level'
    parameter_name = 'stock_level'
    def lookups(self, request, model_admin):
        return [('low', 'Low stock'), ('out', 'Out of stock')]
    def queryset(self, request, queryset):
        if self.value() == 'low':
            return queryset.filter(stock__lte=F('low_stock_threshold'))
        if self.value() == 'out':
            return queryset.filter(stock=0)
        return queryset


@admin.register(Variant, site=site)
class VariantAdmin(admin.ModelAdmin):
    form = VariantForm
    list_display = ['sku', 'product', 'size', 'style', 'price_display', 'stock', 'active']
    list_filter = [LowStockFilter, 'active', 'size', 'style']
    search_fields = ['sku', 'product__name', 'size', 'style']
    autocomplete_fields = ['product']
    readonly_fields = ['stock_history']
    fields = ['product', 'sku', 'size', 'style', 'dollar_price', 'active', 'stock', 'stock_snapshot', 'adjustment_reason', 'low_stock_threshold', 'stock_history']

    @admin.display(description='Price')
    def price_display(self, obj):
        return f'${obj.price / 100:.2f}'

    @admin.display(description='Recent stock changes')
    def stock_history(self, obj):
        if not obj.pk:
            return 'Save the variant to begin stock history.'
        return format_html('<pre>{}</pre>', '\n'.join(f'{m.created_at:%Y-%m-%d %H:%M} {m.delta:+d}: {m.reason} ({m.actor or "system"})' for m in obj.movements.select_related('actor')[:20]))

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        old = Variant.objects.select_for_update().get(pk=obj.pk) if change else None
        # ModelForm holds values loaded before the transaction. Never overwrite stock
        # from a stale form after a concurrent checkout.
        if old and 'stock' not in form.changed_data:
            obj.stock = old.stock
        super().save_model(request, obj, form, change)
        delta = obj.stock - (old.stock if old else 0)
        if delta:
            StockMovement.objects.create(variant=obj, delta=delta, actor=request.user,
                                         reason=form.cleaned_data.get('adjustment_reason') or 'Initial stock')

    def get_queryset(self, request):
        return super().get_queryset(request).filter(product__deleted_at__isnull=True)

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields if f.name != 'id']


class ItemInline(ReadOnlyInline):
    model = OrderItem

class HistoryInline(ReadOnlyInline):
    model = OrderEvent


@admin.register(Order, site=site)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at', 'status', 'mode', 'email', 'total_dollars']
    list_filter = ['status', 'mode', 'created_at']
    search_fields = ['id', 'email', 'stripe_session_id', 'tracking_number', 'items__sku']
    inlines = [ItemInline, HistoryInline]
    actions = ['mark_shipped', 'cancel_pending']
    readonly_fields = [f.name for f in Order._meta.fields if f.name != 'tracking_number']

    @admin.display(description='Total USD')
    def total_dollars(self, obj):
        return f'${obj.total / 100:.2f}'

    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        # Restrict UPDATE to the editable field so a stale admin page cannot roll
        # a paid order back to pending or overwrite webhook customer details.
        obj.save(update_fields=['tracking_number'])
        if form.changed_data:
            OrderEvent.objects.create(order=obj, actor=request.user, message='Tracking number updated.')

    @admin.action(description='Mark selected paid test orders shipped', permissions=['change'])
    def mark_shipped(self, request, queryset):
        for obj in queryset:
            try:
                ship_order(obj.pk, request.user)
            except ValueError as exc:
                self.message_user(request, str(exc), messages.WARNING)

    @admin.action(description='Cancel selected unpaid orders and restore stock', permissions=['change'])
    def cancel_pending(self, request, queryset):
        for obj in queryset:
            # Stripe reservations must be released by verified expiry notifications;
            # cancellation in the provider is required before stock can be resold.
            if obj.mode == 'stripe_test':
                self.message_user(request, 'Expire Stripe sessions in Stripe first; their verified webhook releases stock.', messages.WARNING)
            else:
                release_order(obj.pk, actor=request.user)


for model, columns, search in [
    (OrderItem, ('product_name', 'sku', 'size', 'style', 'quantity', 'unit_price', 'order'), ('sku', 'product_name')),
    (OrderEvent, ('created_at', 'order', 'message', 'actor'), ('message',)),
    (StockMovement, ('created_at', 'variant', 'delta', 'reason', 'actor', 'order'), ('variant__sku', 'reason')),
    (PaymentEvent, ('event_id', 'kind', 'order', 'created_at'), ('event_id',)),
]:
    site.register(model, type(f'{model.__name__}Admin', (ReadOnlyAdmin,), {
        'list_display': columns, 'search_fields': search,
    }))
