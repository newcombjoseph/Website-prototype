# AWS deployment runbook — resources are not provisioned

This release adds the database and staff management backend. It is not deployed to AWS, does not enable live payments, and does not by itself establish production readiness. No AWS account changes, purchases or public exposure are performed by the repository.

## Architecture

Use an existing approved compute environment running the Docker image (EC2 with the provided Caddy configuration, or ECS behind an HTTPS load balancer), **RDS PostgreSQL 16+**, and a **private S3 bucket** for uploaded product pictures. Keep RDS private: its security group permits port 5432 only from the application's security group. Do not expose RDS to the Internet. Use an application-specific database role with only the necessary schema permissions; run migrations with a separate release role. Do not grant the web process database-owner or CREATE DATABASE privileges.

RDS and S3 add cost beyond the previous private static/demo architecture. Select instance size, backup retention, availability and budget alerts for the actual business before provisioning. No price estimate here has been verified against your account or region.

## Configuration and secrets

Inject secrets from AWS Secrets Manager/Parameter Store or the approved host environment; never bake them into the image. Use `.env.example` as a list of requirements, not as usable production values. Docker Compose reads `.env`; Django itself does not.

- `APP_ENV=production`, `DJANGO_DEBUG=false`.
- `DJANGO_SECRET_KEY`: stable high-entropy secret of at least 50 characters.
- `DATABASE_URL`: RDS connection URL with URL-encoded password, `sslmode=verify-full` and `sslrootcert=/run/rds/global-bundle.pem`. Download the current AWS RDS CA bundle from `https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem` over verified HTTPS on your deployment machine. Set `RDS_CA_BUNDLE_PATH` to its absolute host path; Compose mounts it read-only at `/run/rds/global-bundle.pem`. ECS deployments must mount the same public bundle at that path. Renew it as AWS rotates certificates. A typical URL is `postgresql://app:ENCODED_PASSWORD@DB_HOST:5432/bonnets?sslmode=verify-full&sslrootcert=/run/rds/global-bundle.pem`.
- `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`: private S3 media bucket and its region. Enable Block Public Access, encryption and versioning. Use an EC2 instance profile or ECS task role with ListBucket on this bucket and GetObject/PutObject/DeleteObject only under `products/*`. Do not embed access keys. If using SSE-KMS, include scoped KMS permissions.
- Product images are public catalog content exposed using short-lived signed S3 URLs. Do not upload patient/customer documents. Credentials and customer data are never exposed through these image URLs. Keep the bucket private and require TLS in its bucket policy. CSP permits only that bucket's regional/default S3 image hostnames.
- Set explicit HTTPS `PUBLIC_ORIGIN`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`. Set `TRUST_HTTPS_PROXY=true` only when a trusted proxy overwrites the forwarded protocol header and direct app access is blocked.
- Keep `PRIVATE_ACCESS_REQUIRED=true` and configure the owner credentials for a private preview. Set false explicitly when you approve public storefront access. Admin still requires account authentication plus MFA. The exact `/payments/stripe/webhook/` route bypasses the private gate because Stripe cannot use owner credentials; cryptographic signature verification is mandatory there.
- For Stripe sandbox: `CHECKOUT_MODE=stripe_test`, `STRIPE_SECRET_KEY` (test key only), and `STRIPE_WEBHOOK_SECRET`. Default `simulated` does not call Stripe.

## Release

1. Back up the existing database and record its restore point before migrations. Build the image. Configure RDS, private S3, role credentials, networking, HTTPS and secrets on the authorized AWS resources.
2. Run `python manage.py migrate --noinput` once as a release job. Do not run concurrent migrations from web workers.
3. Optionally run `python manage.py seed_store` to add the eight sample scrub cap styles with three sizes each and archive untouched household placeholders. It is repeatable and preserves edited products, inventory and order history. For healthcare bonnet samples run `python manage.py seed_store --bonnets`; these six combinations are unpublished and have zero stock. Do not use samples as real inventory.
4. Run `python manage.py setup_staff_roles`, `python manage.py createsuperuser`, then `python manage.py enroll_admin USERNAME` from a trusted interactive terminal (for Compose use `docker compose --env-file .env -f deploy/compose.yaml exec django ...` after the server starts). Protect the authenticator enrollment URI and recovery codes; never route their output into centralized logs. Create individual staff users, assign the least-privilege groups, and enroll each through that trusted command. Accounts without enrolled MFA cannot use admin.
5. Start the web service. The production container executes `check --deploy --fail-level WARNING` before starting Gunicorn. With `APP_ENV=production`, additional checks reject SQLite, missing S3 storage, insecure RDS certificate settings, missing webhook secrets for Stripe checkout, and an unconfigured private gate. These checks supplement actual AWS validation.
6. If using the included EC2 Compose/Caddy setup, run `docker compose --env-file .env -f deploy/compose.yaml up -d --build`. Only Caddy exposes ports 80/443; Gunicorn is internal. Configure AWS firewalls accordingly. The supplied application container remains read-only; uploads go to S3, sessions and business records to RDS.
7. Schedule `python manage.py expire_reservations` every minute (EventBridge task, cron, or a scheduled container using the same DB/settings). It releases only expired **simulated** reservations. Stripe reservations are released only from verified provider expiry/failure events; releasing on a local timer alone could oversell after a paid-but-delayed notification.
8. Schedule Django `clearsessions` and define access-log retention in line with your security/audit policy. Check installed Axes housekeeping command options before deleting old records. Do not delete business history or access failures needed for an investigation.

For a build behind an enterprise TLS inspection proxy, pass its trusted public CA bundle with `docker build --secret id=build_ca_bundle,src=/path/to/trusted-ca-bundle.pem .` and configure the proxy through standard Docker build arguments. The CA is mounted only for the dependency/certificate download steps and is not baked into the runtime image. Never disable TLS verification.

## Stripe test integration and reservations

Register `https://YOUR_HOST/payments/stripe/webhook/` in Stripe's sandbox with these event types: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`, `checkout.session.async_payment_failed`. Use the endpoint's signing secret. Test signed real sandbox delivery; mocked tests do not prove the deployed integration.

