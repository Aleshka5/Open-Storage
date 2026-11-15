# gateway — BFF (`/auth/*`)

Клиент OIDC, встроенный в edge. Браузер никогда не видит токен: ни в JS, ни в URL, ни в
логах. Gateway обменивает код на токены, держит их в httpOnly cookie и обновляет сам.

## Cookie

| Cookie | Содержимое | TTL | Флаги |
|---|---|---|---|
| `__Secure-open_access` | access JWT как есть | `session.access_ttl` (5m) | `HttpOnly; Secure; SameSite=Lax; Path=/; Domain=.filenkov.store` |
| `__Secure-open_session` | AES-256-GCM(`{sub, refresh_token, sid}`) | `session.idle_ttl` (168h) | то же |
| `__Secure-open_flow` | `{state, nonce, code_verifier, return_to}` | 10m | то же, ставится на время входа |

Префикс `__Secure-`, а не `__Host-`: cookie должна ходить на все поддомены (вход один на
девять хостов), а `__Host-` запрещает `Domain`. Ключ шифрования — `GATEWAY_SESSION_KEY`,
32 байта; ротация ключа разлогинивает всех (это осознанный способ «выйти везде», если
админский API недоступен).

В cookie сессии нет ни ролей, ни email: роли перечитываются из токена на каждом
запросе, поэтому снятие роли в `idp` действует максимум через 5 минут (время жизни
access). Долгий TTL сессии не даёт старым правам.

## Эндпоинты

### `GET /auth/login?return_to=<url>`

1. `return_to` проверяется по allowlist'у: `https` + хост из `hosts` + опционально
   `public_origin`. Невалидный → редирект на `public_origin`.
2. Генерируются `state` (16 байт), `nonce` (16 байт), `code_verifier` (S256).
3. `302` на `https://id.filenkov.store/realms/filenkov/protocol/openid-connect/auth`
   с `client_id=gateway`, `redirect_uri=https://filenkov.store/auth/callback`,
   `response_type=code`, `scope=openid profile email`, `kc_idp_hint=google`,
   `state`, `nonce`, `code_challenge`.

`kc_idp_hint=google` убирает форму Keycloak: пользователь видит сразу выбор
Google-аккаунта.

### `GET /auth/callback?code&state`

1. `state` сверяется с cookie `__Secure-open_flow`, cookie сразу удаляется (одноразово).
2. Обмен: `POST /protocol/openid-connect/token` (`grant_type=authorization_code`,
   `client_secret`, `code_verifier`).
3. `id_token` проверяется: подпись по JWKS, `iss`, `aud=gateway`, `nonce`, `exp`.
4. Ставятся `__Secure-open_access` и `__Secure-open_session` (`sid` из access-токена).
5. `302` на `return_to`.

Ошибки (`invalid state`, обмен не прошёл, `nonce` не совпал) → `302` на
`public_origin/?auth_error=<code>`. HTML-ошибки наружу не отдаются: детали только в лог.

### `GET /auth/session`

Профиль для витрины. Публичный путь, но с телом ответа `200` только для вошедшего.

```json
{
  "subject": "8f14e45f-ceea-467a-9e4b-1c2f9a0f5d11",
  "email": "ada@example.com",
  "name": "Ada Lovelace",
  "roles": ["admin", "svc:storage:family"],
  "services": [
    { "service": "storage", "level": "family" },
    { "service": "image", "level": "admin" }
  ]
}
```

`401 {"error":"unauthorized"}` для анонима. `services` собирается из ролей и реестра
`services:` — витрина не парсит имена ролей сама.

### `POST /auth/logout`

1. Проверка `Origin` (или `X-Requested-With`) — иначе `403`: это единственный
   state-changing эндпоинт, доступный с cookie.
2. `POST /protocol/openid-connect/logout` с refresh-токеном из cookie: Keycloak убивает
   сессию → умирает `sid` → умирают привязанные к сессии данные продуктов.
3. Cookie удаляются, `200 {"status":"ok"}`.

`GET /auth/logout` не существует: выход только POST'ом, чтобы ссылка в письме не могла
разлогинить.

## Обновление токена

Аноним с валидной `__Secure-open_session` на защищённом маршруте:

1. `edge` не находит живого access → `session` берёт refresh из cookie;
2. один обмен на сессию: параллельные запросы ждут общий результат (мутекс по `sub`),
   иначе ротация refresh инвалидирует cookie друг у друга и вкладки разъезжаются;
3. `Set-Cookie` с новым access (и новым refresh, если Keycloak его ротировал)
   копируется в исходный ответ;
4. запрос обрабатывается заново с новым access.

Если Keycloak ответил `400 invalid_grant` (сессия истекла/отозвана) — cookie сессии
удаляются, дальше обычный путь анонима: `302` на `/auth/login` или `401` JSON.

## Что где проверяется

| Угроза | Защита |
|---|---|
| Подмена `return_to` (open redirect) | allowlist хостов + только `https` |
| CSRF на callback | `state` в одноразовой cookie |
| Подмена id_token | подпись RS256 по JWKS + `nonce` + `aud` + `iss` |
| Кража access из XSS | токен в `HttpOnly`, JS его не читает |
| Кража refresh из XSS | refresh лежит внутри запечатанной cookie, отдельным значением не существует |
| Фиксация сессии | `sid` всегда новый от Keycloak, cookie не принимает внешнее значение |
| Логи входа с токенами | токены и коды не логируются; в access-логе только `sub` |

## Приёмка

```bash
# аноним на защищённом хосте → 302 на вход
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://storage.filenkov.store/

# вход → cookie → профиль
curl -s -c /tmp/jar -b /tmp/jar -L 'https://filenkov.store/auth/login?return_to=https%3A%2F%2Ffilenkov.store%2F' >/dev/null
curl -s -b /tmp/jar https://filenkov.store/auth/session | jq

# внешний return_to не проходит
curl -s -o /dev/null -w '%{http_code}\n' 'https://filenkov.store/auth/login?return_to=https%3A%2F%2Fevil.example.com%2F'

# выход рвёт сессию
curl -s -X POST -b /tmp/jar -H 'Origin: https://filenkov.store' https://filenkov.store/auth/logout
curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/jar https://filenkov.store/auth/session   # 401
```

Тесты в репозитории: `internal/bff/*_test.go` (httptest + поддельный `idp`), обязательно
покрыты: неверный `state`, битый `nonce`, истёкший refresh, параллельные refresh в двух
горутинах, `Origin`-проверка на logout.
