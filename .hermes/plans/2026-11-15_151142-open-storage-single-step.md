# Open-Storage: переписывание слоя идентичности и edge — план в один шаг

> **Для Hermes:** спецификация — `docs/services/**` (уже в репозитории). План задаёт
> порядок работ и критерии приёмки. Код пишется по спецификации, а не по этому файлу.

**Цель:** новый слой аутентификации и edge для всех хостов `filenkov.store` — четыре
контейнера (proxy, gateway, idp, idp_db), без собственного IdP, без каталога-сервиса, без
Redis, без совместимости с прошлым контрактом.

**Архитектура:** Caddy завершает TLS и отдаёт один upstream на хост. Go-gateway (≤2000
строк) — OIDC BFF, проверка RS256 по JWKS, политика маршрутов, инъекция личности,
реверс-прокси, `/admin` поверх Keycloak Admin API. Keycloak 26.8.x — единственный источник
личности, ролей и сессий, конфигурация только через `idp/realm.json`. Витрина — статика.

**Стек:** Go 1.26 (stdlib + yaml.v3 + coreos/go-oidc/v3), Keycloak 26.8.2 (Quarkus),
Postgres 17, Caddy 2.11.4, Vite 7 + React 19 + TypeScript, podman-compose 5.7.

---

## Что значит «в один шаг»

Один релиз, один момент переключения. **Нет**: фаз миграции, параллельного
функционирования, флагов совместимости, переноса данных из Auth-Service/User-Service,
сохранения старых UUID, поддержки `X-User-Id`/`X-Storage-Role`, двух версий контракта.

**Есть**: последовательность задач сборки (это порядок производства работ, а не этапы
внедрения), затем одна остановка старого стека и один старт нового.

Страховка (не фаза, а операция): старый стек остаётся `podman compose stop`-нутым с
томами 7 дней. Возврат = `up -d` старого + откат `proxy/Caddyfile` из git.

## Итоговое состояние

| Контейнер | Образ | Порт | Роль |
|---|---|---|---|
| `proxy` | caddy:2.11 | 80/443 | TLS, HSTS, один upstream на хост |
| `gateway` | `open/gateway` | 8080 (127.0.0.1) | BFF, политика, прокси, `/admin` |
| `idp` | keycloak:26.8.2 | 8080 (внутр.) | личность, роли, сессии |
| `idp_db` | postgres:17 | 5432 (внутр.) | состояние Keycloak |
| `resume` | `open/resume-page` | 8080 (внутр.) | витрина + `/admin` UI |

Девять хостов: `filenkov.store`, `storage.`, `image.`, `rag.`, `audio.`, `llm.`,
`observer.`, `meet.`, `id.`. Вне SSO (свои сайт-блоки): `hermes.`, `lite-llm.`.

## Предпосылки

- [ ] Google OAuth client создан заново: redirect URI **только**
      `https://id.filenkov.store/realms/filenkov/broker/google/endpoint`
- [ ] Секреты в `deploy/.env` (вне git): `GATEWAY_SESSION_KEY` (32 байта b64),
      `IDP_DB_PASSWORD`, `IDP_BOOTSTRAP_*`, `IDP_CLIENT_SECRET`, `IDP_ADMIN_SECRET`,
      `GOOGLE_CLIENT_ID/SECRET`, `SWITCH_TOKEN`, `LLM_API_KEY`
- [ ] DNS `id.filenkov.store` → адрес хоста (A-запись или dnsmasq)
- [ ] Порты 80/443 свободны: старый Caddy остановлен на время переключения
- [ ] `podman network create open_network` (или в compose как внешнюю не делать — сеть
      создаёт `deploy/compose.yaml`)

## Задачи

### T1. Каркас репозитория
**Файлы:** `gateway/go.mod`, `gateway/cmd/gateway/main.go`, `deploy/compose.yaml`,
`deploy/.env.example`, `Makefile`, `.gitignore` (+ `deploy/.env`).
**Проверка:** `go build ./...` в `gateway/` проходит на пустом `main`; `podman compose -f
deploy/compose.yaml config` валиден; `.env` в `.gitignore`, `.env.example` — нет.

