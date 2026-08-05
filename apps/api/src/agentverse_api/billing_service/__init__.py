"""Billing bounded context — plans, entitlements, subscriptions, usage
metering and invoicing.

A sibling of `auth_service` and `orchestration_service`: its own
`domain`/`application`/`infrastructure`/`interface` layers, its own
tables, reached from other contexts only through its services — never by
another context querying a `plans` or `billing_*` table directly
(CLAUDE.md §5, Rule 5).
"""
