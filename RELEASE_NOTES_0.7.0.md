# Task Tracker 0.7.0

## Главное

- отдельный `responsible_manager` у каждой задачи;
- массовые операции для Managers;
- глобальный поиск;
- персональные сохранённые фильтры;
- portable host-backup БД + media вне Docker volumes;
- ежедневный systemd timer для backup;
- сохранены full-width UI и улучшенная вкладка «Загрузка» из 0.6.0.

## Обновление

Настоящий production `.env` не заменяйте.

```bash
docker compose up -d --build
docker compose exec web python manage.py check
docker compose exec web pytest
```

При запуске автоматически применяется миграция `0007_responsible_manager_saved_filters`.
Старые задачи получают `responsible_manager = created_by`.

## Backup

В `.env` рекомендуется:

```env
HOST_BACKUP_DIR=/home/adminka/projects/backups/task-tracker
BACKUP_KEEP=20
```

Ручной backup:

```bash
./scripts/backup_host.sh
```

Ежедневный timer:

```bash
./scripts/install_backup_timer.sh
```

Backup создаётся на host Raspberry Pi как переносимый `.tar.gz` + `.sha256`.
