# Validation — October 25, 2026

The commerce/admin change was checked in the cloud workspace with Python 3.12.14 and an actual PostgreSQL 16 container.

- `python scripts/verify.py`: **32 tests passed**, no skipped tests. Static collection and `check --deploy --fail-level WARNING` passed.
- Existing browsing, cart, CSRF, HTTPS, private access and test checkout checks remain covered.
- New checks cover size/style inventory isolation, immutable order snapshots, reservation rollback/release, last-unit concurrent purchases on PostgreSQL, duplicate/mismatched/expired payment notifications, actual HMAC signature verification, lost API-response/session-link recovery, MFA login, one-time recovery codes, login rate limits, staff permissions, read-only financial records, audited stock changes, stale admin forms, image validation/re-encoding and production configuration gates.
- `python manage.py makemigrations --check --dry-run`: no pending model changes. Initial schema and follow-up admin-label migration applied successfully to the development database.
- `python -m pip check`: dependencies compatible.
- Running Django HTTP smoke: home, product options, admin login and static admin CSS returned expected content. CSRF-protected simulated checkout persisted a paid test order, history and stock deduction.
- Static export: 16 original illustrative sample pages rendered. This is not the database-backed running application.

The production Docker image built successfully. A non-root, read-only container passed startup deployment checks and HTTP smoke requests for the storefront, admin login and admin static CSS against the local PostgreSQL fixture. S3 configuration was a placeholder for this smoke check; no AWS media operation was claimed. Its optional build CA secret supports trusted enterprise proxies without disabling TLS verification.

These checks do not establish AWS deployment readiness. RDS/S3/IAM/HTTPS provisioning, actual uploaded-media persistence on S3, real Stripe sandbox delivery, production networking, encrypted backups/restores, monitoring and business launch requirements remain to be verified on the chosen AWS resources. Live payments, refunds and real shipping/tax/email workflows remain disabled or unfinished. See `deploy/AWS.md`.


## Repeatable local PostgreSQL setup

The follow-up `scripts/local.py` helper was executed against the actual Compose PostgreSQL 16 service with authenticated connections on loopback port 15432. Fresh setup applied both shop migrations and created the original catalog, six unpublished bonnet variants, and staff groups. A sample simulated paid order was saved for verification.

Two subsequent setup runs preserved an edited price and stock count, the order, line items, order events, stock movements, staff groups, and the exact saved local settings file. No database volumes were deleted and no passwords were reset. The helper's saved-settings startup returned expected storefront, product-option and MFA login content over HTTP.

`python scripts/local.py test` passed **38 tests**, with no skips, including secret-file preservation, special-character database passwords, failed-authentication handling, and isolation from inherited production settings. `.local/development.json` is ignored by Git and excluded from Docker build context. The Python helper was exercised on the Linux cloud machine; native Windows Docker Desktop execution remains a user-side check.
