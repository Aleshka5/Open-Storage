# resume-page

Витрина `filenkov.store`: дерево-резюме и UI каталога `/admin`. Статика, собранная Vite,
отдаётся nginx внутри `open_network`. Единственный источник личности — `GET /auth/session`
у `gateway`; токенов в JS нет.

- Стек: Vite 7, React 19, TypeScript, CSS-переменные (без UI-китов, без рантайм-CSS)
- Контейнер: `resume` (nginx:alpine, порт 80), публично — только через `gateway`
- Бюджет: начальный JS ≤ 95 KB gzip (сегодня ~88 KB), проверяется в `vite.config.ts` и
  роняет сборку при превышении

## Структура

```
resume-page/
  src/
    App.tsx                 /auth-редиректы, /admin, catch-all
    resume/
      registry.ts           import.meta.glob — центрального списка нод нет
      nodes/<путь>/meta.ts  заголовок, порядок, видимость, тизер (eager)
      nodes/<путь>/node.tsx тело ноды (lazy, отдельный chunk)
    pages/Auth.tsx          экран входа (одна кнопка «Continue with Google»)
    pages/Admin.tsx         таблица каталога (данные — /admin/users)
    components/             Layout, дерево, статья, форма
    hooks/useSession.ts     один запрос /auth/session на приложение
    styles/                 tokens, base, shell, article, tree, forms
  nginx.conf                try_files $uri $uri/ /index.html
  vite.config.ts            sitemap, robots, бюджет бандла
```

## Авторинг нод

Нода = папка. Путь папки = URL. `registry.ts` находит папки через `import.meta.glob` —
регистрировать маршрут не нужно нигде.

```ts
// src/resume/nodes/projects/open-storage/meta.ts
export const meta = {
  title: 'Open-Storage',
  order: 2,
  parent: 'projects',
  visibleWhen: 'signed-in',      // 'always' | 'signed-in' | 'admin' | 'service:storage'
  teaser: 'Свой edge, Keycloak и витрина без legacy',
} as const
```

Инварианты проверяются тестом `registry.test.ts` и роняют сборку:

| Инвариант | Зачем |
|---|---|
| `meta.ts` и `node.tsx` всегда в паре | недописанная нода не даёт пустую страницу |
| родитель существует, глубина ≤ 4 | дерево не рвётся |
| сегменты kebab-case, нет зарезервированных | URL предсказуем |
| `order` уникален среди соседей | порядок не «плавает» между сборками |
| `teaser` ≤ 120 символов | карточки не разъезжаются |
| корень — путь `''` | ровно одна точка входа |

## Личность и видимость

`useSession()` делает один `GET /auth/session` на загрузку приложения (не на каждую ноду):

```ts
type Session = {
  subject: string; email: string; name: string
  roles: string[]
  services: { service: string; level: null | 'family' | 'admin' | 'blocked' }[]
}
```

- `401` → гость: видны ноды `always`, ссылки на сервисы — с замком, ведущим на
  `/auth/login?return_to=<текущий путь>`;
- `signed-in` → все ноды, кроме `admin`;
- ссылка на сервис рисуется, если `services[i].level` ∈ {`family`, `admin`} или у
  пользователя `admin`; иначе — замок.

Клиент не решает, что ему можно: он только решает, что **показать**. Каждый переход всё
равно проходит политику `gateway`, и `403` там — нормальный ответ, а не баг витрины.

## `/admin`

Таблица из `GET /admin/users`: email, имя, глобальный `admin`, колонка на каждый сервис
из реестра. Ячейка сервиса — селект `— / family / admin / blocked`, `PUT` на изменение.
Блокировка аккаунта — отдельный переключатель (`PATCH {"enabled":…}`).

Правила, которые UI обязан отражать, а не изобретать:

- колонка чужого сервиса недоступна (`svc:<svc>:admin`) — селект `disabled`, причина в
  `title`;
- снять `admin` с себя, будучи последним, нельзя — `409 LAST_ADMIN` показывается как
  сообщение, а не как «ошибка сети»;
- список не пагинируется: на стенде десятки пользователей, поиск по email — на клиенте.

## Вход

`/auth` — экран с одной кнопкой. Нажатие = переход на
`/auth/login?return_to=<сохранённый путь>`; `gateway` редиректит в Google, возвращает
cookie и обратно на витрину. Пароля, формы регистрации и «забыл пароль» нет и не будет:
единственный способ входа — Google.

## Сборка и деплой

```bash
npm ci
npm run build          # падает при бюджете > 95 KB и при нарушении инвариантов реестра
npm test               # vitest: registry, Admin, api, useSession
podman build -t open/resume-page .
```

`nginx.conf`: `try_files $uri $uri/ /index.html` — глубокие ссылки живут без правок в
`gateway/config.yaml`: у хоста `filenkov.store` есть `/**` → `resume` с `policy: public`.

## Проверка

```bash
curl -s https://filenkov.store/ | head -5                       # HTML витрины
curl -s -o /dev/null -w '%{http_code}\n' https://filenkov.store/achievements/projects/open-storage   # 200 (SPA)
curl -s -b /tmp/jar https://filenkov.store/auth/session | jq .services
```

Приёмка: гость видит только `always`-ноды; вход через Google возвращает на исходный путь;
ссылка на `storage` появляется только при роли; `/admin` у не-админа — `403` от edge, а
не пустая страница.
