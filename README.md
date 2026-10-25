# Fieldform — bonnet store management prototype

Django storefront with PostgreSQL-backed products, size/style variants, inventory, test orders and order history, plus an MFA-protected staff admin at `/admin/`. Existing placeholder catalog styling is retained; sample healthcare bonnets are seeded as drafts for you to customize.

**Start here:** [Windows setup](docs/WINDOWS_SETUP.md) · [Store admin guide](docs/STORE_ADMIN.md) · [AWS deployment](deploy/AWS.md)

## Local database setup (Windows, macOS and Linux)

Use Python 3.12, Docker Desktop/Linux Docker and a virtual environment with `requirements.txt` installed. From the project folder, using that environment's Python:

```bash
python scripts/local.py setup
python scripts/local.py run
```

First setup asks for the existing database password (or reuses POSTGRES_PASSWORD), starts PostgreSQL on loopback port **15432**, applies all migrations, seeds the sample catalog, and creates staff groups. Existing products, prices, stock, orders and accounts are preserved. It saves private development settings in ignored `.local/development.json`, so later startup needs just `python scripts/local.py run`. Do not commit or share that file. This helper creates a local development database, never AWS resources or a production database.

For a new admin account only:

```bash
python scripts/local.py manage createsuperuser
python scripts/local.py manage enroll_admin YOUR_USERNAME
```

Use individual staff accounts, strong passwords and authenticator codes. No default accounts or credentials are included. Never share the private authenticator setup URI or recovery codes. Existing accounts/MFA are preserved by setup. See the [Windows guide](docs/WINDOWS_SETUP.md) for pulling updates after editing your local Compose port.

Uploads use local `media/` in development and private S3 in production. Django does not load `.env` or `.local/development.json` on its own; use the helper's `manage` command or explicitly configure environment variables for manual commands.

## Verification

Using the saved local settings, run `python scripts/local.py test`. For manual verification, use a fresh shell with DATABASE_URL and a temporary random secret, without HTTP-development overrides:

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
