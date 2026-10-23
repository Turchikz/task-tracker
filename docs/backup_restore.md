# Backup и восстановление

## Что сохраняется

Task Tracker имеет два persistent набора данных:

1. PostgreSQL;
2. пользовательские фото/скриншоты из media volume.

Static-файлы восстанавливаются из Git и в backup не включаются. Реальный `.env` намеренно не упаковывается, чтобы архив с данными можно было безопаснее хранить отдельно от секретов.

## Windows + Docker Desktop

Пока Task Tracker запускается тестово через Docker Desktop на Windows, backup можно хранить на диске Windows **вне Docker volumes**.

Рекомендуемая схема:

```text
C:\Turchik\
├── task-tracker\
└── backups\
    └── task-tracker\
        ├── tasktracker_backup_20261021_210000.tar.gz
        ├── tasktracker_backup_20261021_210000.tar.gz.sha256
        ├── latest.txt
        └── backup_windows.log
```

Если проект находится, например, в:

```text
C:\Turchik\task-tracker
```

то `scripts/backup_windows.ps1` по умолчанию выберет:

```text
C:\Turchik\backups\task-tracker
```

### Ручной backup на Windows

Из корня проекта в PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup_windows.ps1
```

Другой каталог и количество хранимых копий:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup_windows.ps1 `
  -BackupDir "D:\TaskTrackerBackups" `
  -Keep 30
```

Скрипт:

1. проверяет доступность Docker Desktop;
2. создаёт PostgreSQL dump внутри контейнера и безопасно копирует бинарный dump на Windows;
3. архивирует Docker media volume с фото/скриншотами;
4. создаёт `manifest.txt`;
5. упаковывает всё в переносимый `.tar.gz`;
6. создаёт `.sha256`;
7. удаляет старые копии сверх лимита.

Реальный `.env` в backup намеренно не включается.

### Ежедневный backup через Планировщик заданий Windows

Один раз выполните из PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_backup_task_windows.ps1
```

По умолчанию:

- время: `21:00`;
- хранение: 30 последних копий;
- каталог: соседний `backups\task-tracker`.

Задать свои параметры:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_backup_task_windows.ps1 `
  -Time "21:30" `
  -BackupDir "D:\TaskTrackerBackups" `
  -Keep 30
```

Проверить зарегистрированную задачу:

```powershell
Get-ScheduledTask -TaskName "Task Tracker Daily Backup"
```

Запустить её вручную:

```powershell
Start-ScheduledTask -TaskName "Task Tracker Daily Backup"
```

Посмотреть журнал:

```powershell
Get-Content "C:\Turchik\backups\task-tracker\backup_windows.log" -Tail 50
```

Удалить ежедневную задачу:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_backup_task_windows.ps1
```

### Ограничение Docker Desktop

Автоматическая задача настроена на запуск в интерактивной сессии текущего пользователя. Это сделано намеренно: Docker Desktop обычно также работает в пользовательской сессии.

Поэтому в назначенное время:

- пользователь Windows должен быть вошедшим в систему;
- Docker Desktop должен быть запущен;
- контейнер `db` должен работать.

Если условия не выполнены, скрипт не создаст неполный backup и запишет причину в `backup_windows.log`.

### Перенос на Raspberry Pi

Windows backup имеет ту же полезную структуру данных, что и Linux host-backup:

```text
database.dump
media.tar.gz
manifest.txt
env.example
VERSION
```

Поэтому свежую копию можно сохранить на флешку и позднее использовать при переносе данных на Raspberry Pi.

## Где хранится backup

Backup создаётся **на файловой системе Raspberry Pi, вне Docker volumes**. По умолчанию:

```text
/home/adminka/projects/backups/task-tracker/
```

Путь задаётся в `.env`:

```env
HOST_BACKUP_DIR=/home/adminka/projects/backups/task-tracker
BACKUP_KEEP=20
```

Результат:

```text
tasktracker_backup_20261021_203000.tar.gz
tasktracker_backup_20261021_203000.tar.gz.sha256
latest.tar.gz -> tasktracker_backup_20261021_203000.tar.gz
```

В `.tar.gz` находятся:

```text
database.dump
media.tar.gz
manifest.txt
env.example
VERSION
```

## Создать backup вручную

Из корня проекта:

```bash
./scripts/backup_host.sh
```

Скрипт использует `docker compose exec`, но финальный файл записывает на **host**, поэтому потеря Docker volume не уничтожает сам backup.

## Ежедневный backup

Установить systemd timer один раз:

```bash
chmod +x scripts/*.sh
./scripts/install_backup_timer.sh
```

По умолчанию backup запускается ежедневно около `02:30` с небольшим случайным сдвигом. Проверить:

```bash
systemctl list-timers task-tracker-backup.timer
sudo systemctl status task-tracker-backup.timer
```

Запустить вручную через systemd:

```bash
sudo systemctl start task-tracker-backup.service
```

## Копирование на флешку

После подключения флешки найдите её mount point, например `/media/adminka/BACKUP`, затем:

```bash
cp ~/projects/backups/task-tracker/tasktracker_backup_*.tar.gz /media/adminka/BACKUP/
cp ~/projects/backups/task-tracker/tasktracker_backup_*.sha256 /media/adminka/BACKUP/
sync
```

Хранить backup только на том же накопителе Raspberry Pi недостаточно. Периодически переносите хотя бы одну свежую копию на другой физический носитель.

## Проверка целостности

```bash
cd ~/projects/backups/task-tracker
sha256sum -c tasktracker_backup_YYYYMMDD_HHMMSS.tar.gz.sha256
```

## Восстановление полного backup

Перед восстановлением создайте backup текущего состояния. Затем:

```bash
./scripts/restore_host.sh ~/projects/backups/task-tracker/tasktracker_backup_YYYYMMDD_HHMMSS.tar.gz
```

Скрипт:

1. проверит SHA-256, если sidecar-файл доступен;
2. остановит web/notifier/nginx;
3. восстановит PostgreSQL;
4. восстановит media;
5. снова запустит Docker Compose.

Для подтверждения требуется вручную ввести `RESTORE`.

## CI/CD

Перед каждым production deploy GitHub Actions вызывает `scripts/backup_host.sh`, поэтому pre-deploy backup имеет тот же переносимый формат.

## Проверка восстановления

Не реже раза в месяц рекомендуется проверить свежую копию:

- `python manage.py check`;
- вход в систему;
- количество задач/пользователей;
- несколько задач с историей;
- открытие нескольких фото/скриншотов.
