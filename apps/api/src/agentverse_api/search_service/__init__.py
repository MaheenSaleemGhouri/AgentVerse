"""Cross-context search.

Search belongs to no single bounded context — it spans agents, knowledge
bases and teams (orchestration) and the public catalog (marketplace) —
so it lives in its own module rather than being bolted onto whichever
context happened to need it first.

That does **not** make it a service that reads other services' tables.
Each searchable context implements its own `search_*` repository method
over its own tables; this module holds only the fan-out, the shared
result shape, and the ranking policy, reaching each context through a
`KindSearcher` port (Rule 5). It is a module inside `apps/api`, not a new
deployable service, so no service boundary is created and no ADR is due.
"""
