# Windows development setup

Install Python 3.12, Git and Docker Desktop (Linux containers). Start Docker Desktop and wait for its engine to run. Use PowerShell in the folder containing `manage.py`.

## Update an existing checkout

```powershell
git pull origin main
```

If Git refuses because you previously edited `deploy/compose.local.yaml` to fix the port, preserve that edit before pulling:

```powershell
git stash push -m "Save previous local PostgreSQL port configuration" -- deploy/compose.local.yaml
git pull origin main
```

The new configuration defaults to port **15432**, so you do not need to reapply the old port edit. Other custom changes in that stash should be reviewed separately. No database volume is deleted by Git or this setup helper.

## First setup

If you do not already have `.venv`, create it once:

```powershell
py -3.12 -m venv .venv
```

Then install dependencies and create/initialize the database:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/local.py setup
```

If `POSTGRES_PASSWORD` is still set in your current PowerShell window, setup reuses it. Otherwise it asks for a password without displaying it. **If the database already exists, enter its original password.** For a new database, choose a strong password. Setup does not reset passwords or remove volumes.

The helper:

1. Starts the existing Compose PostgreSQL service, or creates it if absent, on loopback port **15432**. Use `setup --db-port 5432` only if your existing service deliberately uses port 5432; you can also set `POSTGRES_PORT` before first setup.
2. Verifies a real authenticated database connection before saving settings.
3. Creates/applies the tables for products, size/style variants, images, inventory history, orders, purchased items, order history, payment events, staff accounts and sessions.
4. Adds eight sample scrub caps, each with Small/Medium/Large variants, plus the optional original draft bonnet-fitting examples. Untouched household samples are unpublished. Edited products and all stock/order records are preserved. Orders remain empty until you perform a test checkout; no invented customer orders are added.
5. Configures the staff permission groups. It never creates default admin credentials or disables MFA.

Private local settings (database password, selected port and a stable Django secret) are saved in `.local/development.json`. This file is excluded from Git and Docker builds. Treat it like a local `.env` file: it is not encrypted, should remain in your private Windows user folder, and must not contain production credentials. Do not upload or share it. The helper explicitly uses the local development database, even if your shell also has a production DATABASE_URL set.

To create your admin account **only if you do not already have one**:

```powershell
.\.venv\Scripts\python.exe scripts/local.py manage createsuperuser
.\.venv\Scripts\python.exe scripts/local.py manage enroll_admin YOUR_USERNAME
```

Replace `YOUR_USERNAME` with the username you chose. Enrollment displays a private `otpauth://` setup URI in your trusted terminal. Add its secret to an authenticator app, enter the current code to confirm enrollment, and store the one-time recovery codes safely offline. Existing admin accounts and MFA enrollment are preserved.

## Every time you want to run the website

Start Docker Desktop, then run:

```powershell
.\.venv\Scripts\python.exe scripts/local.py run
```

That command starts PostgreSQL if needed and loads your saved local settings. No repeated password exports are necessary. Visit `http://localhost:8000` and `http://localhost:8000/admin/`. Stop Django with Ctrl+C. If the website port is occupied, use `scripts/local.py run --port 8001` and open port 8001 instead.

After pulling changes that add migrations, rerun `scripts/local.py setup`. It is repeatable and preserves existing products, stock, orders, staff accounts and the stable secret. It adds missing sample caps and archives untouched household examples, while preserving edits to product details, prices and inventory. PostgreSQL data lives in the existing Compose volume. Do not use `docker compose down -v` unless you deliberately intend to delete that development data.

## Troubleshooting

- **Docker engine / named pipe error:** open Docker Desktop, select Linux containers and wait for the engine.
- **Port blocked:** first setup defaults to 15432. For a new setup choose another free port with `setup --db-port 25432`. For already saved settings, deliberately change only `postgres_port` in your private `.local/development.json`, then rerun setup. The named volume and password stay the same.
- **Wrong password:** use the database's original password. Editing `POSTGRES_PASSWORD` does not reset an initialized PostgreSQL volume. Correct the private saved password if you deliberately changed the database password elsewhere. Do not delete a volume to solve authentication errors.
- **Forgotten private local settings:** recover the existing password from your password manager or original protected configuration. The helper cannot recover/reset an unknown database password automatically.
- **Manual commands:** Django does not load `.env` or `.local/development.json` automatically. Use `scripts/local.py manage COMMAND` to apply the saved settings.

## Tests and housekeeping

```powershell
.\.venv\Scripts\python.exe scripts/local.py test
.\.venv\Scripts\python.exe scripts/local.py manage expire_reservations
```

Tests run deployment checks and the existing suites using a disposable PostgreSQL test database. The local Docker role can create test databases; the production application role should not have that permission. Test checkout never uses live Stripe credentials. Run `expire_reservations` periodically to release abandoned simulated reservations after 35 minutes.

AWS production setup remains separate; see [AWS deployment](../deploy/AWS.md). This local helper neither provisions AWS nor creates a production database.

## Updating to the clinical scrub cap collection

After pulling this update, stop the website and run `scripts/local.py setup`, then `scripts/local.py run` using your virtual environment's Python. Setup adds the new sample collection and unpublishes untouched household placeholders without deleting them. If an old sample has already been edited or its stock has changed, it stays under your control: unpublish it in the admin if you no longer want it in the storefront. Orders and their purchased-item snapshots are preserved. No new migrations or admin/MFA enrollment are required for this visual/catalog update.
