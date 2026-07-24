"""Interface layer: health/readiness routes.

A background-job consumer doesn't inherently need an HTTP surface, but
CLAUDE.md §5 requires every service to define `/health` and `/ready`
before any business route — this minimal server exists so container
orchestration has a real endpoint to probe, ahead of Phase 3's actual
queue-consumer loop.
"""
