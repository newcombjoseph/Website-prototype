"""Additional gates for an actual production deployment (APP_ENV=production)."""
import os
from django.conf import settings
from django.core.checks import Error, Tags, register

@register(Tags.security, deploy=True)
def production_checks(app_configs, **kwargs):
    if os.environ.get('APP_ENV') != 'production':
        return []
    errors = []
    def require(condition, message, code):
        if not condition:
            errors.append(Error(message, id=f'shop.{code}'))
    db = settings.DATABASES['default']
    require(not settings.DEBUG, 'Production requires DJANGO_DEBUG=false.', 'E001')
    require(db['ENGINE'] == 'django.db.backends.postgresql', 'Production requires PostgreSQL DATABASE_URL.', 'E002')
    require(bool(settings.AWS_STORAGE_BUCKET_NAME), 'Production requires persistent S3 upload storage.', 'E003')
    if '.rds.amazonaws.com' in str(db.get('HOST', '')):
        options = db.get('OPTIONS', {})
        require(options.get('sslmode') == 'verify-full' and bool(options.get('sslrootcert')), 'RDS requires sslmode=verify-full and the AWS RDS CA bundle in sslrootcert.', 'E004')
    if settings.CHECKOUT_MODE == 'stripe_test':
        require(bool(settings.STRIPE_WEBHOOK_SECRET), 'Stripe checkout requires STRIPE_WEBHOOK_SECRET.', 'E005')
    require(settings.PUBLIC_ORIGIN.startswith('https://'), 'Production requires an HTTPS PUBLIC_ORIGIN.', 'E006')
    require(settings.ALLOWED_HOSTS and '*' not in settings.ALLOWED_HOSTS, 'Set explicit production DJANGO_ALLOWED_HOSTS.', 'E007')
    if settings.PRIVATE_ACCESS_REQUIRED:
        require(bool(settings.PRIVATE_USERNAME and settings.PRIVATE_PASSWORD_HASH), 'Configure the private preview gate or explicitly disable it for a public storefront.', 'E008')
    return errors
