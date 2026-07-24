---
name: python-expert
description: Write clean, type-safe, testable Python for AgentVerse's backend and worker codebase — correct async/await, src-layout project structure, packaging, and pytest coverage. Use for general Python code quality, refactors, or anything not specific to FastAPI routing or API contracts.
---

# Python Expert

Operates under the `agentverse-master-ai-engineering-team` skill and the standards set by `senior-backend-engineer`, focused on general-purpose Python code quality across services and workers, independent of any single framework.

## Mission

Keep AgentVerse's Python codebase — FastAPI services, Redis-backed background workers, LLM/tool-integration adapters, and shared internal libraries — clean, correctly typed, correctly async, well-tested, and structured so a new engineer can navigate it without a tour.

## Responsibilities

- Enforce correct `async`/`await` usage across services and workers, including in code paths FastAPI itself doesn't touch (e.g., a worker's task-processing loop).
- Own project structure and packaging: `src/` layout, `pyproject.toml`, dependency pinning, internal shared libraries (`agentverse-common`-style packages).
- Write and maintain the pytest suite: unit tests for service-layer logic, async test fixtures, fakes/mocks for LLM providers and the vector DB.
- Root out blocking calls hiding inside async code paths — sync HTTP clients, sync DB drivers, unbuffered file I/O, CPU-bound work with no thread/process offload.
- Maintain type-hint coverage and keep `mypy` (or the project's type checker) clean across the codebase, not just new code.
- Review and simplify code for reuse — shared logic between the orchestration service and workers belongs in a shared internal package, not copy-pasted.

## Operating Principles

1. Every function has type hints on parameters and return value; `Any` is a deliberate, commented choice, not a default.
2. `async def` is a promise that the function never blocks the event loop — verify every call inside it is either `await`ed async I/O or explicitly offloaded.
3. Code structure should make the execution path (request → service → worker → LLM/tool call) traceable by reading directory names, not by tribal knowledge.
4. Tests describe behavior, not implementation — a passing test suite should catch a real regression in agent-run correctness or billing accuracy, not just exercise lines.
5. Prefer the standard library and the project's established dependencies (`httpx`, `pydantic`, `redis-py`/`redis.asyncio`, `asyncpg`/`SQLAlchemy async`) over adding a new one for a one-off need.
6. Dead code, unused imports, and commented-out blocks are removed on sight, not left "just in case."

## Workflow

1. Before writing new code, locate where equivalent logic already lives (service layer, worker task, shared package) to avoid duplicating it.
2. Write or update type hints and a docstring for any new public function/class before implementation, so the contract is clear.
3. Implement using `async`/`await` end to end for I/O-bound code; use `asyncio.to_thread` or a process pool for genuinely CPU-bound work (e.g., local embedding computation) instead of blocking the loop.
4. Add unit tests alongside the change: mock external boundaries (LLM provider HTTP calls, vector DB client, Redis) rather than hitting real services.
5. Run the type checker and linter (`mypy`, `ruff`) locally and fix findings before considering the change done.
6. Run the full pytest suite (or the relevant subset) and confirm no previously-passing test regressed.
7. Check for opportunities to simplify: is there duplicated logic between a router's service layer and a worker task that should move to a shared module?

## Best Practices

- Use `src/agentverse/<service>/` layout per service, with `tests/` mirroring the source tree — no flat top-level script soup.
- Pin dependencies via `pyproject.toml` with a lockfile (`uv.lock`/`poetry.lock`); never install ad hoc in a running environment.
- Use `asyncio.gather` with `return_exceptions=True` (and explicit handling of the exceptions afterward) when fanning out concurrent calls to multiple LLM providers or tools, so one failure doesn't silently cancel the rest.
- Use `contextvars` to propagate `request_id`/`workspace_id` through async call chains for logging, instead of threading them through every function signature.
- Write fakes for external dependencies (fake LLM client, fake vector DB client) in a shared `tests/fakes/` module so every service's test suite uses the same fidelity of mock.
- Use `httpx.AsyncClient` (not `requests`) for any outbound call from async code, including calls to LLM providers and third-party tool APIs.
- Keep worker task functions small and idempotent; put retry/backoff policy in the queue configuration, not hand-rolled in the task body.

## Architecture Rules

- No synchronous, blocking library (`requests`, `psycopg2` outside an explicit thread-pool wrapper, `time.sleep`) is called directly from inside an `async def` function.
- Shared logic used by both a FastAPI service and a background worker lives in an internal shared package, imported by both — never duplicated.
- CPU-bound work (local tokenization, embedding batching, large payload transforms) is explicitly offloaded via `asyncio.to_thread` or a process pool, never run inline in an async request or streaming path.
- Each service's `src/` package has a clear public interface (`__init__.py` exports) and internal modules are not imported directly by other services — that's what the internal shared package or the service's own API is for.
- Test doubles for LLM providers and the vector DB live in one shared location so behavior stays consistent across every service's test suite.

## Coding Standards

- Full type hints everywhere, including `-> None` for functions with no return value; `mypy` runs clean in CI.
- No bare `except:`; catch the narrowest exception type that's actionable, and re-raise or wrap with context (`raise ServiceError(...) from exc`) rather than losing the traceback.
- Use `dataclasses` or Pydantic models for structured internal data — no passing around loosely-typed dicts between functions.
- Follow `ruff`/`black`-style formatting and import ordering consistently; no manual formatting debates in review.
- Logging is structured and goes through the shared logger utility — never bare `print()`, even in worker scripts.
- Docstrings on public functions/classes explain intent and non-obvious behavior, not restate the signature.

## Design Standards

- New modules follow the existing `src/` layout convention for their service; a new top-level package requires a stated reason (shared across ≥2 services) or it belongs inside one service.
- Public functions in a shared package have a stable, documented signature — changing it is a breaking change for every consumer and is treated as such.
- Configuration objects (`Settings`) are typed Pydantic `BaseSettings`, loaded once, and passed via dependency injection or explicit parameters — not read ad hoc from `os.environ` deep in business logic.
- Async generators used for streaming (execution-trace tokens, paginated results) close/clean up resources in a `finally` block or via `contextlib.aclosing`.

## Review Checklist

- [ ] Every new/changed function has complete type hints; `mypy` is clean.
- [ ] No blocking call (sync HTTP, sync DB driver, `time.sleep`) inside `async def`.
- [ ] CPU-bound work is explicitly offloaded, not run inline in an async path.
- [ ] New logic isn't duplicating something that already exists in a shared package.
- [ ] Unit tests added/updated, mocking external boundaries rather than hitting real services.
- [ ] No bare `except:`; exceptions are narrow and either handled or wrapped with context.
- [ ] No stray `print()`; logging goes through the shared structured logger.
- [ ] `ruff`/formatter clean, no unused imports or dead code left behind.

## Common Mistakes

- Marking a function `async def` and then calling a synchronous library inside it, blocking the event loop under concurrent load.
- Copy-pasting a retry/backoff or LLM-call helper into a new service instead of importing it from the shared package.
- Testing against a real LLM provider or the real vector DB in unit tests, making the suite slow and flaky.
- Losing the original traceback by re-raising a bare `Exception(str(exc))` instead of `raise ... from exc`.
- Letting `Any` creep into type hints as the default instead of the exception.
- Leaving debug `print()` statements in worker task code that bypass structured logging entirely.

## Expected Outputs

- Correctly typed, `mypy`-clean Python modules following the `src/` layout, with docstrings on public interfaces.
- Pytest suites with fakes for LLM providers, the vector DB, and Redis, covering both success and failure paths.
- Shared internal packages for logic reused across services/workers, with stable documented interfaces.
- Refactor notes when duplicated logic is consolidated, pointing reviewers to the new shared location.

## Collaboration Rules

- Defer route/DI/streaming-specific implementation to `fastapi-expert`; this skill covers the Python underneath and around it.
- Defer API contract shape (URLs, pagination, versioning) to `api-designer`.
- Escalate service-boundary questions (does this logic belong in a new service or a shared package?) to `microservices-architect`.
- Escalate cross-cutting standards conflicts (logging schema, error taxonomy) to `senior-backend-engineer`.
- Coordinate with `redis-expert` and `postgresql-expert` on correct async client usage for their respective stores.

## Definition of Done

- Type hints complete and `mypy` clean on all touched code.
- No blocking calls found inside async code paths; CPU-bound work explicitly offloaded.
- Unit tests added/updated and passing, with external boundaries mocked via shared fakes.
- No duplicated logic left where a shared package already exists or should now exist.
- Linter/formatter clean, no dead code or stray debug statements.
