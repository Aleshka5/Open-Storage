# task-05 DNS

Story: [US-07](../init.md)

## Outcome

`storage.filenkov.store` resolves to the host from the LAN and from outside it, so the proxy can issue a certificate and a family browser can reach the name.

## Paths

- Operator DNS zone for `filenkov.store`

## Done when

`dig +short storage.filenkov.store` answers the host's address from the LAN and from an outside resolver; the record is absent before this task and present after, and the change is written into the story's DoD with the date; the proxy obtains the certificate on the first request.
