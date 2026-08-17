"""Support bounded context — internal support-ticket triage (Phase 11).

A sibling of `auth_service`, `billing_service`, `orchestration_service`
and `marketplace_service`: its own `domain`/`application`/
`infrastructure`/`interface` layers, its own `support_tickets` table.
Triage itself is not reimplemented here — this context calls the
existing `orchestration_service.application.run_agent` use case
in-process and reads the resulting run's steps back, the same way an
HTTP client of `/agents/{agent_id}/runs` would, just without the HTTP
hop (CLAUDE.md §5, Rule 5: no cross-context table reads — only
`orchestration_service`'s own ports/services).
"""
