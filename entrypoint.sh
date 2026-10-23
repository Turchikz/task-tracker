#!/bin/sh
set -eu

if [ "${DEBUG:-1}" = "0" ] && [ "${POSTGRES_PASSWORD:-}" = "change-me" ]; then
  echo "POSTGRES_PASSWORD must be changed for production" >&2
  exit 1
fi

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
fi

exec "$@"
