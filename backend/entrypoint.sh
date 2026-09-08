#!/usr/bin/env bash
set -euo pipefail

wait_for() {
  local host="$1" port="$2" label="$3"
  echo "waiting for ${label} at ${host}:${port} ..."
  until nc -z "${host}" "${port}"; do sleep 1; done
  echo "${label} is up."
}

wait_for "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}" "postgres"

if [[ -n "${CELERY_BROKER_URL:-}" ]]; then
  wait_for "${RABBITMQ_HOST:-rabbitmq}" "${RABBITMQ_PORT:-5672}" "rabbitmq"
fi

# Only the web container migrates, so the worker and beat don't race it.
if [[ "${RUN_MIGRATIONS:-0}" == "1" ]]; then
  python manage.py migrate --noinput

  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print('created superuser admin/admin')
"
fi

exec "$@"
