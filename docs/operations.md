# Эксплуатация

## Проверка состояния

```bash
docker compose ps
```

Затем:

```bash
curl -fsS http://127.0.0.1:8081/health/
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

## Просмотр логов

```bash
docker compose logs --tail=100 web
docker compose logs --tail=100 nginx
docker compose logs --tail=100 db
docker compose logs --tail=100 notifier
```

Онлайн:

```bash
docker compose logs -f web nginx
```

## Перезапуск

Обычный restart:

```bash
docker compose restart web nginx
```

Если изменился `.env`, `restart` недостаточен: контейнер необходимо пересоздать.

```bash
docker compose up -d --force-recreate
```

## Обновление

```bash
docker compose up -d --build --remove-orphans
```

## Проверка миграций

```bash
docker compose exec web python manage.py showmigrations
```

## Django check

```bash
docker compose exec web python manage.py check
```

## Создание superuser

```bash
docker compose exec web python manage.py createsuperuser
```

## Диск

На Raspberry Pi периодически проверяйте:

```bash
df -h
docker system df
```

Не используйте агрессивную очистку Docker volumes без понимания, какие данные в них находятся.

## После перезагрузки Raspberry Pi

Проверить:

```bash
docker compose ps
systemctl status actions.runner.*
```

Контейнеры с `restart: unless-stopped` должны стартовать автоматически.

## Ежедневный portable backup (v0.7.0)

Backup хранится на host Raspberry Pi, а не внутри Docker volume:

```bash
./scripts/backup_host.sh
```

Установить автоматический запуск:

```bash
./scripts/install_backup_timer.sh
```

Проверить timer:

```bash
systemctl list-timers task-tracker-backup.timer
```

Директория по умолчанию:

```text
/home/adminka/projects/backups/task-tracker/
```

Последний `.tar.gz` и соответствующий `.sha256` рекомендуется периодически копировать на USB-носитель.


## Ежедневный backup на Windows + Docker Desktop

Ручной запуск:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup_windows.ps1
```

Зарегистрировать ежедневный запуск в 21:00:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_backup_task_windows.ps1
```

Backup хранится на диске Windows вне Docker volumes. По умолчанию — в соседнем относительно проекта каталоге:

```text
..\backups\task-tracker\
```

Docker Desktop должен быть запущен в момент выполнения задачи.

