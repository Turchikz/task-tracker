#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Использование: ./scripts/restore_media.sh backups/tasktracker_media_YYYYMMDD_HHMMSS.tar.gz" >&2
  exit 1
fi

backup_file=$1
if [ ! -s "$backup_file" ]; then
  echo "Backup не найден или пуст: $backup_file" >&2
  exit 1
fi

echo "ВНИМАНИЕ: изображения из backup будут добавлены/перезаписаны в текущем media volume."
printf "Введите RESTORE для продолжения: "
read confirmation
if [ "$confirmation" != "RESTORE" ]; then
  echo "Отменено."
  exit 1
fi

docker compose exec -T web python -c 'import os,sys,tarfile; os.makedirs("/app/media", exist_ok=True); t=tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz"); t.extractall("/app/media", filter="data"); t.close()' < "$backup_file"
echo "Изображения восстановлены."
