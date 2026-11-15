# gateway

Единственный вход в приложения Open-Storage после TLS-слоя. Один бинарь, один
конфиг-файл, никакого состояния на диске.

- Язык: Go 1.26, только stdlib + `gopkg.in/yaml.v3` + `github.com/coreos/go-oidc/v3`
- Порт: `8080` внутри `open_network`, публикуется как `127.0.0.1:8080` для проб
- Конфиг: `gateway/config.yaml`, монтируется read-only, валидируется на старте
- Бюджет: **≤ 2000 строк Go** без тестов. Всё, что не влезает, — повод пересмотреть
  фичу, а не дописать пакет.

## Что делает

1. **BFF** (`/auth/*`) — OIDC-клиент к `idp`: вход, callback, выход, выдача профиля
   для витрины. Токены живут в httpOnly cookie, JS их не видит. Детали: [bff.md](bff.md).
2. **Политика** — по `Host` + пути + методу выбирает маршрут и проверяет, кому он
   доступен (`public`, `session`, `admin`, `service(<svc>, …)`).
3. **Личность** — срезает любые входящие `X-Auth-*`/`X-User-Id`/`X-Storage-Role`,
   проверяет access-токен по JWKS и инжектит канонический набор заголовков. Детали:
   [identity-contract.md](identity-contract.md).
4. **Прокси** — реверс-прокси с per-host таймаутами, WebSocket-апгрейдом, SSE и
   инъекцией сервисных токенов. Детали: [operations.md](operations.md).
5. **Админка** (`/admin/*`) — каталог пользователей поверх Keycloak Admin API с
   проверками «последний админ» и «админ сервиса правит свой сервис». Детали:
   [admin.md](admin.md).

## Чего не делает

| Не делает | Где это живёт |
|---|---|
| Не выдаёт и не подписывает токены | `idp` |
| Не хранит пользователей, роли, сессии | `idp` |
| Не завершает TLS, не говорит по ACME | `proxy` |
| Не рендерит UI | `resume-page` |
| Не держит Redis/БД/файлов состояния | нигде — состояния нет |
| Не знает, что такое «User-Service» | — |

## Пакеты

```
gateway/
  cmd/gateway/main.go        флаги, загрузка конфига, старт/остановка
  internal/config/           схема, валидатор, компиляция маршрутов, табличные тесты
  internal/oidc/             discovery, JWKS-кэш, верификатор, claims → Identity
  internal/session/          печать/распаковка cookie (AES-256-GCM), single-flight refresh
  internal/policy/           предикаты и их проверка по Identity
  internal/edge/             матчинг хоста/пути/метода, прокси, WS, заголовки, логи, /metrics
  internal/bff/              /auth/login|c |allback|logout|session
  internal/adminapi/         /admin/users*
  config.yaml                маршруты и хосты (единственный источник правды по edge)
```

## Жизненный цикл запроса

1. `proxy` присылает запрос с `Host` и `X-Forwarded-Proto`.
2. `edge` находит маршрут по `Host` + `Path` + `Method`. Нет маршрута → `404` JSON
   (`{"error":"not_found"}`), а не «провались в SPA»: у каждого хоста обязан быть явный
   `/**`.
3. `session` читает `__Secure-open_access`; если нет или истёк — читает
   `__Secure-open_session` и делает один общий refresh на сессию.
4. `oidc` проверяет подпись, `iss`, `aud`, `exp`, `typ=Bearer`.
5. `policy` отвечает: пускать / `403` / `401`. Анонима на браузерном пути — `302` на
   `/auth/login?return_to=…`; на `/api/*` и `/users*` — `401` JSON.
6. `edge` срезает входящие identity-заголовки, инжектит свои, ставит `X-Forwarded-*`.
7. `edge` проксирует на upstream с таймаутами хоста; `101` проходит без правок.

## Переменные окружения

| Переменная | Обязательна | Назначение |
|---|---|---|
| `GATEWAY_CONFIG` | да | путь к `config.yaml` |
| `GATEWAY_SESSION_KEY` | да | 32 байта base64, ключ AES-GCM для cookie сессии |
| `IDP_CLIENT_SECRET` | да | секрет клиента `gateway` |
| `IDP_ADMIN_SECRET` | для `/admin/*` | секрет service account `gateway-admin` |
| `SWITCH_TOKEN` | для `/api/services` | инжектится в `X-Service-Token` |
| `LLM_API_KEY` | для `/api/chat` | инжектится в upstream для LiteLLM |
| `LOG_LEVEL` | нет | `info` по умолчанию |

Секреты приходят только из env. Строка секрета в `config.yaml` — ошибка валидации на
старте: конфиг лежит в git.

## Деплой

```yaml
# deploy/compose.yaml (фрагмент)
gateway:
  build: ../gateway
  command: ["--config", "/etc/gateway/config.yaml"]
  environment:
    GATEWAY_SESSION_KEY: ${GATEWAY_SESSION_KEY}
    IDP_CLIENT_SECRET: ${IDP_CLIENT_SECRET}
    IDP_ADMIN_SECRET: ${IDP_ADMIN_SECRET}
    SWITCH_TOKEN: ${SWITCH_TOKEN}
    LLM_API_KEY: ${LLM_API_KEY}
  volumes: [ ../gateway/config.yaml:/etc/gateway/config.yaml:ro ]
  ports: [ "127.0.0.1:8080:8080" ]
  networks: [ open_network, models_network, llm_network, rag_edge, common_network, deploy_auth_network ]
```

Сети продуктов подключаются только те, чьи upstream'ы описаны в конфиге: имя контейнера
резолвится лишь в общей с ним сети. Лишняя сеть — лишняя поверхность атаки, поэтому
список сетей ревьюится вместе с `config.yaml`.

## Проверка

```bash
# 1. валидация конфига и политик без сети
go test ./internal/config/ ./internal/policy/

# 2. юнит-тесты BFF на httptest с поддельным idp
go test ./internal/bff/ ./internal/session/

# 3. живой стенд: матрица хост × путь × роль
GATEWAY_PROBE=https://filenkov.store scripts/verify-edge.sh

# 4. процесс
curl -fsS http://127.0.0.1:8080/healthz   # liveness
curl -fsS http://127.0.0.1:8080/readyz    # discovery + JWKS получены
```

`readyz` не проверяет upstream'ы: недоступный `grafana` не должен выводить edge из
ротации. Доступность продуктов меряется их собственными health-путями через `proxy`.
