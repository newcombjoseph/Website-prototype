FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY config config
COPY shop shop
COPY manage.py .
# The build-only key is random and is not retained as an environment setting.
RUN python -c "import os,secrets; os.environ['DJANGO_SECRET_KEY']=secrets.token_urlsafe(64); os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; import django; django.setup(); from django.core.management import call_command; call_command('collectstatic',interactive=False,verbosity=0)"
RUN useradd --uid 10001 --create-home storefront
USER 10001
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "30", "--error-logfile", "-"]
