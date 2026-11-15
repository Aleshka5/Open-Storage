# idp — эксплуатация

## Принцип

`idp/realm.json` — единственный источник конфигурации realm. Правки через Admin Console
запрещены: они не переживут пересоздание тома и создадут дрейф, который обнаружится в
самый неподходящий момент. Исключение — пользователи: они живут в БД и в git не ездят.

## Импорт и дрейф

```bash
# старт: realm импортируется при пустой БД (--import-realm, ifResourceExists: SKIP)
podman compose -f deploy/compose.yaml up -d idp_db idp

# дрейф: выгрузить живой realm и сравнить с git (в отчёте только отличия, без секретов)
podman exec idp /opt/keycloak/bin/kc.sh export --realm filenkov --file /tmp/live.json
podman cp idp:/tmp/live.json /tmp/live.json
jq -S 'del(.users, .components, .id)' /tmp/live.json > /tmp/live.norm.json
jq -S 'del(.users, .components, .id)' idp/realm.json > /tmp/git.norm.json
diff -u /tmp/git.norm.json /tmp/live.norm.json && echo "no drift"
```

Ожидаемые отличия, которые не являются дрейфом: `users`, `components` (ключи подписи),
`id`, временные метки. Всё остальное в diff'е — правка мимо git, её нужно либо перенести в
`realm.json`, либо откатить.

Изменение схемы realm (новый клиент, роль, mapper) делается так:

1. правка `idp/realm.json`;
2. `podman compose up -d --force-recreate idp` (импорт идемпотентен для новых объектов);
3. проверка: `curl -fsS https://id.filenkov.store/realms/filenkov/.well-known/openid-configuration | jq -r .issuer`;
4. вход через Google руками — токен должен содержать ожидаемые `realm_access.roles`.

## Бутстрап и break-glass

Первый админ появляется не сам (счётчика «первый пользователь» в Keycloak нет):

```bash
scripts/grant-admin.sh ada@example.com   # войти через Google один раз, затем выдать роль
```

Скрипт берёт клиент `gateway-admin` из env-файла (админский пароль в чат не попадает),
находит пользователя по email и добавляет realm-роль `admin`.

Если сломалась выдача ролей через `gateway` (например, ошибочно снят `admin` у всех):
админский доступ к `https://id.filenkov.store/admin/` идёт мимо `gateway`-политики внутрь
`idp`, поэтому восстановление возможно всегда, пока жив `idp_db`. Пароль
`KC_BOOTSTRAP_ADMIN_*` — только для пустой БД; после первого старта он удаляется из env.

## Апгрейд

1. прочитать release notes на ломающие изменения (`quarkus`, `realm` схемы);
2. изменить тег в `idp/README.md` и `deploy/compose.yaml` — оба места;
3. `pg_dump` перед обновлением:

```bash
podman exec idp_db pg_dump -U keycloak keycloak | gzip > backups/keycloak-$(date +%F).sql.gz
```

4. `podman compose up -d idp`; при неудаче — вернуть тег, БД откатывается из дампа.

Версия в БД миграции назад не откатываются: единственный откат — восстановление дампа.

## Бэкап

| Что | Чем | Как часто |
|---|---|---|
| `idp_db` | `pg_dump` в `backups/` (hard disk, не в контейнерный том) | сутки |
| `realm.json` | git | каждый коммит |
| Ключи подписи | внутри `idp_db`, поэтому дамп обязателен | сутки |

Восстановление: поднять `idp_db` на пустом томе, залить дамп, стартовать `idp` **без**
`--import-realm` (иначе импорт может перетереть объекты).

## Сессии и ревокация

```bash
# все сессии пользователя (и живые access-токены умрут в течение 5 минут по exp)
curl -fsS -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://id.filenkov.store/admin/realms/filenkov/users/$ID/logout
```

| Ситуация | Действие |
|---|---|
| «Разлогинь меня везде» | Admin API `users/{id}/logout` + `notBefore` |
| Заблокировать человека | `enabled=false` (в `gateway` это выглядит как аноним) |
| Заблокировать от одного сервиса | снять `svc:<svc>:family` и выдать `svc:<svc>:blocked` |
| Подозрение на утечку refresh | `revokeRefreshToken=true` уже включён: ротация одноразовая |

## Наблюдаемость

- `https://id.filenkov.store/realms/filenkov/health/ready` — готовность (публичный путь
  на host `id.filenkov.store`, политика `public`);
- события входа/ошибок — в логах `idp` (JSON, `podman logs -f idp`);
- brute-force защита: `bruteForceProtected: true`, `failureFactor: 5`,
  `waitIncrementSeconds: 60` — включено в realm.

## Частые сбои

| Симптом | Причина | Проверка |
|---|---|---|
| `Invalid parameter: redirect_uri` | redirect URI в Google-клиенте не `…/broker/google/endpoint` | Google Console |
| `We are sorry... Cookie not found` | `KC_PROXY_HEADERS=xforwarded` не задан, Keycloak видит http | `podman logs idp` |
| Вход срабатывает, но `roles` пусты | realm-роли не выданы или импорт не применился | `GET /admin/realms/filenkov/users/{id}/role-mappings/realm` |
| `sub` меняется между входами | у `google` IdP включён `syncMode: FORCE`, привязка по email | realm.json: `IMPORT` |
| Долгий первый старт | импорт realm + миграции БД | нормально до ~60 с |
