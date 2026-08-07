# ADR-0013: Cross-Context Search and Full-Text Indexing

## Context

Phase 10 M6 adds global search. Until now the ⌘K palette matched only route names from `lib/navigation.ts`: it could find the Agents *page* but never an agent. A workspace with forty agents had no way to reach one by name from the keyboard, and the marketplace catalog's `q` filter was an `ILIKE '%…%'` scan that the M1 migration comment explicitly flagged as provisional ("M6's search work owns the upgrade; this is honest until then").

Four decisions in this milestone are load-bearing and awkward to reverse once other surfaces depend on them.

**1. Where does search live?** Searchable rows are owned by two existing bounded contexts: `agents`, `knowledge_bases` and `teams` in `orchestration_service`, `marketplace_listings` in `marketplace_service`. A search feature naturally wants to `SELECT` across all four in one query — they are in the same database and there is no network boundary in the way. Rule 5 and ADR-0001 forbid exactly that. But search also belongs to neither context: putting the fan-out inside orchestration would make orchestration read the marketplace's tables, and vice versa.

**2. Stored `tsvector` column, or expression index?** Postgres full-text search needs an index to be worth anything. The textbook answer is a `GENERATED ... STORED` `tsvector` column plus a GIN index on it. On a hot table that migration takes an `ACCESS EXCLUSIVE` lock and rewrites every row.

**3. How does user typing become a `tsquery`?** This backs a typeahead, so terms must prefix-match — someone who has typed "knowl" expects their knowledge base, and `websearch_to_tsquery` would search for the whole word "knowl" and find nothing. Prefix matching requires `to_tsquery`, which — unlike `plainto_tsquery` — **parses its argument as an expression**. Anything reaching it is executable `tsquery` syntax.

**4. What response shape?** CLAUDE.md §7 fixes one list envelope: `{"data", "next_cursor", "has_more"}`.

## Decision

**Search is a fourth bounded context, `search_service`, that owns only fan-out and ranking policy.**

