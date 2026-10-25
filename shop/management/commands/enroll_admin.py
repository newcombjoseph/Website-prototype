"""Trusted-console MFA enrollment. Never expose this operation as a public URL."""
from getpass import getpass
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

class Command(BaseCommand):
    help = 'Enroll an existing staff user in an authenticator app and issue recovery codes locally.'
    def add_arguments(self, parser):
        parser.add_argument('username')
    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options['username'], is_staff=True, is_active=True)
        except get_user_model().DoesNotExist:
            raise CommandError('An active staff user with this username is required.')
        if not user.check_password(getpass('Confirm this staff account password: ')):
            raise CommandError('Incorrect password.')
        if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
            raise CommandError('MFA is already enrolled. Recovery/reset requires a trusted operator; do not delete devices casually.')
        device, _ = TOTPDevice.objects.get_or_create(user=user, name='Authenticator', defaults={'confirmed': False})
        self.stdout.write('Secret setup link: enter it in your authenticator locally. Do not share or log it.')
        self.stdout.write(device.config_url)
        if not device.verify_token(getpass('Six-digit code from your authenticator: ')):
            raise CommandError('Invalid code. Enrollment not confirmed; rerun to retry.')
        device.confirmed = True
        device.save(update_fields=['confirmed'])
        backup = StaticDevice.objects.create(user=user, name='Recovery codes')
        self.stdout.write('Store these one-time recovery codes offline:')
        for _ in range(10):
            token = StaticToken.random_token()
            StaticToken.objects.create(device=backup, token=token)
            self.stdout.write(token)
