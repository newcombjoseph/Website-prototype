"""Render the Django templates into an explicitly labeled, browser-local preview.

This is not a Python-server deployment. Do not claim the Sites URL runs Django.
"""
import os
import secrets
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ.setdefault('DJANGO_SECRET_KEY', secrets.token_urlsafe(64))
import django
django.setup()
from django.template.loader import render_to_string
from shop.catalog import PRODUCTS, cart_summary

root = Path(__file__).resolve().parents[1]
dist = root / 'dist'
if dist.exists():
    shutil.rmtree(dist)
dist.mkdir()
context = {'preview': True, 'catalog_data': PRODUCTS, 'checkout_mode': 'simulated', 'bag': cart_summary({})}
pages = [('', 'home', 'home', {'products': PRODUCTS[:4]}),
         ('shop', 'catalog', 'catalog', {'products': PRODUCTS}),
         ('cart', 'cart', 'cart', {}), ('checkout', 'checkout', 'checkout', {}),
         ('checkout/complete', 'complete', 'complete', {}),
         ('checkout/cancel', 'cancel', 'cancel', {}),
         ('about', 'info', 'about', {'info': 'about'}),
         ('shipping', 'info', 'shipping', {'info': 'shipping'})]
pages += [(f'products/{p["slug"]}', 'product', 'product', {'product': p, 'products': [q for q in PRODUCTS if q != p][:3]}) for p in PRODUCTS]
for path, template, page, extra in pages:
    output = dist / path / 'index.html'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_to_string(f'shop/{template}.html', {**context, 'page': page, **extra}))
shutil.copytree(root / 'staticfiles', dist / 'static')
(dist / 'robots.txt').write_text('User-agent: *\nDisallow: /\n')
(dist / '_headers').write_text('''/*
  X-Robots-Tag: noindex, nofollow, noarchive
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: same-origin
  Cache-Control: no-store
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
''')
print(f'Rendered {len(pages)} Django-template pages into {dist}. Interactive preview only.')
