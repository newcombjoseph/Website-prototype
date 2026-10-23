import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get('DJANGO_DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('Set DJANGO_SECRET_KEY to a random value of at least 50 characters.')
ALLOWED_HOSTS = [x.strip() for x in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if x.strip()]
INSTALLED_APPS = ['django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.staticfiles', 'shop']
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'shop.middleware.PrivateAccessMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'shop.middleware.StoreHeadersMiddleware',
]
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True,
              'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'shop.context.store']}}]
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
# All products are immutable placeholder catalog records. No order or customer DB is created.
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 86400
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
# Enable only behind the shipped Caddy reverse proxy, which overwrites this header.
if os.environ.get('TRUST_HTTPS_PROXY', 'false').lower() == 'true':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
WHITENOISE_MANIFEST_STRICT = True
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
PRIVATE_ACCESS_REQUIRED = os.environ.get('PRIVATE_ACCESS_REQUIRED', 'true').lower() == 'true'
PRIVATE_USERNAME = os.environ.get('PRIVATE_USERNAME', '')
PRIVATE_PASSWORD_HASH = os.environ.get('PRIVATE_PASSWORD_HASH', '')
CHECKOUT_MODE = os.environ.get('CHECKOUT_MODE', 'simulated')
if CHECKOUT_MODE not in ('simulated', 'stripe_test'):
    raise ImproperlyConfigured('Only simulated and stripe_test checkout are allowed. Live payments are disabled.')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
if STRIPE_SECRET_KEY and not STRIPE_SECRET_KEY.startswith(('sk_test_', 'rk_test_')):
    raise ImproperlyConfigured('Only Stripe test credentials are accepted.')
if CHECKOUT_MODE == 'stripe_test' and not STRIPE_SECRET_KEY:
    raise ImproperlyConfigured('stripe_test requires a test API key.')
PUBLIC_ORIGIN = os.environ.get('PUBLIC_ORIGIN', 'https://localhost').rstrip('/')
if not DEBUG and not PUBLIC_ORIGIN.startswith('https://'):
    raise ImproperlyConfigured('PUBLIC_ORIGIN must use HTTPS.')
