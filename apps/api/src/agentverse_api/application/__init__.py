"""Application layer: use cases/services that orchestrate the domain layer.

Depends inward on `domain`, never on `interface` or a specific
`infrastructure` implementation (CLAUDE.md §5 — dependencies point
inward; infrastructure implements domain-defined ports). Empty in
Phase 0 — the first use cases land alongside Phase 1's workspace model.
"""
