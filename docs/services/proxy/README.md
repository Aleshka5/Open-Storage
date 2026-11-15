# proxy — Caddy

TLS-слой. Единственный процесс, который слушает мир. Делает три вещи: завершает TLS,
перенаправляет `http://` на `https://`, ставит HSTS. Всё остальное — не его дело.

- Caddy 2.11.x, один файл `proxy/Caddyfile`
- Порты `80`/`443`, `default_bind` — адрес хоста в LAN + адрес WireGuard
- Единственный upstream на каждый хост: `reverse_proxy gateway:8080`

## Почему у него нет логики

Любая маршрутизация, любая проверка ролей и любой заголовок приложения в Caddy означали бы
второй источник правды об edge. Мы уже проходили: маршрут в одном файле, политика в
другом, и «фича пропала» ищется в трёх слоях. Поэтому Caddyfile отвечает только на вопрос
«этот домен — да, TLS есть», а на вопрос «кому и куда» отвечает `gateway`.

## Два класса хостов

| Класс | Пример | Сертификат |
|---|---|---|
| Публичный | `filenkov.store`, `storage.`, `image.`, `rag.`, `audio.`, `llm.`, `observer.`, `id.` | ACME (HTTP-01) от Let's Encrypt: у каждого имени своя публичная A-запись, wildcard не нужен |
| LAN/ WG | `meet.filenkov.store` | локальный CA (`tls internal`), сертификат ставится в системное и NSS-хранилище клиентов |

Правило: **не оставлять хост на `tls internal` молча**. Если выбран приватный CA,
в `proxy/README.md` и в ответе пользователю должно быть сказано, что клиенту нужно
установить корень.

## Caddyfile

```caddy
{
	admin off
	email admin@filenkov.store
	servers {
		protocols h1 h2          # без h3: quic не нужен, WS-путь проще отлаживать
	}
}

(secure) {
	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		-Server
	}
}

# хаб: витрина + BFF + каталог
filenkov.store {
	import secure
	reverse_proxy gateway:8080
}

# остальные продукты — тот же один upstream, отличается только имя
storage.filenkov.store {
	import secure
	reverse_proxy gateway:8080
}

image.filenkov.store {
	import secure
	reverse_proxy gateway:8080
}

rag.filenkov.store {
	import secure
	reverse_proxy gateway:8080
}

audio.filenkov.store {
	import secure
	reverse_proxy gateway:8080
}

llm.filenkov.store {
	import secure
	reverse_proxy gateway:8080
}

observer.filenkov.store {
	import secure
	reverse_proxy gateway:8080
}

# сам IdP — тоже через edge, чтобы политика и логи были в одном месте
id.filenkov.store {
	import secure
	reverse_proxy gateway:8080
}

# LAN/ WG only: приватный CA + пининг источника
meet.filenkov.store {
	tls internal
	@lan remote_ip 10.10.0.0/24 192.168.1.0/24 127.0.0.1
	handle @lan {
		reverse_proxy gateway:8080
	}
	respond 403
}

# вне SSO-контракта: у этих хостов своя аутентификация, gateway их не проксирует
hermes.filenkov.store {
	import secure
	reverse_proxy 127.0.0.1:9119
}

lite-llm.filenkov.store {
	import secure
	reverse_proxy 127.0.0.1:4000
}
```

HTTP→HTTPS: при заданном `default_bind` Caddy не создаёт редирект сам, поэтому внизу
файла — явный список:

```caddy
http://filenkov.store, http://storage.filenkov.store, … {
	redir https://{host}{uri} permanent
}
```

## Что Caddy НЕ ставит

`Permissions-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` —
это `gateway`, потому что значения зависят от хоста. Дубль этих заголовков в двух слоях
уже ломал микрофон: браузер пересекает политики, и `microphone=(self)` из одного слоя
отменялся `microphone=()` из другого.

## Добавить хост

1. A-запись (или запись в dnsmasq для LAN-only);
2. сайт-блок в `proxy/Caddyfile` — пять строк, копия предыдущего;
3. хост в `gateway/config.yaml`;
4. `caddy validate --config proxy/Caddyfile && systemctl reload caddy`.

## Проверка

```bash
caddy validate --config proxy/Caddyfile
curl -fsSI https://filenkov.store | grep -i strict-transport
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://filenkov.store/   # 308 → https
openssl s_client -connect filenkov.store:443 -servername filenkov.store </dev/null 2>/dev/null | openssl x509 -noout -issuer -dates
```
