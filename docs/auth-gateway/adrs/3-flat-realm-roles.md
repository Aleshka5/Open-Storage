## Status

Accepted

## Decision

Service access is flat realm roles `svc:<service>:<level>`. Globally there is only `admin`. Block is `enabled: false`. No role means stranger.

## Rejected

Client roles plus a protocol mapper per service. Groups. One realm per service. A global `FAMILY` / `STRANGER` / `BLOCKED` set copied onto every host.

## Cost

Every service role is visible in one list. Granting access to a new service is an explicit grant, not a global family flag. Eight services times three levels is small enough that groups add nothing.

## Because

Client roles appear only for that client, so each service needs its own mapper. A realm per service removes single sign-on. A global family role does not mean anything on a host that has its own role. Disabling the account is the only block that stops login, token issue, and live sessions together.
