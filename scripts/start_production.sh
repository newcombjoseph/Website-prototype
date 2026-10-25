#!/bin/sh
set -eu
# Migrations run once as a release step, not independently in each web worker.
export APP_ENV=production
python manage.py check --deploy --fail-level WARNING
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2 --timeout 30 --error-logfile -
