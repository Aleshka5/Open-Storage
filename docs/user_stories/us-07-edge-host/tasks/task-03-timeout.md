# task-03 Timeout

Story: [US-07](../init.md)

## Outcome

The host holds a large upload and download well past the 60s default, and a stuck upstream still answers `504`.

## Paths

- `src/auth-gateway/gateway/config.yaml` — `timeouts: { response_header: 30m }`

## Done when

`response_header: 30m` is on this host only; a download whose first byte is slower than 60s completes; an upstream that sends no header at all is cut off by the host timeout and answers `{"error":"gateway_timeout"}`; other hosts keep their own timeouts.
