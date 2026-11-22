# task-04 Vault session key

Story: [US-06](../init.md)

## Outcome

The private vault keys its Redis session on the gateway's session cookie, derived in-process, instead of the `auth_session` cookie the old auth service minted. The unlock, lock and read paths work under the new cookie.

## Paths

- `src/open-storage/app/app/presentation/dependencies/private.py` — `_get_session_id`
- `src/open-storage/app/config.py` — `AuthSettings.cookie_name` removed, `private_session_ttl_hours` kept
- `src/open-storage/app/tests/test_private_vault_cookie.py`

## Done when

The key comes from the `__Secure-open_session` cookie; a missing cookie answers 401 exactly as today; the Redis key is not the raw cookie value (it is hashed, so a log or a dump does not hold a credential); two logins of one user produce two vault keys, and the first key's private key is not readable under the second session; `AUTH_COOKIE_NAME` is gone from the code and from `.env.example`; `unlock_attempts` stays keyed on user and IP, not on the session.
