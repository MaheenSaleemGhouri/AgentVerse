"""Infrastructure layer: concrete adapters (config, logging, and — from
Phase 1 onward — Postgres, Redis, the vector DB, and LLM provider clients).
Implements ports defined by `domain`/`application`; never the reverse.
"""
