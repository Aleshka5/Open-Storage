# gateway — `/admin/*`

Каталог пользователей и выдача ролей. Живёт в `gateway`, потому что ему нужен контекст
«кто вызвал»: Admin API Keycloak у service-аккаунта один на всех, а правило «админ
сервиса правит только свой сервис» вне edge не выразить.

Все пути — на хосте `filenkov.store`, обрабатываются внутри процесса (не проксируются).

## Права

| Эндпоинт | `admin` | `svc:<svc>:admin` | прочие |
|---|---|---|---|
| `GET /admin/users` | ✓ | ✗ `403` | ✗ `403` |
| `PUT /admin/users/{id}/roles/{svc}` | ✓ (любой сервис) | только свой `{svc}` | ✗ `403` |
| `PATCH /admin/users/{id}` (enabled) | ✓ | ✗ `403` | ✗ `403` |
| `PUT /admin/users/{id}/admin` | ✓ | ✗ `403` | ✗ `403` |

## `GET /admin/users`

```json
{
  "users": [
    {
      "id": "8f14e45f-…",
      "email": "ada@example.com",
      "name": "Ada Lovelace",
      "enabled": true,
      "admin": false,
      "services": [
        { "service": "storage", "level": "family" },
        { "service": "image", "level": null }
      ]
    }
  ],
  "total": 4
}
```

Сборка: `GET /admin/realms/filenkov/users?first=0&max=200` + по одному
`GET /admin/realms/filenkov/users/{id}/role-mappings/realm`. Это N+1, и это осознанно:
на стенде десятки пользователей, кэш не нужен, а `max=200` ограничивает взрыв. Если
пользователей станет больше — переходить на `roles` конец Admin API с фильтром, не на
локальную копию каталога.

`services` всегда содержит все ключи из `services:` конфига, `level: null` = роль не
выдана (витрина рисует пустую колонку). Порядок — как в конфиге.

## `PUT /admin/users/{id}/roles/{svc}`

```json
{ "level": "family" }      // family | admin | blocked | null (снять роль)
```

Поведение: снимаются все `svc:<svc>:*` у пользователя, затем выдаётся выбранный уровень.
Один сервис — максимум одна роль, состояние не может «накопиться».

Ошибки: `409 LAST_ADMIN` (для `admin`), `403` (чужой сервис), `404` (нет пользователя),
`400` (неизвестный уровень), `503` (IdP недоступен).

## `PATCH /admin/users/{id}`

```json
{ "enabled": false }
```

Глобальная блокировка: `PUT /admin/realms/filenkov/users/{id}` + `POST
/admin/realms/filenkov/users/{id}/logout` (живые сессии умирают сразу, access-токены —
за 5 минут по `exp`).

## `PUT /admin/users/{id}/admin`

```json
{ "value": true }
```

Выдать/снять realm-роль `admin`. Правила:

- только вызывающий с ролью `admin`;
- **нельзя снять `admin` с себя**, если ты последний: `409 LAST_ADMIN`;
- нельзя снять `admin` с другого, если он последний (счётчик `admin`-пользователей
  запрашивается до изменения, сравнение — в одной операции).

## Проверки, которых нет в Keycloak

| Проверка | Реализация |
|---|---|
| Последний админ | `GET /admin/realms/filenkov/roles/admin/users` → если длина 1 и это цель, `409` |
| Админ сервиса правит свой сервис | сравнение `{svc}` из пути с `svc:<svc>:admin` в ролях вызывающего |
| Самолечение | снять роль с самого себя можно, если ты не последний админ |
| Запрет править `admin` через сервисный эндпоинт | `PUT /admin/users/{id}/roles/{svc}` с `svc=admin` → `400`: глобальный уровень отдельным эндпоинтом |

## Ошибки

Единый конверт, как у всех эндпоинтов edge:

```json
{ "error": { "code": "LAST_ADMIN", "message": "Cannot remove the last admin" } }
```

| Код | HTTP |
|---|---|
| `UNAUTHORIZED` | 401 |
| `FORBIDDEN` | 403 |
| `NOT_FOUND` | 404 |
| `VALIDATION` | 400 |
| `LAST_ADMIN` | 409 |
| `IDP_UNAVAILABLE` | 503 |

## Приёмка

```bash
T=$(curl -s -b /tmp/jar https://filenkov.store/auth/session | jq -r .subject)

# список
curl -s -b /tmp/jar https://filenkov.store/admin/users | jq '.total, .users[0].services'

# выдать сервисную роль и увидеть её в токене после refresh
curl -s -X PUT -b /tmp/jar -H 'Content-Type: application/json' \
  -d '{"level":"family"}' https://filenkov.store/admin/users/$T/roles/storage

# последний админ не снимается
curl -s -o /dev/null -w '%{http_code}\n' -X PUT -b /tmp/jar \
  -H 'Content-Type: application/json' -d '{"value":false}' \
  https://filenkov.store/admin/users/$T/admin      # 409, если админ один

# чужая колонка недоступна сервисному админу
# (под сервисным админом storage: PUT .../roles/image → 403)
```

Тесты: `internal/adminapi/*_test.go` с поддельным Admin API; обязательные случаи —
последний админ, сервисный админ на чужом сервисе, `svc=admin` через сервисный путь,
снятие роли и `null`.
