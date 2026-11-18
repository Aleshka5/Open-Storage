# resume-page — security

The page does not hold tokens, does not see cookies' contents, and does not know secrets.

- One `GET /auth/session` per application load, not per node.
- `401` means guest. Show nodes with `visibleWhen: always`. Service links show a lock to `/auth/login?return_to=<current path>`.
- `signed-in` shows every node except `admin`.
- A service link is shown when that service's `level` is `family` or `admin`, or the user has realm `admin`. Otherwise show the lock.
- The page only chooses what to display. Gateway still enforces the route. A `403` from the edge is a normal answer.
- `/admin` for a non-admin is `403` from the edge, not an empty page drawn by the UI.
- A select for a service the caller does not administer is `disabled`, with the reason in `title`.
- `409 LAST_ADMIN` is shown as that message, not as a network error.
- Sign-in navigates to `/auth/login?return_to=<saved path>`. Gateway sets the cookies and returns to the showcase.
