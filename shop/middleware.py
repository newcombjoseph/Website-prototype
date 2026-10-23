import base64
import hmac
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.http import HttpResponse


class PrivateAccessMiddleware:
    """Fail closed, including if private-access credentials were not configured."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.PRIVATE_ACCESS_REQUIRED:
            allowed = False
            try:
                scheme, value = request.headers.get('Authorization', '').split(' ', 1)
                username, password = base64.b64decode(value, validate=True).decode().split(':', 1)
                allowed = (scheme.lower() == 'basic' and bool(settings.PRIVATE_USERNAME) and
                           bool(settings.PRIVATE_PASSWORD_HASH) and
                           hmac.compare_digest(username, settings.PRIVATE_USERNAME) and
                           check_password(password, settings.PRIVATE_PASSWORD_HASH))
            except (ValueError, TypeError, UnicodeDecodeError):
                pass
            if not allowed:
                return HttpResponse('Private prototype. Owner access required.', status=401,
                                    headers={'WWW-Authenticate': 'Basic realm="Fieldform private prototype", charset="UTF-8"',
                                             'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow'})
        return self.get_response(request)


class StoreHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = ("default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self' https://checkout.stripe.com")
        response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        response['Cache-Control'] = 'no-store'
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=()'
        return response
