#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Использование: ./scripts/restore.sh backups/file.dump" >&2
  exit 1
fi

backup_file=$1
if [ ! -s "$backup_file" ]; then
  echo "Backup не найден или пуст: $backup_file" >&2
  exit 1
fi

echo "ВНИМАНИЕ: восстановление изменит текущую PostgreSQL базу Task Tracker."
printf "Введите RESTORE для продолжения: "
read confirmation
if [ "$confirmation" != "RESTORE" ]; then
  echo "Отменено."
  exit 1
fi

docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$backup_file"

echo "Восстановление завершено."
