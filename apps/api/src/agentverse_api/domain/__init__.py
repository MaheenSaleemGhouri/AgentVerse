"""Domain layer: entities and business rules.

Zero framework imports (no FastAPI, no Pydantic-for-I/O, no DB driver) —
this layer is pure Python so it stays testable without I/O and reusable
by apps/worker (CLAUDE.md §5). Empty in Phase 0: the first entities
(workspace, workspace_members) land in Phase 1.
"""
