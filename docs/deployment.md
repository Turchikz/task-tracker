# Развёртывание

## Production host

Целевая платформа:

- Raspberry Pi 5;
- Linux;
- Docker Engine;
- Docker Compose plugin;
- GitHub Actions self-hosted runner.

## Переменные окружения

Production `.env` не хранится в Git.

Рекомендуемое расположение:

```text
~/projects/.config/task-tracker/.env
```

Пример находится в `.env.example`.

Минимально необходимы:

```env
SECRET_KEY=...
DEBUG=0

ALLOWED_HOSTS=...
CSRF_TRUSTED_ORIGINS=...

POSTGRES_DB=tasktracker
POSTGRES_USER=tasktracker
POSTGRES_PASSWORD=...
POSTGRES_HOST=db
POSTGRES_PORT=5432

APP_PORT=8081
```

## Ручной deployment

```bash
docker compose up -d --build --remove-orphans
```

Проверка:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8081/health/
```

Логи:

```bash
docker compose logs --tail=100 web nginx
```

## CI/CD

Workflow находится в:

```text
.github/workflows/ci.yml
```

### CI

Для push и pull request:

```text
checkout
↓
Python setup
↓
pip install
↓
Django check
↓
migration check
↓
pytest
```

### CD

Выполняется только после успешного CI для `main`.

```text
self-hosted runner
↓
production .env
↓
backup
↓
docker compose up --build
↓
healthcheck
```

## Self-hosted runner

Runner должен иметь labels:

```text
self-hosted
Linux
ARM64
task-tracker
```

Runner должен работать от пользователя, имеющего доступ к Docker.

## Persistent data

Не удаляйте volumes при обычном deployment.

Особенно опасна команда:

```bash
docker compose down -v
```

Она удаляет persistent volumes.

Обычное обновление:

```bash
docker compose up -d --build --remove-orphans
```

не удаляет данные PostgreSQL и media.

## После deployment

Проверить:

```bash
docker compose ps
docker compose logs --tail=100 web nginx notifier
curl -fsS http://127.0.0.1:${APP_PORT:-8081}/health/
```


## Portable host backup перед deploy (v0.7.0)

Pre-deploy job вызывает `scripts/backup_host.sh`. Архив записывается в `/home/adminka/projects/backups/task-tracker/` на host Raspberry Pi, а не в Docker volume. Поэтому его можно скопировать на внешний USB-носитель даже независимо от состояния контейнеров после создания backup.
