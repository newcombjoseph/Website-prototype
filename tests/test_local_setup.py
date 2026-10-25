import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import urlsplit, unquote
from django.test import SimpleTestCase
from scripts import local


class LocalDatabaseSetupTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name) / '.local' / 'development.json'
        self.location = patch.object(local, 'STATE', self.state)
        self.location.start()
        self.addCleanup(self.location.stop)
        self.settings = {'version': 1, 'postgres_port': 15432,
                         'postgres_password': 'local-only-@:/?#+% password',
                         'django_secret_key': 'test-only-private-local-key-' * 3}

    def test_connection_encodes_special_characters_and_ignores_production_url(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://production.invalid/db', 'APP_ENV': 'production', 'AWS_STORAGE_BUCKET_NAME': 'production-images', 'STRIPE_SECRET_KEY': 'not-a-local-key'}):
            env = local.environment(self.settings)
        url = urlsplit(env['DATABASE_URL'])
        self.assertEqual((url.hostname, url.port, url.path), ('127.0.0.1', 15432, '/bonnets'))
        self.assertEqual(unquote(url.password), self.settings['postgres_password'])
        self.assertEqual(env['APP_ENV'], 'development')
        self.assertEqual(env['AWS_STORAGE_BUCKET_NAME'], '')
        self.assertEqual(env['STRIPE_SECRET_KEY'], '')
        self.assertEqual(env['CHECKOUT_MODE'], 'simulated')

    def test_existing_credentials_and_secret_cannot_be_overwritten(self):
        local.save_settings(self.settings)
        before = self.state.read_bytes()
        with self.assertRaises(local.SetupError):
            local.save_settings({**self.settings, 'postgres_password': 'replacement'})
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(local.load_settings(), self.settings)

    def test_malformed_saved_settings_are_preserved(self):
        self.state.parent.mkdir()
        for data in ['not JSON', '[]', '{"version": 2}']:
            self.state.write_text(data)
            with self.assertRaises(local.SetupError):
                local.load_settings()
            self.assertEqual(self.state.read_text(), data)

    def test_failed_database_authentication_never_saves_credentials(self):
        error = io.StringIO()
        with patch.dict(os.environ, {'POSTGRES_PASSWORD': 'incorrect-local-only-password'}), patch.object(local, 'start_database', side_effect=local.SetupError('Database sign-in failed.')), contextlib.redirect_stderr(error):
            result = local.main(['setup'])
        self.assertEqual(result, 1)
        self.assertFalse(self.state.exists())
        self.assertNotIn('incorrect-local-only-password', error.getvalue())

    def test_setup_reuses_existing_settings_without_prompting(self):
        local.save_settings(self.settings)
        before = self.state.read_bytes()
        with patch.object(local, 'start_database'), patch.object(local, 'manage') as manage, patch.object(local, 'new_settings', side_effect=AssertionError('Should reuse saved settings')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(local.main(['setup']), 0)
        self.assertEqual(self.state.read_bytes(), before)
        commands = [call.args[0] for call in manage.call_args_list]
        self.assertIn(['migrate', '--noinput'], commands)
        self.assertIn(['seed_store', '--bonnets'], commands)
        self.assertNotIn(['createsuperuser'], commands)
        self.assertNotIn(['flush'], commands)

    def test_test_command_keeps_security_checks_enabled(self):
        env = local.environment(self.settings, testing=True)
        self.assertEqual(env['DJANGO_DEBUG'], 'false')
        self.assertEqual(env['PRIVATE_ACCESS_REQUIRED'], 'true')
        self.assertEqual(env['PUBLIC_ORIGIN'], 'https://localhost')