- New `apps/api/src/agentverse_api/search_service/` with the same four layers as its three siblings, holding no SQL of its own.
- Each searchable context grows a `search_*` method on **its own** repository — `SqlAgentRepository.search_agents`, `SqlKnowledgeRepository.search_knowledge_bases`, `SqlTeamRepository.search_teams`, `SqlListingRepository.search_published` — each reusing that repository's existing tenant and soft-delete predicates, so search can never disagree with the owning context about what "a live agent" is.
- `search_service` reaches them through a `KindSearcher` port, satisfied by four four-line adapters in `infrastructure/searchers.py`. This is the same shape as `OrchestrationAgentImporter` (ADR-0010's tool-execution boundary precedent, reused by the marketplace in Phase 10 M2), and the composition root in `interface/dependencies/services.py` is the complete, auditable list of what search touches.
- It is a **module inside `apps/api`, not a new deployable service.** No independent scaling, ownership, or failure-isolation need exists (§5), so no service boundary is created.
- Searchers run **sequentially**, not under `asyncio.gather`: they share one `AsyncSession`, which is not safe for concurrent use. Gathering would raise `MissingGreenlet`/`InvalidRequestError` under exactly the load that makes parallelism look attractive.

**Indexes are GIN expression indexes, built `CONCURRENTLY`, with the expression generated from one function.**

- Four indexes over `agents`, `knowledge_bases`, `teams` and `marketplace_listings` on `to_tsvector('english', coalesce(title,'') || ' ' || coalesce(subtitle,''))`. No column is added and no table is rewritten; this is indexing *within* the schema `database-architect` owns, which is `postgresql-expert`'s remit.
- `agentverse_api.infrastructure.full_text` is the single source of that expression: the migration renders `searchable(...)` into its `CREATE INDEX` and every repository builds its query through `search_query(...)`.
- Inside it, the constants are `literal_column`, **not** `literal`. `literal("english")` compiles to a bind parameter, and Postgres matches an expression index by comparing parsed expression trees — a parameter it does not know at plan time does not match the constant the index was built with. The query would return correct rows and sequentially scan forever, with no error and no log line.
- An integration test asserts `EXPLAIN` picks a `Bitmap Index Scan` for all four, with `enable_seqscan = off` so the plan reflects index *matching* rather than the optimizer's preference on a small table. This is the only mechanism that catches the drift described above.

**`to_prefix_tsquery` is injection-safe by construction, in `agentverse_shared`.**

- It extracts `[A-Za-z0-9]+` runs, lowercases, caps at 8 terms and 128 characters, and joins with ` & `, appending `:*` to each. No `tsquery` operator (`&`, `|`, `!`, `<->`, quotes, parentheses) can survive, because nothing but alphanumerics does — safety by allowlist, not by escaping.
- It lives in `packages/python-shared` because four repositories across two contexts build queries with it. Four copies would drift, and a drifted normalizer shows up as "search finds it in the palette but not in the catalog", which is indistinguishable from a data bug.

**The search response deliberately does not use the standard list envelope.**

`GET /api/v1/workspaces/{workspace_id}/search` returns `{"query", "groups": [{"kind", "hits", "has_more"}]}`. A cursor envelope is for collections a client walks; this is a typeahead. Nobody pages a ⌘K palette — they type another character, which is a *new* query, against which a cursor issued for the previous one is meaningless. `has_more` means "narrow your search", not "fetch page two", and is computed by over-fetching one row rather than a second `COUNT(*)`.

A query below `MIN_QUERY_LENGTH` returns empty groups, **not** a 422: the user is mid-word on the way to a valid query, and answering a keystroke with a validation error would put an error under the search box on the way to every successful search.

## Consequences

- Adding a searchable kind is a `search_*` method on the owning repository plus a four-line adapter. It is never a join across a context boundary, and the composition root makes any attempt visible in review.
- `browse`'s `ILIKE` scan is replaced by the same full-text predicate, so the catalog and the palette agree on what matches. The M1 comment promising this is removed.
- The catalog searcher is the **only** query in the codebase with no `workspace_id` predicate. `status = 'published'` does all of the security work there; without it, every workspace's drafts would be readable from every other workspace's search box. It is called out in the code and covered by an integration test.
- `viewer` is the floor. Everything reachable through search is already readable by a viewer through its own list endpoint — search is a faster route to those rows, never a wider one.
- Runs are **not** searchable. There is still no read path over `agent_runs` (the Phase 4 gap tracked as `runHistory` in `feature-availability.ts`), and a result that cannot be opened is worse than one not offered. The same reasoning keeps `listing` out of the palette's requested kinds until the marketplace UI ships.
- `ts_rank_cd` scores are comparable only *within* a kind, since they come from different columns. `rank` is therefore not on the wire: exposing it would invite a client to sort across kinds by it.

## Alternatives Considered

- **One cross-context `SELECT` with `UNION ALL`.** Rejected: the direct Rule 5 violation this ADR exists to avoid, and it would couple search to four table shapes it does not own.
- **Search inside `orchestration_service`.** Rejected: it owns three of the four kinds but not the catalog, so it would have to read the marketplace's tables.
- **A separate deployable search service.** Rejected as speculative complexity (Rule 10): no independent scaling, ownership, or failure-isolation need exists.
- **A dedicated search engine (OpenSearch/Meilisearch/Typesense).** Rejected for now: a new datastore to operate, back up, and keep consistent with Postgres, to serve a typeahead over hundreds of rows per workspace. Postgres full-text is the boring, proven option (§3 KISS), and this ADR is the place to revisit it if per-workspace corpora reach a scale where ranking quality or latency actually suffers.
- **Stored generated `tsvector` columns.** Rejected: a full-table rewrite under `ACCESS EXCLUSIVE` on live tables, for no benefit an expression index does not give.
- **`plainto_tsquery` / `websearch_to_tsquery`.** Rejected: neither supports prefix matching, so a typeahead would find nothing until the user finished every word.
- **Escaping user input into `to_tsquery`.** Rejected in favour of an allowlist. Escaping is a blocklist by another name, and `tsquery` has enough syntax to make that a losing game.
- **The standard cursor envelope.** Rejected as an unusable contract for a typeahead, as above.

## Status

Accepted — Phase 10 M6.

## Owner Skills

`principal-software-architect` (context boundary), `postgresql-expert` (indexing and query plans), `api-designer` (response contract), `security-engineer` (`tsquery` injection surface, catalog-without-tenant-predicate review).
