# Тестирование

## Основные инструменты

- pytest;
- pytest-django;
- Django system checks.

## Локальный запуск

Если dev-зависимости установлены:

```bash
pytest
```

Через Docker dev image, если pytest включён в образ:

```bash
docker compose exec web pytest
```

## Что необходимо тестировать

### Permissions

- anonymous перенаправляется на login;
- Employee не видит чужие задачи;
- Employee не создаёт задачи;
- Employee не принимает задачу;
- Manager видит все задачи;
- Employee не получает доступ к manager-only страницам.

### Workflow

```text
new
→ in_progress
→ review
→ done
```

и:

```text
review
→ revision
→ in_progress
→ review
```

### Notifications

Проверять:

- назначение;
- изменение срока;
- отправку на проверку;
- принятие;
- возврат на доработку;
- просрочку.

### Workload

Выполненные и отменённые задачи не должны увеличивать текущий score.

Задача `На проверке` должна отображаться как текущая, но не увеличивать рабочую нагрузку исполнителя.

### Images

Проверять:

- разрешённые MIME/type;
- размер;
- доступ только пользователя с доступом к задаче;
- невозможность открыть изображение чужой задачи.

## CI

GitHub Actions перед deployment выполняет:

```bash
python manage.py check --settings=config.settings_test
python manage.py makemigrations --check --dry-run --settings=config.settings_test
pytest
```

Если любой шаг падает, production deployment не должен запускаться.
