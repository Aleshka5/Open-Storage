# gateway — эксплуатация

## Инварианты, которые нельзя «оптимизировать»

Эти правила выглядят как детали, но каждое ломает конкретный живой сценарий. Они
зафиксированы тестами, а не комментариями.

| Инвариант | Что сломается, если нарушить |
|---|---|
| `ForceAttemptHTTP2: false` на транспорте к upstream | h2 не умеет `Upgrade` — WebSocket-хендшейк отваливается |
| `FlushInterval: -1` в реверс-прокси | SSE и стрим токенов буферизуются, чат «висит» и приходит целиком |
| Нет `ReadTimeout`/`WriteTimeout` на сервере | дедлайны переживают hijack и рвут длинные WS-туннели; `ReadHeaderTimeout` и `IdleTimeout` — безопасны |
| В обёртке статуса есть `Hijack`, `Flush`, `Unwrap` | обёртка для access-лога ломает апгрейд, статус не пишется как `101` |
| `ModifyResponse` выходит сразу на `101` | HSTS/X-Frame-Options, навешенные на handshake, рвут апгрейд |
| Заголовки безопасности не ставятся на `Upgrade: websocket` | то же |
| Стрип identity-заголовков вызывается **до** инъекции и до прокси | клиент может подставить `X-Auth-Subject` и стать кем угодно |

## Health, метрики, логи

| Путь | Смысл |
|---|---|
| `GET /healthz` | процесс жив, конфиг валиден |
| `GET /readyz` | discovery `idp` получен и JWKS загружен; иначе `503` |
| `GET /metrics` | Prometheus, только `127.0.0.1` |

`/readyz` намеренно **не** проверяет upstream'ы: упавший `grafana` не должен выводить
edge из балансировки. Доступность продуктов проверяется их `/health` через `proxy`.

Метрики (минимальный набор, больше не нужно):

```
gateway_requests_total{host,route,policy,status}
gateway_request_duration_seconds{host,route}
gateway_token_refresh_total{result}      ok | invalid_grant | error
gateway_idp_request_total{op,status}     discovery | jwks | token | admin
gateway_ws_active{host}
```

Access-лог — одна JSON-строка на запрос: `ts, host, method, path, route, policy, status,
dur_ms, sub, ip, ua`. Токены, коды, cookie и `Authorization` не логируются никогда.

## Рестарт и применение изменений

```bash
# конфиг (маршруты, таймауты, политики) — монтируется read-only
podman restart gateway && curl -fsS http://127.0.0.1:8080/readyz

# новая сборка
podman compose -f deploy/compose.yaml up -d --build gateway

# проверка после любого изменения
scripts/verify-edge.sh
```

Hot-reload конфига не поддерживается: половина применённого конфига опаснее явного
рестарта (рестарт edge не разлогинивает — состояние в cookie, а не в памяти).

## Rate limit

`defaults.rate_limit` — 600 запросов/минуту на IP, per-host override при необходимости.
Счётчик в памяти процесса (token bucket), при нескольких репликах он станет
некорректным — но реплик нет и не планируется. За `idp` собственный brute-force
(`failureFactor: 5`) — дублировать его на edge не нужно.

## Заголовки: кто что ставит

| Заголовок | Ставит | Почему там |
|---|---|---|
| `Strict-Transport-Security` | `proxy` | он единственный знает, что запрос пришёл по TLS |
| `Permissions-Policy` | `gateway` (per-host) | политика зависит от хоста (микрофон/камера), а хосты знает gateway |
| `X-Content-Type-Options`, `Referrer-Policy` | `gateway` | одинаковы, но зависят от ответа upstream |
| `X-Frame-Options: DENY` | `gateway`, кроме `meet`/`audio` | Jitsi и ASR встраиваются в свой же контекст |
| `X-Forwarded-*` | `proxy` → `gateway` (перезапись) | gateway должен видеть настоящий `Host` |

Правило: один заголовок ставит один компонент. Дубль в ответе — всегда баг: браузер
пересекает политики, и разрешение из одного слоя отменяется запретом из другого (так
уже ломались микрофон и камера).

## Runbook

| Симптом | Слой | Что проверить |
|---|---|---|
| `alert internal error`, `curl: (35)` | `proxy` | нет сайт-блока или сертификата: `caddy validate`, `grep <fqdn> proxy/Caddyfile` |
| `404 {"error":"not_found"}` | `gateway` | нет хоста/маршрута в `config.yaml`: `curl -H 'Host: <fqdn>' http://127.0.0.1:8080/<path>` |
| `502 {"error":"bad_gateway"}` | upstream | имя не резолвится или порт не тот: `podman exec gateway wget -qO- http://<upstream>/` |
| `302` по кругу на `/auth/login` | `gateway`↔`idp` | `return_to`/`redirect_uri` не совпадает с настройкой клиента; cookie не ставится (проверить `Domain`, `Secure`, часы) |
| `401` на всё, хотя вход прошёл | `idp` | `aud`/`iss` не совпадают с конфигом; `podman logs gateway \| grep token` |
| `403 {"error":"forbidden"}` у своего | роли | `curl -b jar /auth/session \| jq .roles` — есть ли `svc:<svc>:family` |
| WS рвётся через минуту | сервер | кто-то добавил `WriteTimeout`; см. инварианты |
| Долгая загрузка отдаёт `504` | таймаут хоста | `timeouts.response_header` у хоста |
| Медленно всё | `idp` | JWKS TTL истёк и каждый запрос ходит за ключами: смотреть `gateway_idp_request_total` |

## Ресурсы

- Память: 48 MiB достаточно (Go, без кэша тел); лимит в compose — 128 MiB.
- CPU: проксирование без буферизации, ограничение `cpus: 1` проверено на 30 одновременных
  загрузках.
- Диск: не пишет ничего.

## Бэкап

Бэкапить нечего: конфиг в git, состояние в `idp`. `GATEWAY_SESSION_KEY` хранится в
env-файле вне git; его потеря = разлогин всех, но не потеря данных.
