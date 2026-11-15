# Сервисы Open-Storage

Слой идентичности и edge. Четыре компонента, у каждого свой каталог документации в
`docs/services/` и свой каталог исходников в корне репозитория — один к одному.

| Компонент | Исходники | Отвечает за | Не делает |
|---|---|---|---|
| **proxy** | `proxy/Caddyfile` | TLS 1.2/1.3, HTTP→HTTPS, единственный публичный слушатель :80/:443, HSTS | маршрутизацию по приложениям, авторизацию, заголовки приложений |
| **gateway** | `gateway/` (Go) | OIDC BFF (`/auth/*`), проверку access-токена, политику маршрутов, инъекцию личности, реверс-прокси, `/admin/*` | хранение пользователей, выдачу токенов, хранение сессий |
| **idp** | `idp/` (Keycloak + realm.json) | единственный источник личности: Google broker, токены, сессии, роли, блокировка | проксирование, маршрутизацию, знание о хостах |
| **resume-page** | `resume-page/` (Vite/React) | витрину-дерево `filenkov.store` и UI `/admin` | хранение токенов, собственную авторизацию, знание о секретах |

## Поток запроса

```
Браузер
  │  https://storage.filenkov.store/files
  ▼
proxy (Caddy, :443)                 TLS, HSTS. Один upstream на хост → gateway:8080
  ▼
gateway (:8080)                     Host+Path → маршрут → политика
  ├─ токена нет / протух  → 302 на https://filenkov.store/auth/login?return_to=… (или 401 JSON для /api/*)
  ├─ токен есть           → проверка RS256 по JWKS idp, роли из claim'ов
  ├─ политика не пускает  → 403 JSON
  └─ пускает              → стрип входящих X-Auth-*, инъекция личности, прокси на upstream
  ▼
app:8000 / audio-api:8000 / rag-edge:8080 / qwen-image:8000 / qwen38:4001 / grafana:3000 / jitsi-web:8000
```

Вход и выход идут только через `gateway`:

```
/auth/login    → 302 на id.filenkov.store/realms/filenkov/protocol/openid-connect/auth?kc_idp_hint=google
/auth/callback ← code → обмен (PKCE + client_secret) → проверка id_token → cookie → 302 на return_to
/auth/logout   → revoke refresh в idp → end-session → чистит cookie
```

## Сеть и порты

| Контейнер | Порт | Публикация | Сеть |
|---|---|---|---|
| `proxy` | 80, 443 | `0.0.0.0` + адрес WG | `open_network` |
| `gateway` | 8080 | `127.0.0.1:8080` (только для проб и метрик) | `open_network` + сети продуктов |
| `idp` | 8080 | нет | `open_network` |
| `idp_db` | 5432 | нет | `open_network` |
| `resume` | 80 | нет | `open_network` |

Состояния в `gateway` нет: ни Redis, ни своей БД. Сессия — запечатанная AES-GCM cookie,
её содержимое — refresh-токен Keycloak. Всё, что нужно помнить, помнит `idp`.

## Контракт личности

Ровно одна версия — **v1**, без флагов совместимости и без легаси-имён. Полное описание:
[gateway/identity-contract.md](gateway/identity-contract.md). Кратко:

- вниз уходит `Authorization: Bearer <access JWT>` (RS256, JWKS у `idp`);
- рядом — `X-Auth-Subject`, `X-Auth-Email`, `X-Auth-Name`, `X-Auth-Roles`, `X-Auth-Session`;
- любой входящий `X-Auth-*`, `X-User-Id`, `X-Storage-Role` срезается до инъекции;
- роли приходят в токене: `admin`, `svc:<service>:<level>`. Запросов «а какая у него роль»
  к отдельному сервису нет — каталога ролей, кроме `idp`, не существует.

## Что отвергнуто на уровне платформы

| Отвергнуто | Почему |
|---|---|
| HS256 + общий секрет | токен нельзя проверить вне одного сервиса; рокировка секрета = перевыпуск всех сессий |
| Отдельный сервис-каталог (User-Service) | второй сервис в горячем пути ради двух SELECT'ов; заменяется ролями в токене |
| Redis для сессий/ревокации | у `idp` уже есть сессии, logout-all и not-before; второго хранилища состояния не нужно |
| JWT в браузере (PKCE-SPA) | токены в JS, CORS на каждый API, третьесторонние cookie; BFF держит их в httpOnly |
| Легаси-имена `X-User-Id` / `X-Storage-Role` | дублирующий контракт, из-за которого приложение должно знать, кто его вызвал |
| Версии контракта v2… | одно развёртывание, одна версия; ломающее изменение = правка всех потребителей в том же релизе |

## Документы

- [idp/README.md](idp/README.md), [idp/roles.md](idp/roles.md), [idp/operations.md](idp/operations.md)
- [gateway/README.md](gateway/README.md), [gateway/config.md](gateway/config.md),
  [gateway/bff.md](gateway/bff.md), [gateway/identity-contract.md](gateway/identity-contract.md),
  [gateway/admin.md](gateway/admin.md), [gateway/operations.md](gateway/operations.md),
  [gateway/decisions.md](gateway/decisions.md)
- [proxy/README.md](proxy/README.md), [proxy/operations.md](proxy/operations.md)
- [resume-page/README.md](resume-page/README.md)
