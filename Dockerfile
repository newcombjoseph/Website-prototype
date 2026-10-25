# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chown=10001:10001 requirements.txt .
# Optional enterprise/cloud build CA, mounted for the build only. TLS remains verified.
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -f /run/secrets/build_ca_bundle ]; then export PIP_CERT=/run/secrets/build_ca_bundle; fi; \
    pip install --no-cache-dir -r requirements.txt
COPY --chown=10001:10001 config config
COPY --chown=10001:10001 shop shop
COPY --chown=10001:10001 manage.py .
COPY --chown=10001:10001 scripts/start_production.sh scripts/start_production.sh
# The build-only key is random and is not retained as an environment setting.
RUN python -c "import os,secrets; os.environ['DJANGO_SECRET_KEY']=secrets.token_urlsafe(64); os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; import django; django.setup(); from django.core.management import call_command; call_command('collectstatic',interactive=False,verbosity=0)"
RUN useradd --uid 10001 --create-home storefront
USER 10001
EXPOSE 8000
CMD ["sh", "scripts/start_production.sh"]