### T2. Конфиг и его валидация
**Файлы:** `gateway/config.yaml` (полный пример из `docs/services/gateway/config.md`),
`gateway/internal/config/{config.go,routes.go,validate.go,table_test.go}`.
**Действие:** типы, загрузка YAML, компиляция маршрутов, восемь правил fail-fast.
**Проверка:** `go test ./internal/config/` — таблица «хост×путь×метод» и тесты на каждое
правило: нет `/**`, недостижимый маршрут, дубль, неизвестный upstream, неизвестный
сервис, секрет вместо `env:`, пересечение `aliases`, пустой путь после `strip_prefix`.

### T3. OIDC-верификатор
**Файлы:** `gateway/internal/oidc/{provider.go,claims.go,provider_test.go}`.
**Действие:** discovery, JWKS-кэш по `kid` (TTL 15m), `Verify(access) → Identity{Subject,
Email, Name, Roles, SID}`, проверки `iss`/`aud`/`exp`/`typ`.
**Проверка:** юнит-тесты на поддельном JWKS: валидный токен, битая подпись, чужой `aud`,
истёкший `exp`, неизвестный `kid` → повторная загрузка ключей (ровно один раз).

### T4. Сессия и cookie
**Файлы:** `gateway/internal/session/{seal.go,refresh.go,refresh_test.go}`.
**Действие:** AES-256-GCM seal/open, три cookie (`__Secure-open_access`,
`__Secure-open_session`, `__Secure-open_flow`), single-flight refresh по `sub`.
**Проверка:** тесты: подделка cookie (не расшифровывается), истёкшая сессия,
`invalid_grant` → cookie чистятся, два параллельных refresh → один обмен, оба запроса
получают валидный ответ.

### T5. Политика
**Файлы:** `gateway/internal/policy/{policy.go,policy_test.go}`.
**Действие:** `public | session | admin | deny | service(svc[, level…])` → решение
`allow/deny` по `Identity`.
**Проверка:** таблица «роли × политика»: `stranger` vs `family` vs `admin` vs
`blocked`, `service(storage,admin)` без `family`, `deny` на любые роли.

### T6. Edge: матчинг, заголовки, прокси
**Файлы:** `gateway/internal/edge/{router.go,headers.go,proxy.go,log.go,metrics.go}`,
`gateway/internal/edge/{headers_test.go,proxy_test.go}`.
**Действие:** матчинг, стрип `X-Auth-*`/`X-User-Id`/`X-Storage-Role`, инъекция
канонического набора, `X-Forwarded-*`, реверс-прокси с per-host таймаутами, WS-апгрейд,
JSON-ошибки, access-лог, `/healthz`, `/readyz`, `/metrics`.
**Проверка:** тесты на `httptest`-upstream: заголовки от клиента срезаны; `101` проходит;
SSE не буферизуется; таймаут хоста даёт `504`; `deny` → `404`; `401` vs `302`
(по `Accept`/`X-Requested-With`/префиксу `/api/`).

### T7. BFF
**Файлы:** `gateway/internal/bff/{login.go,callback.go,logout.go,session.go,bff_test.go}`.
**Действие:** как в `docs/services/gateway/bff.md`, включая allowlist `return_to`,
одноразовый `state`, `nonce`, PKCE S256, `Origin`-проверку на logout.
**Проверка:** тесты: невалидный `return_to` уходит на `public_origin`; чужой `state`
→ `302` с `auth_error`; `nonce` не совпал → отказ; logout без `Origin` → `403`.

### T8. Admin API
**Файлы:** `gateway/internal/adminapi/{users.go,roles.go,admin_test.go}`.
**Действие:** `/admin/users`, `/admin/users/{id}/roles/{svc}`, `PATCH` enabled,
`PUT …/admin`, проверки последнего админа и админа сервиса.
**Проверка:** тесты на поддельном Keycloak Admin API: `409 LAST_ADMIN`, чужой сервис →
`403`, `svc=admin` через сервисный путь → `400`, `level: null` снимает роль.

