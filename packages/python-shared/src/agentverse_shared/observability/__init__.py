"""Observability primitives shared by apps/api and apps/worker.

The three pillars stay separate (CLAUDE.md §12): this package is the
*metrics* pillar only. Logging lives in each service's
`infrastructure/logging.py`, tracing in the Phase 4 trace-event schema.
They correlate through `request_id` / `workspace_id` / `run_id`, and are
deliberately not merged here.
"""

from __future__ import annotations
