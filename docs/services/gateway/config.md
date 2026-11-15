# gateway — конфигурация

`gateway/config.yaml` — единственное место, где описан edge: хосты, маршруты, политики,
таймауты. Файл лежит в git, монтируется read-only, читается только на старте (изменение =
рестарт, hot-reload сознательно не делается: половина применённого конфига хуже старого).

Секретов в файле нет: значения только как `env:NAME`.

## Схема

```yaml
listen: ":8080"
public_origin: "https://filenkov.store"

idp:
  issuer: "https://id.filenkov.store/realms/filenkov"
  client_id: "gateway"
  client_secret: "env:IDP_CLIENT_SECRET"
  scopes: [openid, profile, email]
  audience: "account"          # access-токен Keycloak по умолчанию имеет aud=account
  authorized_party: "gateway"  # azp обязан совпадать: токен выпущен нашему клиенту
  jwks_ttl: 15m

session:
  cookie_domain: ".filenkov.store"
  access_ttl: 5m            # совпадает с access-токеном Keycloak
  idle_ttl: 168h            # сколько живёт cookie сессии
  key: "env:GATEWAY_SESSION_KEY"

admin:
  client_id: "gateway-admin"
  client_secret: "env:IDP_ADMIN_SECRET"

# Только сервисы с per-service ролями. Хаб, llm, observer и meet живут на глобальных
# политиках (public/admin/session) и ролей не имеют: колонка в /admin без смысла — лишний UI.
services: [storage, image, rag, audio]

defaults:
  timeouts: { connect: 5s, read_header: 15s, response_header: 60s, idle: 120s }
  rate_limit: { requests: 600, per: 1m }

upstreams:                  # имена резолвятся в DNS контейнерной сети
  resume: "resume:80"       # SPA (nginx:alpine, дефолтный порт)
  idp: "idp:8080"
  storage: "app:8000"
  image: "qwen-image:8000"
  llm: "qwen38:4001"
  rag: "rag-edge:8080"
  audio: "audio-api:8000"
  audio_web: "frontend:80"
  grafana: "grafana:3000"
  jitsi: "jitsi-web:8000"
  switch: "host.docker.internal:8095"
  litellm: "litellm-proxy-server:4000"

hosts:
  - host: filenkov.store
    aliases: []
    upstream: resume
    routes:
      # BFF: вход/выход/профиль. Внутренние обработчики gateway, не прокси.
      - { path: /auth/**, bff: true }
      # Каталог: список, роли, блокировка. Внутренний обработчик gateway.
      - { path: /admin/**, admin: true, policy: admin }
      # Совиный чат витрины: аноним здоровается, поэтому public + инъекция ключа.
      - { path: /api/chat, methods: [POST], upstream: litellm, policy: public,
          inject_headers: { X-Api-Key: "env:LLM_API_KEY" }, timeouts: { response_header: 60s } }
      # Управление моделями: чтение — любому вошедшему, переключение — админу.
      - { path: /api/services, methods: [GET], upstream: switch, policy: session,
          inject_headers: { X-Service-Token: "env:SWITCH_TOKEN" } }
      - { path: /api/services/**, upstream: switch, policy: admin,
          inject_headers: { X-Service-Token: "env:SWITCH_TOKEN" } }
      # Прямого доступа к каталогу нет: /admin проксирует Admin API на стороне gateway.
      - { path: /users/**, policy: deny }
      - { path: /** , upstream: resume, policy: public }

  - host: id.filenkov.store
    upstream: idp
    # Keycloak сам аутентифицирует консоль /admin/, поэтому здесь public целиком.
    # policy: admin тут сломал бы break-glass восстановление.
    routes:
      - { path: /**, policy: public }

  - host: storage.filenkov.store
    upstream: storage
    timeouts: { response_header: 30m }   # загрузка файлов: ответ ждать долго
    routes:
      - { path: /health, policy: public }
      - { path: /**, policy: "service(storage, family, admin)" }

  - host: image.filenkov.store
    upstream: image
    timeouts: { response_header: 30m }   # генерация отдаёт первый байт через минуты
    routes:
      - { path: /healthz, policy: public }
      - { path: /**, policy: "service(image, family, admin)" }

  - host: rag.filenkov.store
    upstream: rag
    timeouts: { response_header: 5m }    # загрузка PDF + стрим чата
    routes:
      - { path: /health, policy: public }
      - { path: /**, policy: "service(rag, family, admin)" }

  - host: audio.filenkov.store
    upstream: audio_web                  # оболочка SPA — статика, публична
    permissions_policy: "camera=(), microphone=(self), geolocation=()"
    timeouts: { response_header: 30m }   # диаризация идёт минутами
    routes:
      - { path: /health, upstream: audio, policy: public }
      - { path: /api/**, upstream: audio, policy: "service(audio, family, admin)" }
      - { path: /** }

  - host: llm.filenkov.store
    upstream: llm
    timeouts: { response_header: 10m }   # первый токен может идти долго
    routes:
      - { path: /**, policy: admin }

  - host: observer.filenkov.store
    upstream: grafana
    timeouts: { response_header: 5m }    # диапазоны по 30 дней на HDD-диске
    routes:
      - { path: /api/health, policy: public }
      - { path: /**, policy: session }   # + собственный логин Grafana сверху

  - host: meet.filenkov.store
    upstream: jitsi
    permissions_policy: "camera=(self), microphone=(self), display-capture=(self), geolocation=()"
    timeouts: { response_header: 5m }
    routes:
      - { path: /**, policy: session }
```