### T9. Realm как код
**Файлы:** `idp/realm.json`, `idp/theme/filenkov/{login/theme.properties,login/resources/css/filenkov.css}`.
**Действие:** realm `filenkov` по `docs/services/idp/README.md`: Google IdP (`IMPORT`,
`kc_idp_hint`), `emailAsUsername`, запрет дублей email, два клиента (`gateway`,
`gateway-admin`), роли `admin` + `svc:*` для четырёх сервисов (`storage`, `image`, `rag`,
`audio`), TTL 5m/7d/30d, brute-force.
**Проверка:** `jq -e '.realm, .identityProviders[0].alias, .clients[].clientId' idp/realm.json`;
старт `idp` на пустом томе; `curl .well-known/openid-configuration | jq -r .issuer`.

### T10. Скрипты бутстрапа и проверки
**Файлы:** `scripts/grant-admin.sh`, `scripts/verify-edge.sh`, `scripts/golden.sh`.
**Действие:** `grant-admin.sh <email>` (Admin API, пароль из env, нигде не печатается);
`verify-edge.sh` — по одному запросу на каждый из девяти хостов через `proxy` и напрямую
в `gateway` (сравнивает слои отдельно).
**Проверка:** `shellcheck scripts/*.sh`; прогон на собранном стенде.

### T11. Витрина
**Файлы:** `resume-page/` (Vite-проект по `docs/services/resume-page/README.md`),
`resume-page/nginx.conf`, `resume-page/Dockerfile`.
**Действие:** дерево нод с `import.meta.glob`, `useSession`, страница `/auth`, `/admin`
(таблица без пагинации), бюджет 95 KB, `try_files`.
**Проверка:** `npm run build` (инварианты реестра + бюджет), `npm test`, глубокий URL
отдаёт `index.html`.

### T12. Proxy
**Файлы:** `proxy/Caddyfile` (по `docs/services/proxy/README.md`).
**Действие:** девять SSO-сайт-блоков на `gateway:8080`, `meet` — `tls internal` +
`remote_ip`, два сайта вне контракта (`hermes`, `lite-llm` → локальные порты),
HTTP→HTTPS-список, `protocols h1 h2`.
**Проверка:** `caddy validate --config proxy/Caddyfile`; `curl -I https://<host>` даёт HSTS;
`http://` → `308 https://`.

### T13. Compose и запуск стенда
**Файлы:** `deploy/compose.yaml`, `Makefile` (`up`, `down`, `rebuild`, `verify`).
**Действие:** пять сервисов, сети (`open_network` + продуктовые, только для upstream'ов из
конфига), healthchecks, лимиты памяти, тома `idp_pgdata`/`caddy_data`.
**Проверка:** с нуля (`podman compose down -v && make up`) стенд поднимается за ≤90 с;
`/readyz` = 200; `make verify` зелёный.

### T14. Перевести потребителей на контракт v1
**Файлы (вне Open-Storage, по одной правке на проект):**
| Проект | Что меняется |
|---|---|
| WebStorage | `X-User-Id`/`X-Storage-Role` → `X-Auth-Subject`/`X-Auth-Roles`; ключ vault: `auth_session` cookie → `X-Auth-Session` |
| RAG-Chat | `X-Auth-User-Id` → `X-Auth-Subject`; `X-Auth-Role` → разбор `X-Auth-Roles` |
| ASR-Service | `X-Auth-User-Id` → `X-Auth-Subject` |
| qwen-image-service | `X-Auth-User-Id`/`Name`/`Email` → новые имена |
| Switch-Service | без изменений (`X-Service-Token` инжектит edge) |
| hermes-auth-gateway | выводится из эксплуатации: `hermes.filenkov.store` идёт мимо SSO |

**Проверка:** в каждом проекте — тест, читающий новые заголовки; grep по старым именам
(`X-User-Id|X-Storage-Role|X-Auth-User-Id`) возвращает пусто; вход и одна реальная операция
(загрузка файла в WebStorage, вопрос в RAG, транскрипт в ASR, генерация картинки) —
руками, под своей учёткой.

