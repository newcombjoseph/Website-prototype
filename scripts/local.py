"""Create and run the local store without copying secrets into shell history.

This helper deliberately targets the loopback-only development Compose database.
It never reads a production DATABASE_URL or provisions AWS resources.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.local' / 'development.json'
COMPOSE = ROOT / 'deploy' / 'compose.local.yaml'


class SetupError(Exception):
    pass


def load_settings():
    if not STATE.exists():
        return None
    try:
        data = json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SetupError('Cannot read .local/development.json. Keep the file safe and fix its permissions/format; it has not been replaced.') from exc
    if (not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('postgres_password'), str)
            or not data['postgres_password'] or not isinstance(data.get('django_secret_key'), str)
            or len(data['django_secret_key']) < 50 or type(data.get('postgres_port')) is not int
            or not 1024 <= data['postgres_port'] <= 65535):
        raise SetupError('Saved development settings are invalid. They have not been overwritten.')
    return data


def new_settings(port):
    # Existing Docker volumes keep their original password. Never guess or reset it.
    password = os.environ.get('POSTGRES_PASSWORD') or getpass.getpass(
        'PostgreSQL password (use the existing password if the database already exists): ')
    if not password:
        raise SetupError('A PostgreSQL password is required. No database settings were saved.')
    return {'version': 1, 'postgres_password': password, 'postgres_port': port,
            'django_secret_key': secrets.token_urlsafe(64)}


def save_settings(data):
    STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of credentials. This is
    # an ignored local development file, never a database backup or production vault.
    try:
        descriptor = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SetupError('Settings were created by another process. Rerun setup to reuse them.') from exc
    with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
        json.dump(data, output, indent=2)
        output.write('\n')


def environment(data, port=8000, testing=False):
    values = os.environ.copy()
    password = quote(data['postgres_password'], safe='')
    values.update({
        'POSTGRES_PASSWORD': data['postgres_password'],
        'POSTGRES_PORT': str(data['postgres_port']),
        'DATABASE_URL': f'postgresql://bonnets:{password}@127.0.0.1:{data["postgres_port"]}/bonnets',
        'DJANGO_SECRET_KEY': data['django_secret_key'],
        'DJANGO_SETTINGS_MODULE': 'config.settings',
        'APP_ENV': 'development',
        'DJANGO_DEBUG': 'false' if testing else 'true',
        'DJANGO_ALLOWED_HOSTS': 'testserver,localhost,127.0.0.1' if testing else 'localhost,127.0.0.1',
        'PUBLIC_ORIGIN': 'https://localhost' if testing else f'http://localhost:{port}',
        'DJANGO_CSRF_TRUSTED_ORIGINS': '' if testing else f'http://localhost:{port},http://127.0.0.1:{port}',
        'PRIVATE_ACCESS_REQUIRED': 'true' if testing else 'false',
        'TRUST_HTTPS_PROXY': 'false',
        'CHECKOUT_MODE': 'simulated',
        'STRIPE_SECRET_KEY': '',
        'STRIPE_WEBHOOK_SECRET': '',
        'AWS_STORAGE_BUCKET_NAME': '',
    })
    return values


def execute(command, env, **kwargs):
    return subprocess.run(command, cwd=ROOT, env=env, check=True, **kwargs)


def start_database(env):
    try:
        subprocess.run(['docker', 'info'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SetupError('Start Docker Desktop using Linux containers, wait for the engine to run, then retry.') from exc
    execute(['docker', 'compose', '-f', str(COMPOSE), 'up', '-d', '--wait'], env)
    # A healthy PostgreSQL process does not prove the supplied password works.
    try:
        import psycopg
    except ImportError as exc:
        raise SetupError('Install dependencies first: python -m pip install -r requirements.txt') from exc
    try:
        with psycopg.connect(env['DATABASE_URL'], connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_database(), current_user')
                if cursor.fetchone() != ('bonnets', 'bonnets'):
                    raise SetupError('Connected to an unexpected database or role.')
    except psycopg.Error as exc:
        # Driver errors can contain connection details. Do not print them or reset
        # a password/volume automatically when an existing database rejects access.
        raise SetupError('Could not sign in to local PostgreSQL. Use its original password and check Docker/port settings. No database volume was deleted and no password was reset.') from exc


def manage(arguments, env):
    execute([sys.executable, str(ROOT / 'manage.py'), *arguments], env)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local PostgreSQL store setup and startup; no AWS resources are created.')
    commands = parser.add_subparsers(dest='command', required=True)
    setup = commands.add_parser('setup', help='Create/start the local database, migrate and seed samples without overwriting existing data.')
    setup.add_argument('--db-port', type=int, default=None, help='First setup only; defaults to POSTGRES_PORT or 15432.')
    run = commands.add_parser('run', help='Start PostgreSQL and the development web server using saved settings.')
    run.add_argument('--port', type=int, default=8000)
    management = commands.add_parser('manage', help='Run a Django management command using the saved development database.')
    management.add_argument('arguments', nargs=argparse.REMAINDER)
    commands.add_parser('test', help='Run existing checks against a disposable PostgreSQL test database.')
    args = parser.parse_args(argv)
    try:
        data = load_settings()
        fresh = data is None
        if fresh:
            if args.command != 'setup':
                raise SetupError('Run python scripts/local.py setup first.')
            try:
                port = args.db_port if args.db_port is not None else int(os.environ.get('POSTGRES_PORT', '15432'))
            except ValueError as exc:
                raise SetupError('POSTGRES_PORT must be a number, such as 15432.') from exc
            if not 1024 <= port <= 65535:
                raise SetupError('Choose a database port between 1024 and 65535.')
            data = new_settings(port)
        elif args.command == 'setup' and args.db_port is not None and args.db_port != data['postgres_port']:
            raise SetupError('Setup keeps the saved port to avoid switching databases. Update postgres_port in your private .local/development.json deliberately if you need to move it.')
        if args.command == 'manage' and not args.arguments:
            raise SetupError('Supply a command, for example: python scripts/local.py manage createsuperuser')
        if args.command == 'run' and not 1024 <= args.port <= 65535:
            raise SetupError('Choose a website port between 1024 and 65535.')
        env = environment(data, port=getattr(args, 'port', 8000), testing=args.command == 'test')
        start_database(env)
        if fresh:
            save_settings(data)
            print('Saved private development settings in .local/development.json (excluded from Git).')
        if args.command == 'setup':
            for arguments in [['migrate', '--noinput'], ['seed_store'], ['seed_store', '--bonnets'], ['setup_staff_roles'], ['check']]:
                manage(arguments, env)
            print('Local PostgreSQL database is ready. Existing products, stock and orders were preserved.')
            print('Next: python scripts/local.py run')
            print('New admin account only: python scripts/local.py manage createsuperuser')
            print('MFA enrollment: python scripts/local.py manage enroll_admin YOUR_USERNAME')
        elif args.command == 'run':
            manage(['runserver', f'127.0.0.1:{args.port}'], env)
        elif args.command == 'manage':
            manage(args.arguments, env)
        else:
            execute([sys.executable, str(ROOT / 'scripts' / 'verify.py')], env)
        return 0
    except SetupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print('The command failed. Address the error above and rerun; no volume deletion or password reset was attempted.', file=sys.stderr)
        return exc.returncode if exc.returncode > 0 else 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
