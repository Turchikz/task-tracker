# Task Tracker 0.7.1

## Главное изменение

Добавлен автоматический backup для текущего тестового окружения Windows + Docker Desktop.

### Ручной backup

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup_windows.ps1
```

При расположении проекта:

```text
C:\Turchik\task-tracker
```

копии по умолчанию будут создаваться в:

```text
C:\Turchik\backups\task-tracker
```

### Ежедневный запуск

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_backup_task_windows.ps1
```

По умолчанию задача выполняется ежедневно в 21:00 и хранит 30 последних копий.

Docker Desktop должен быть запущен, а пользователь Windows — находиться в активной/вошедшей сессии.

## Что находится в backup

```text
database.dump
media.tar.gz
manifest.txt
VERSION
env.example
```

Реальный `.env` в архив не включается.

Результат:

```text
tasktracker_backup_YYYYMMDD_HHMMSS.tar.gz
tasktracker_backup_YYYYMMDD_HHMMSS.tar.gz.sha256
```

Backup находится вне Docker volumes и подходит для копирования на флешку.
