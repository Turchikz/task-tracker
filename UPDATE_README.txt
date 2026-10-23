RaTracker 0.8.3 — полная версия проекта

Распакуйте архив поверх текущего проекта. Сохраните существующий .env.
Сначала создайте резервную копию базы и media.

Основные команды:
  docker compose up -d --build
  docker compose exec web python manage.py migrate
  docker compose exec web python manage.py check
  docker compose exec web pytest tests/test_v083_collaboration.py

Полная инструкция: RELEASE_NOTES_0.8.3.md
О новых функциях: docs/collaboration_and_handover.md

Старые задачи сохраняют своих основных исполнителей; новая миграция
0008 лишь добавляет связь с дополнительными сотрудниками и историю передач.
