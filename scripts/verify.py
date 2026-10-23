import os
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ.setdefault('DJANGO_SECRET_KEY', secrets.token_urlsafe(64))
os.environ.setdefault('DJANGO_ALLOWED_HOSTS', 'testserver,localhost,127.0.0.1')
import django
django.setup()
from django.core.management import call_command

call_command('collectstatic', interactive=False, clear=True, verbosity=0)
call_command('check', deploy=True, fail_level='WARNING')
call_command('test', 'tests', verbosity=2)
