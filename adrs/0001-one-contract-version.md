# ADR-0001 One contract version

## Status

Accepted

## Decision

Identity has one contract, v1, and the header names in [identity v1](../docs/auth-gateway/external-contracts/identity-v1.md). No compatibility flag and no second set of names.

## Rejected

A `legacy_headers` flag, or two versions carried in the token, for the duration of a migration.

## Cost

One cutover. SSO is down until the last consumer is updated. That is cheaper than a second contract that stays for years.

## Because

A transition period is code that needs tests for both modes. There is one stand and a handful of consumers, all reachable by the same operator.