## Политики

| Выражение | Пропускает |
|---|---|
| `public` | всех, включая анонимов |
| `session` | аутентифицированного с живым (не выключенным) аккаунтом |
| `admin` | только `admin` |
| `service(<svc>)` | `svc:<svc>:family` или `svc:<svc>:admin` |
| `service(<svc>, admin)` | только `svc:<svc>:admin` |
| `deny` | никого (путь отвечает `404`, как будто его нет) |

`service(...)` включает в себя `session`: отдельно проверять вход не нужно.
`svc:<svc>:blocked` перекрывает `session`, если у хоста политика `session` — поэтому
выключенный от сервиса человек не получит и статику этого хоста.

## Маршрут

```yaml
- path: /api/**                 # литерал, /prefix/** или /**
  methods: [GET, POST]          # необязательно; по умолчанию все
  policy: "session"             # обязательно
  upstream: audio               # необязательно: переопределяет upstream хоста
  strip_prefix: /api            # необязательно: /api/notes → /notes
  bff: true                     # внутренний обработчик /auth/*
  admin: true                   # внутренний обработчик /admin/*
  inject_headers: { X-Service-Token: "env:SWITCH_TOKEN" }
  timeouts: { response_header: 30m }
```

Матчинг: первый подходящий маршрут выигрывает. Специфичные — выше общих.

## Валидация на старте (fail-fast)

Процесс не поднимается, если:

1. у хоста нет ровно одного `/**`, или `/**` стоит не последним;
2. маршрут недостижим (стоит после `/**` того же хоста);
3. два маршрута одного хоста с одинаковыми `path` + `methods` пересекаются;
4. `upstream` не объявлен в `upstreams` (кроме `bff`/`admin`);
5. `service(<svc>)` ссылается на сервис не из `services`;
6. значение похоже на секрет, а не на `env:NAME` (проверка префикса);
7. `aliases` хоста пересекаются с другим хостом;
8. `strip_prefix` делает путь пустым (`/api/**` + `strip_prefix: /api` на запросе `/api`).

Отдельный тест `internal/config/table_test.go` собирает матрицу
`хост × путь × метод × роль × состояние cookie` и сравнивает с ожидаемым вердиктом. Это
единственное место, где описано поведение edge; `handler_test.go` на 2000 строк, как в
прошлой реализации, не нужен.

## Почему такие таймауты

`response_header` — не «время жизни запроса», а ожидание **первого байта ответа**. Он
растёт там, где upstream сначала долго думает (загрузка файла, генерация картинки,
диаризация, диапазон по TSDB), и остаётся малым там, где ответ приходит сразу. Размер
тела запроса и длину SSE/WS он не ограничивает — для этого в `edge` нет
`ReadTimeout`/`WriteTimeout` (см. [operations.md](operations.md)).

## Добавить хост

1. строку в `upstreams`, блок в `hosts` с явным `/**`;
2. строку в `services`, если хост — продукт с ролями;
3. сайт-блок в `proxy/Caddyfile`;
4. `podman restart gateway` — конфиг монтируется, рестарт занимает доли секунды.