### T15. Приёмка стенда (до переключения)
**Действие:** прогнать матрицу из `scripts/verify-edge.sh` + ручные сценарии.
**Обязательные проверки:**
```bash
# гость → 302 на вход, API → 401
curl -s -o /dev/null -w '%{http_code}\n' https://storage.filenkov.store/
curl -s -o /dev/null -w '%{http_code}\n' https://storage.filenkov.store/api/files
# вход и профиль
curl -s -c /tmp/jar -b /tmp/jar -L 'https://filenkov.store/auth/login?return_to=https%3A%2F%2Ffilenkov.store%2F' >/dev/null
curl -s -b /tmp/jar https://filenkov.store/auth/session | jq
# чужой return_to не проходит
curl -s -o /dev/null -w '%{http_code}\n' 'https://filenkov.store/auth/login?return_to=https%3A%2F%2Fevil.example.com%2F'
# роли: stranger 403, family 200 (на выданной учётке)
curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/jar https://image.filenkov.store/
# последний админ
curl -s -o /dev/null -w '%{http_code}\n' -X PUT -b /tmp/jar -H 'Content-Type: application/json' -d '{"value":false}' https://filenkov.store/admin/users/$SUB/admin
# WS (Grafana Live, Jitsi signaling) и SSE (rag chat) живут дольше 5 минут
```
**Критерий:** все девять хостов отвечают ожидаемым кодом на анонима/вошедшего/админа;
`403` отдаёт JSON, а не HTML; в логах `gateway` нет токенов.

### T16. Переключение (единственный «шаг»)
```bash
systemctl stop caddy                       # старый TLS-слой
podman compose -f ~/projects/Auth-Service/deploy/docker-compose.yml stop
podman compose -f ~/projects/User-Service/compose.yaml stop
systemctl start caddy                      # новый Caddy → proxy/Caddyfile → gateway:8080
make -C ~/projects/Open-Storage verify
```
**Критерий:** `make verify` зелёный, вход через Google на трёх разных хостах, реальная
операция в каждом из четырёх продуктов.

### T17. Снос старого
**Действие:** через 7 дней — `podman compose down -v` для Auth-Service/User-Service,
удаление `~/projects/Auth-Service`, `~/projects/User-Service`, `hermes-auth-gateway` из
эксплуатации, чистка DNS/сайт-блоков, которых больше нет.
**Критерий:** `grep -rn 'auth_access\|auth_refresh\|auth_session\|X-User-Id' ~/projects
--include='*.go' --include='*.py' --include='*.yaml' --include='*.conf'` пуст (кроме
историй в docs).

### T18. Документация = реальность
**Действие:** `docs/services/**` обновляется в том же коммите, что и код. Расхождение
спецификации и конфига — дефект, а не «потом поправлю».
**Проверка:** `gateway/config.yaml` совпадает с примером в `docs/services/gateway/config.md`;
список сервисов в `services:` совпадает с `docs/services/idp/roles.md`; роли в
`idp/realm.json` совпадают с таблицей.

## Риски

| Риск | Что делать |
|---|---|
| Потребители не обновлены к моменту переключения | T14 идёт **до** T16; критерий — grep по старым именам пуст |
| Потеря доступа (нет админа) | `grant-admin.sh` + доступ к консоли Keycloak мимо политики gateway; проверить до переключения |
| Jitsi/Grafana ломаются на WS | проверка длинной сессии WS в T15, а не после |
| Микрофон/камера отваливаются | `permissions_policy` только в `gateway`; проверить, что `curl -I` не содержит дубля |
| Утечка секрета в конфиг | валидация T2 отвергает не-`env:` значения; `deploy/.env` в `.gitignore` |
| Нет отката | старый стек остановлен, но не удалён 7 дней; `proxy/Caddyfile` в git |

## Definition of Done

- [ ] `make up` с нуля поднимает стенд ≤90 с, `/readyz` = 200
- [ ] `make verify` зелёный: девять хостов × {аноним, вошедший, админ}
- [ ] вход через Google, один на все хосты; выход рвёт сессию и привязанные к `sid` данные
- [ ] роль, выданная в `/admin`, действует в течение 5 минут; снятая — тоже
- [ ] последний админ не снимается (`409`), админ сервиса не правит чужой сервис (`403`)
- [ ] `go test ./...`, `npm test`, `caddy validate` — зелёные
- [ ] в `gateway` ≤2000 строк Go; нет Redis, нет сервиса-каталога, нет `X-User-Id`
- [ ] `docs/services/**` соответствует коду; план закрыт
