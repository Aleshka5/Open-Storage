# Контракт личности v1

Ровно одна версия. Нет флага «старый режим», нет второго набора имён, нет переговоров о
версии через заголовок. Изменение контракта = одновременная правка всех потребителей в
одном релизе.

## Что приложение получает

| Заголовок | Значение | Пример |
|---|---|---|
| `Authorization` | `Bearer <access JWT>` — тот самый, что в cookie, без перевыпуска | `Bearer eyJhbGciOiJSUzI1NiIs…` |
| `X-Auth-Subject` | `sub` — неизменный ID пользователя в `idp` | `8f14e45f-…` |
| `X-Auth-Email` | `email` | `ada@example.com` |
| `X-Auth-Name` | `name` (отображаемое имя из Google) | `Ada Lovelace` |
| `X-Auth-Roles` | realm-роли через пробел, отсортированы | `admin svc:storage:family` |
| `X-Auth-Session` | `sid` — ID сессии Keycloak | `a1b2c3d4-…` |
| `X-Forwarded-Host/Proto/For` | от `proxy`, затем переписаны `edge` | — |

Пустой набор ролей → заголовка `X-Auth-Roles` нет (не пустая строка).

## Что срезается

До инъекции из запроса удаляются, без исключений:

```
X-Auth-*        (любой префикс, любой регистр)
X-User-Id
X-Storage-Role
X-Original-User
```

Правило одной строкой: **приложение никогда не получает identity-заголовок, который
пришёл от клиента.** Тест `internal/edge/headers_test.go` проверяет это на каждом
маршруте, включая WebSocket-апгрейд.

## Как приложению проверять себя

Два законных способа, оба опираются на один и тот же токен:

**A. Доверять заголовкам** (простое приложение внутри `open_network`, недоступное иначе):

```python
sub   = request.headers["X-Auth-Subject"]      # обязателен, иначе 401
roles = request.headers.get("X-Auth-Roles", "").split()
if "svc:storage:family" not in roles and "svc:storage:admin" not in roles:
    raise Forbidden
```

**B. Проверять токен сам** (правильный путь; обязателен, если приложение достижимо
напрямую или выполняет длинные фоновые задачи от имени пользователя):

```python
import jwt, requests
jwks = requests.get("https://id.filenkov.store/realms/filenkov/protocol/openid-connect/certs").json()
claims = jwt.decode(request.headers["Authorization"].split(" ", 1)[1], jwks,
                    algorithms=["RS256"], audience="account",
                    issuer="https://id.filenkov.store/realms/filenkov")
sub = claims["sub"]
```

JWKS кэшируется по `kid` (TTL 15 минут, обновление по неизвестному `kid`), `aud`
проверяется как минимум на `account`, `exp` — обязательно.

Проверяющие стороны: `iss` = issuer realm, `aud` содержит `account`, `azp` = `gateway`
(кто именно выпустил токен), `exp`/`nbf`. Проверять только `aud=account` недостаточно:
это значение есть у токена любого клиента этого realm.

## Identity и сессия

- `X-Auth-Subject` — стабильный идентификатор владельца данных. Использовать его как
  внешний ключ в своих таблицах можно и нужно.
- `X-Auth-Session` — не идентификатор пользователя. Это ключ сессии: по нему строятся
  вещи, которые должны умереть вместе со входом (приватный ключ хранилища, черновики).
  Два разных входа одного человека → два разных `sid`.
- Logout в `idp` убивает `sid`; всё, что приложение привязало к `sid`, становится
  недостижимым само, без колбэка.

## Ошибки edge

| Код | Тело | Когда |
|---|---|---|
| `302` | `Location: https://filenkov.store/auth/login?return_to=…` | аноним, браузерный путь |
| `401` | `{"error":"unauthorized"}` | аноним на `/api/*`, `/users*`, WS |
| `403` | `{"error":"forbidden"}` | аутентифицирован, но роль не даёт |
| `403` | `{"error":"blocked"}` | аккаунт выключен в `idp` |
| `404` | `{"error":"not_found"}` | нет маршрута (в том числе для путей `deny`) |
| `503` | `{"error":"auth_unavailable"}` | недоступны `idp`/JWKS |
| `502` | `{"error":"bad_gateway"}` | upstream не ответил |

`return_to` собирается из фактического запроса и проверяется по allowlist'у хостов из
конфига: внешний адрес в `return_to` не пройдёт.

## Совместимость

Никакой. Клиент, ожидающий `X-User-Id` или `X-Storage-Role`, работать не будет — это
осознанно: два имени для одного смысла и есть тот легаси, который переписывание убирает.
