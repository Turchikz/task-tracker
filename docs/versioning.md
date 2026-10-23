Текущая версия: **0.7.0**

# Версионирование и релизы

## Текущая версия

```text
0.5.0
```

Версия хранится в корневом файле:

```text
VERSION
```

## Почему пока `0.x`

Task Tracker уже пригоден для реальной внутренней эксплуатации, но остаётся в активной фазе развития.

Версию `1.0.0` разумно присвоить после:

- пилотной эксплуатации реальными пользователями;
- проверки backup/restore;
- стабилизации workflow;
- покрытия критических сценариев тестами;
- подтверждения production deployment и recovery procedures.

## Semantic Versioning

Формат:

```text
MAJOR.MINOR.PATCH
```

### PATCH

Исправление без нового пользовательского функционала.

Пример:

```text
0.5.0 → 0.5.1
```

### MINOR

Новая обратно совместимая функция.

Пример:

```text
0.5.1 → 0.6.0
```

### MAJOR

Несовместимое изменение пользовательского поведения/API/структуры эксплуатации.

После первого стабильного релиза:

```text
1.2.0 → 2.0.0
```

## Процесс релиза

1. Убедиться, что working tree чистый.
2. Обновить `VERSION`.
3. Обновить `CHANGELOG.md`.
4. Запустить тесты.
5. Commit.
6. Push.
7. Убедиться, что CI/CD прошёл.
8. Создать Git tag.

Windows:

```powershell
git tag -a v0.5.0 -m "Task Tracker v0.5.0"
git push origin v0.5.0
```

Linux:

```bash
git tag -a v0.5.0 -m "Task Tracker v0.5.0"
git push origin v0.5.0
```

## Следующие версии

Ориентировочно:

```text
0.5.x — стабилизация текущего набора функций
0.6.0 — full-width UI / рефакторинг
0.7.0 — responsible manager / bulk actions / global search / saved filters / portable backup
0.7.0 — production reliability / observability
1.0.0 — стабильная внутренняя версия
```
