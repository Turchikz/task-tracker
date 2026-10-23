# Безопасность

## Секреты

Никогда не храните реальный `.env` в Git.

Обязательно:

```text
.env
```

должен находиться в `.gitignore`.

В `.env.example` допускаются только фиктивные значения.

## Django

Production:

```env
DEBUG=0
```

`SECRET_KEY` должен быть уникальным и длинным.

`ALLOWED_HOSTS` должен содержать только реальные hostnames/IP приложения.

`CSRF_TRUSTED_ORIGINS` содержит полные trusted origins со схемой.

## Пароли

Используйте отдельные:

- Django user passwords;
- PostgreSQL password;
- VPN password;
- SSH key.

Не используйте один пароль для нескольких систем.

## Docker Compose и `$`

Если секрет содержит `$`, учитывайте интерполяцию Docker Compose.

В `.env` безопаснее использовать одинарные кавычки:

```env
SECRET_KEY='value$with$dollar'
```

## Доступ к production

Предпочтительно:

```text
HTTPS → web application
VPN → SSH / administration
```

Не публикуйте SSH напрямую в Интернет без необходимости.

## Пользовательские изображения

Media не должны быть опубликованы как полностью публичный каталог.

Скачивание/просмотр должен проходить через проверку:

```text
authenticated user
+
permission to view task
```

## Permissions

Проверка прав должна выполняться server-side.

Нельзя полагаться только на скрытие кнопок в шаблоне.

## Backup

Backup содержит рабочие данные и должен рассматриваться как чувствительный файл.

Ограничьте права доступа к директории backup.

## Рекомендации на будущее

- rate limit / временная блокировка login;
- audit login events;
- регулярная проверка restore;
- HTTPS-only cookies после полного перехода на HTTPS;
- обновление зависимостей по расписанию.
