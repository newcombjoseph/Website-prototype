# Fieldform — bonnet store management prototype

Django storefront with PostgreSQL-backed products, size/style variants, inventory, test orders and order history, plus an MFA-protected staff admin at `/admin/`. Existing placeholder catalog styling is retained; sample healthcare bonnets are seeded as drafts for you to customize.

**Start here:** [Windows setup](docs/WINDOWS_SETUP.md) · [Store admin guide](docs/STORE_ADMIN.md) · [AWS deployment](deploy/AWS.md)

## Development (macOS/Linux)

Use Python 3.12 and PostgreSQL 16+. Create a virtual environment, install `requirements.txt`, set `DATABASE_URL` and a random `DJANGO_SECRET_KEY` (50+ characters), and set these local-only settings:

```bash
export DJANGO_DEBUG=true
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
export PUBLIC_ORIGIN=http://localhost:8000
export PRIVATE_ACCESS_REQUIRED=false
export CHECKOUT_MODE=simulated
python manage.py migrate
python manage.py seed_store
python manage.py seed_store --bonnets
python manage.py setup_staff_roles
python manage.py createsuperuser
python manage.py enroll_admin YOUR_USERNAME
python manage.py runserver
```

Django does not automatically read `.env`. Docker Compose does. Uploads use local `media/` in development and private S3 in production. Database sessions replace the original cookie-only cart sessions; existing prototype carts need to be recreated after upgrade.

Use individual staff accounts, strong passwords and authenticator codes. No default accounts or credentials are included. The trusted-console enrollment command prints a private authenticator setup URI and one-time recovery codes; do not share or log them.

## Verification

In a fresh shell with DATABASE_URL and a temporary random secret, without HTTP-development overrides:

```bash
python scripts/verify.py
python manage.py makemigrations --check --dry-run
python -m pip check
```

Verification collects static files, checks deployment settings, and runs browsing/cart, admin/MFA/permissions, uploads, order snapshots, webhook and inventory tests. PostgreSQL is required to exercise the concurrent last-unit test. SQLite is a lightweight fallback only and is rejected when `APP_ENV=production` deployment checks run.

Optional `python scripts/export_preview.py` renders the original immutable sample collection into 16 static HTML pages after static collection. It is an illustrative browser-local preview, not the live store, admin, database or order system.

## Current boundaries

Checkout supports simulated and Stripe **test** modes only. Orders and inventory are durable, payment notifications are signature-verified and idempotent, and historical financial records are read-only in admin. Original prices, demo shipping ($6 below $75) and zero tax remain illustrative. Sample bonnet variants have zero stock until you add your real information. No patient/medical records are collected; this is a retail catalog for bonnets.

No AWS resources have been provisioned. Actual RDS/S3/IAM/HTTPS deployment, backups and restore, real Stripe sandbox delivery, and business requirements must be verified before production launch. Live payments, refunds, transactional email and real tax/shipping are not enabled by this release.
