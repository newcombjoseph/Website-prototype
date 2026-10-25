"""Store records. Money is stored as integer USD cents, never binary floats."""
import uuid
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(unique=True)
    category = models.CharField(max_length=80, default='Healthcare bonnets')
    description = models.TextField()
    materials = models.TextField(blank=True)
    dimensions = models.CharField(max_length=200, blank=True)
    care = models.TextField(blank=True)
    note = models.CharField(max_length=200, blank=True)
    badge = models.CharField(max_length=80, blank=True)
    published = models.BooleanField(default=False, help_text='Only published products with active variants appear in the shop.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='variants')
    sku = models.CharField('SKU', max_length=80, unique=True)
    size = models.CharField(max_length=50)
    style = models.CharField(max_length=80)
    price = models.PositiveIntegerField('Price (USD cents)', validators=[MinValueValidator(1)], help_text='2500 means $25.00. Use the dollar price field in the admin.')
    stock = models.PositiveIntegerField('Available stock', default=0, help_text='Units available to sell; reserved orders have already been deducted.')
    low_stock_threshold = models.PositiveIntegerField(default=5)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['product_id', 'id']
        verbose_name = 'inventory variant'
        verbose_name_plural = 'Inventory (sizes and styles)'
        constraints = [models.UniqueConstraint(fields=['product', 'size', 'style'], name='unique_product_size_style'),
                       models.CheckConstraint(condition=models.Q(price__gt=0), name='positive_variant_price')]

    def __str__(self):
        return f'{self.product.name} / {self.size} / {self.style} ({self.sku})'


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/%Y/%m/', help_text='JPEG, PNG or WebP; up to 8 MB. Images are resized and metadata removed.')
    alt_text = models.CharField(max_length=200, help_text='Describe the bonnet for customers using screen readers.')
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return self.alt_text


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Awaiting test payment'
        PAID = 'paid', 'Test payment received'
        SHIPPED = 'shipped', 'Marked shipped (test)'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    mode = models.CharField(max_length=16, choices=[('simulated', 'Simulated'), ('stripe_test', 'Stripe test')])
    email = models.EmailField(blank=True)
    shipping_details = models.JSONField(default=dict, blank=True)
    subtotal = models.PositiveIntegerField()
    shipping = models.PositiveIntegerField()
    total = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default='usd')
    stripe_session_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(condition=models.Q(total=models.F('subtotal') + models.F('shipping')), name='order_total_matches')]

    def __str__(self):
        return f'{str(self.pk)[:8]} — {self.get_status_display()}'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='items')
    variant = models.ForeignKey(Variant, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=160)
    sku = models.CharField(max_length=80)
    size = models.CharField(max_length=50)
    style = models.CharField(max_length=80)
    unit_price = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name='positive_order_quantity')]

    def __str__(self):
        return f'{self.product_name} / {self.size} / {self.style} × {self.quantity}'


class OrderEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='history')
    message = models.CharField(max_length=255)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return self.message


class StockMovement(models.Model):
    variant = models.ForeignKey(Variant, on_delete=models.PROTECT, related_name='movements')
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.PROTECT)
    delta = models.IntegerField()
    reason = models.CharField(max_length=255)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return f'{self.variant.sku}: {self.delta:+d} ({self.reason})'


class PaymentEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    order = models.ForeignKey(Order, on_delete=models.PROTECT)
    kind = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)
