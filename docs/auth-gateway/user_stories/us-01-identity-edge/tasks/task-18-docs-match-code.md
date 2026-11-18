# task-18 Docs match the code

Story: [US-01](../init.md)

## Outcome

A contract update lands in the same change as the code. A difference between the spec and the config is a defect.

## Done when

- `src/auth-gateway/gateway/config.yaml` matches the host list in the gateway message contract.
- `services:` matches the role table in the idp message contract.
- Roles in `realm.json` match that table.
