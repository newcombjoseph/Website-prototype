# Windows development setup

Install Python 3.12, Git, and Docker Desktop (Linux containers). Start Docker Desktop. Open PowerShell in your existing project folder, pull the updated branch, then:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Save the generated local DB password in a password manager; reuse the same
# password for this Docker volume on subsequent runs. Do not regenerate it
# when reconnecting to an existing database.
$env:POSTGRES_PASSWORD = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(24))"
docker compose -f deploy/compose.local.yaml up -d --wait
$env:DATABASE_URL = "postgresql://bonnets:$($env:POSTGRES_PASSWORD)@127.0.0.1:5432/bonnets"
$env:DJANGO_SECRET_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
$env:DJANGO_DEBUG = "true"
$env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:PUBLIC_ORIGIN = "http://localhost:8000"
$env:PRIVATE_ACCESS_REQUIRED = "false"
$env:CHECKOUT_MODE = "simulated"

.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_store
.\.venv\Scripts\python.exe manage.py seed_store --bonnets
.\.venv\Scripts\python.exe manage.py setup_staff_roles
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py enroll_admin YOUR_USERNAME
.\.venv\Scripts\python.exe manage.py runserver
```

Enrollment displays a secret setup URI only in your trusted terminal. Add its secret to an authenticator app manually, enter the code when prompted, and store the one-time recovery codes offline. Never share the URI, secret or codes in chat or screenshots. No account has a default password.

Visit `http://localhost:8000` and `http://localhost:8000/admin/`. Stop Django with Ctrl+C. Stop PostgreSQL with `docker compose -f deploy/compose.local.yaml stop`. Keep the volume: it holds your data. Do not use `down -v` unless deliberately deleting that development data.

Django does not load `.env` automatically. New PowerShell windows need the environment variables again, using the existing DB password. Use a stable, securely stored Django secret if you want sessions to survive restarts. This example generates an ephemeral development secret only.

Run `python manage.py expire_reservations` periodically in development to release abandoned simulated checkouts (35 minutes). On Windows the complete command is `.\.venv\Scripts\python.exe manage.py expire_reservations`.

## Tests

Keep PostgreSQL running. Use a separate PowerShell window and set DATABASE_URL plus a temporary random DJANGO_SECRET_KEY as above, without the local HTTP development exports. Then run:

```powershell
.\.venv\Scripts\python.exe scripts/verify.py
```

The DB test role needs permission to create a disposable test database. The local Compose role has it; the production application role should not. Tests create and destroy their own `test_` database and never use real Stripe credentials. SQLite remains available as a lightweight development fallback if DATABASE_URL is unset; it does not validate PostgreSQL locking or production readiness.