A pending order snapshots its item descriptions and integer-cent prices, atomically subtracts available variant stock, and reserves it for a 35-minute checkout window. Checkout retries reuse the same order and Stripe idempotency key. Card payments are the only enabled method. Verified notifications validate the order ID, session ID, currency, amount and test mode. Event IDs are unique; repeated notifications do not charge or reduce stock again. The browser return cannot mark Stripe orders paid.

Monitor aging pending orders and webhook errors. Signature-verified events can link the session to the immutable order UUID even if the create-session response was lost. Stripe reservations are not released by the local expiry job. Failed webhook delivery can still hold stock: inspect Stripe using the order UUID/idempotency key, link/replay the verified event as appropriate, and only release after establishing payment cannot complete. Late paid events after a released reservation fail visibly for manual reconciliation rather than overselling. Subscribe only the relevant Stripe account's sessions to this endpoint. Live mode is rejected.

## Mandatory deployment verification

- On the actual host run deployment checks and migration checks. Confirm RDS connection TLS hostname verification and no direct external database/app-container access.
- Test admin access with no session, password only, valid MFA, invalid MFA, used recovery codes, disabled users and staff permissions. Confirm HTTPS, secure cookies, CSRF rejection and rate limits; configure edge/WAF login limits too. Account-wide and IP-wide login lockouts use database-backed Axes. Set proxy/IP handling deliberately before changing defaults.
- Create a real draft bonnet, upload a picture, add sizes/styles, publish and confirm correct image/price/stock. Restart/redeploy and confirm persistence. Test that simultaneous attempts at the last unit reserve it once.
- Complete a Stripe sandbox purchase, close the browser before return, and verify the webhook still updates the saved order. Exercise duplicate events, invalid signatures, wrong amounts, abandoned checkout expiry, delayed notifications and provider failure. Verify no financial fields can be manually rewritten in admin.
- Enable encrypted RDS automated backups/point-in-time recovery and S3 versioning/lifecycle policies. Restore the DB to a separate instance and restore a media object; record timings and recovery procedures. Restrict IAM permissions for deleting audit history/backups.
- Configure alerts for HTTP errors, webhook failures, aging reservations, database capacity and backup failures. Avoid logging payment payloads, auth headers, tokens, addresses or secret values. Keep OS/dependencies patched. Choose order/customer retention policies and restrict personal-data access to order staff.

Refunds, live payments, customer emails, real shipping/tax policies and public launch remain separate work. This implementation has no refund button that could falsely claim to return money. Historical orders are read-only except tracking and controlled status transitions. Do not enable real sales until those remaining business flows and AWS deployment checks are complete.
