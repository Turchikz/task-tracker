RaTracker 0.9.11 — полная версия проекта

Новое: XLSX-отчёт по загрузке и работе отдела за произвольный период.
Включает выполненные задачи, сводку для руководства и календарь по месяцам.

Перед обновлением сделайте резервную копию БД и media.
Сохраните существующий .env. Не удаляйте Docker volumes.

docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py check

Экспорт: Загрузка → даты «с» и «по» → Скачать XLSX.
Подробности и результаты проверок: RELEASE_NOTES_0.9.11.md.
