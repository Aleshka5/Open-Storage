# idp — Keycloak

Единственный источник личности в Open-Storage. Держит пользователей, роли, сессии и
токены. Не знает ни про хосты, ни про маршруты, ни про то, какие приложения существуют.

- Образ: `quay.io/keycloak/keycloak:26.8.2` (пин по тегу, апгрейд — осознанное действие)
- Порт: `8080` внутри `open_network`, публично только через `proxy` на
  `https://id.filenkov.store`
- БД: `idp_db` (Postgres 17), том `idp_pgdata`
- Исходники конфигурации: `idp/realm.json`, `idp/theme/`
- Режим: `start --optimized`, realm импортируется при старте из `/opt/keycloak/data/import`

## Что настроено

| Объект | Значение | Зачем |
|---|---|---|
| Realm | `filenkov` | один realm на все хосты, отдельного tenant-разделения нет |
| Identity Provider | `google`, `syncMode: IMPORT`, `kc_idp_hint=google` | единственный способ входа; форма Keycloak не показывается |
| First broker login flow | `create user if unique` + `confirm link` отключён | первый вход создаёт пользователя без диалогов |
| Регистрация | выключена | новых пользователей создаёт только Google-вход |
| `emailAsUsername` | `true` | username = email: уникальность бесплатно, без логики коллизий |
| Дубли email | запрещены (`duplicateEmailsAllowed: false`) | одна личность = один email |
| Клиент `gateway` | confidential, standard flow, PKCE S256, redirect `https://filenkov.store/auth/callback` | BFF в gateway |
| Клиент `gateway-admin` | confidential, service account, роли `view-users`, `manage-users`, `query-users`, `view-realm` | `/admin/*` в gateway через Admin API |
| Клиент `account` | выключен | своим UI аккаунта не пользуемся |
| Тема | `filenkov` | минимум: логотип, язык, без лишних ссылок |

Токены: RS256, `iss=https://id.filenkov.store/realms/filenkov`, JWKS на
`/realms/filenkov/protocol/openid-connect/certs`. Claim'ы, которые реально читаются:
`sub`, `email`, `name`, `preferred_username`, `realm_access.roles`, `sid`, `exp`, `aud`.

## Времена жизни

| Что | Значение | Почему |
|---|---|---|
| Access token | **5m** | его нельзя отозвать; короткое окно — единственный честный способ |
| SSO session idle | **7d** | «залогинился и забыл» — норма для домашнего стенда |
| SSO session max | **30d** | дальше — повторный вход через Google |
| Refresh rotation | включён, `revokeRefreshToken=true` | украденный refresh живёт один обмен |
| Access token в cookie | 5m, обновляется gateway'ем молча | пользователь не видит пересессий |

Ревокация: `POST /admin/realms/filenkov/users/{id}/logout` (все сессии) + not-before по
пользователю — это и есть «забанить прямо сейчас». Отдельного списка отозванных токенов
нет и не нужно: access живёт 5 минут.

## Роли

Модель и именование — [roles.md](roles.md). Кратко: `admin` + `svc:<service>:<level>`,
`stranger` = отсутствие роли, глобальная блокировка = `enabled: false`.

## Чего в Keycloak нет и что с этим делать

| Нужно | В Keycloak | Решение |
|---|---|---|
| Бутстрап первого админа | счётчик «первый пользователь» отсутствует | `scripts/grant-admin.sh <email>` один раз после первого входа |
| Запрет снять роль с последнего админа | нет | проверка в `gateway` (`PUT /admin/...` отвечает `409 LAST_ADMIN`) |
| «Админ сервиса правит только свой сервис» | fine-grained admin permissions есть, но тяжеловесны | проверка в `gateway`: `admin` или `svc:<svc>:admin` |
| Список пользователей в своём UI | Admin API | `gateway` → `GET /admin/users` |

Правило: всё, что относится к «кто кого может править», живёт в `gateway`; всё, что
относится к «кто ты и какие у тебя роли», живёт здесь.

## Деплой

```bash
# deploy/compose.yaml (фрагмент)
idp_db:
  image: postgres:17-alpine
  environment: { POSTGRES_DB: keycloak, POSTGRES_USER: keycloak, POSTGRES_PASSWORD: ${IDP_DB_PASSWORD} }
  volumes: [ idp_pgdata:/var/lib/postgresql/data ]
  networks: [ open_network ]

idp:
  image: quay.io/keycloak/keycloak:26.8.2
  command: [ start, --optimized, --import-realm ]
  environment:
    KC_DB: postgres
    KC_DB_URL: jdbc:postgresql://idp_db:5432/keycloak
    KC_DB_USERNAME: keycloak
    KC_DB_PASSWORD: ${IDP_DB_PASSWORD}
    KC_HOSTNAME: https://id.filenkov.store
    KC_HTTP_ENABLED: "true"
    KC_PROXY_HEADERS: xforwarded
    KC_BOOTSTRAP_ADMIN_USERNAME: ${IDP_BOOTSTRAP_USER}
    KC_BOOTSTRAP_ADMIN_PASSWORD: ${IDP_BOOTSTRAP_PASSWORD}
    GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
    GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
  volumes:
    - ../idp/realm.json:/opt/keycloak/data/import/realm.json:ro
    - ../idp/theme/filenkov:/opt/keycloak/themes/filenkov:ro
  depends_on: [ idp_db ]
  networks: [ open_network ]
```

Google Cloud Console: OAuth client «Web application», authorized redirect URI ровно один —
`https://id.filenkov.store/realms/filenkov/broker/google/endpoint`. Никаких
`filenkov.store/oauth/google/callback` больше нет.

`KC_BOOTSTRAP_ADMIN_*` действует только при пустой БД: после первого старта удалить
переменные из env-файла, админский доступ к консоли — через `admin`-роль обычного
пользователя на `https://id.filenkov.store/admin/` (доступ к консоли у host-only пути
`/admin/**` с политикой `admin`).

## Проверка

```bash
curl -fsS https://id.filenkov.store/realms/filenkov/.well-known/openid-configuration | jq -r .issuer
curl -fsS https://id.filenkov.store/realms/filenkov/protocol/openid-connect/certs | jq '.keys[0].alg'  # RS256
```

Приёмка: вход через Google создаёт пользователя с `emailAsUsername`, `sub` стабилен между
входами, второй вход не создаёт второго пользователя, `enabled=false` рвёт вход и сессии.
