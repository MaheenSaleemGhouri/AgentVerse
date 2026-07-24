"""Interface layer: FastAPI routers, request/response schemas, middleware.

Thin orchestration only — handlers resolve dependencies and delegate to
`application`; no LLM/provider SDK call or business logic lives here
(CLAUDE.md §7). In Phase 0 this layer carries only health/readiness
routes: there is no business logic to delegate to yet.
"""
