# resume-page — design

Static showcase for `filenkov.store` and the `/admin` catalog UI. Served by nginx in `open_network`, reached only through gateway.

Stack: Vite 7, React 19, TypeScript, CSS variables. See [brand-book](../../brand-book/README.md).

## Tree

A node is a folder. The folder path is the URL. `registry.ts` discovers folders with `import.meta.glob`. Nothing registers a route by hand.

```text
src/resume/nodes/<path>/meta.ts    title, order, parent, visibleWhen, teaser (eager)
src/resume/nodes/<path>/node.tsx   body (lazy, own chunk)
```

`visibleWhen`: `always` | `signed-in` | `admin` | `service:<name>`.

The build fails when any of these break:

| Rule | Why |
|---|---|
| `meta.ts` and `node.tsx` come as a pair | A half-written node must not ship as an empty page |
| The parent exists, depth ≤ 4 | The tree stays connected |
| Path segments are kebab-case and not reserved | URLs stay predictable |
| `order` is unique among siblings | Order does not drift between builds |
| `teaser` ≤ 120 characters | Cards stay aligned |
| Exactly one root, path `''` | One entry |

`/auth` is one button, "Continue with Google". No other account UI.

`/admin` is one table from `GET /admin/users`: email, name, global admin, one column per service. A service cell is a select: empty, `family`, `admin`, `blocked`. Account block is a separate switch. No pagination. Email search is on the client. Tens of users is the expected size.

nginx: `try_files $uri $uri/ /index.html`. Deep links do not need a gateway route of their own. The host catch-all is `policy: public`.
