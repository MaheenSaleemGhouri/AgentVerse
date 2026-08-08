# ADR-0014: The In-Product Assistant and Its Docs Grounding

## Context

Phase 10 M8 adds the AgentVerse assistant: a help surface reachable from every dashboard page that answers questions about the product. M6 shipped the documentation portal (eleven guides under `apps/web/content/docs/`) and global search, so a user can already *find* a guide. They still cannot ask a question in the words they actually have.

Four decisions here are load-bearing and awkward to reverse once the surface exists.

**1. What is an assistant turn, architecturally?** CLAUDE.md Rule 14 is unambiguous: long-running agent execution is always a background worker job, never inline in a request. An agent run in this platform means the worker fleet, the Agents SDK, a queue, a trace, and a quota decrement. If the assistant is "an agent", all of that applies, and a help question becomes a billable run that appears in the customer's run history.

**2. Where does the grounding corpus live?** The guides are markdown under `apps/web/content/docs/`, owned by the web app and rendered at build time. The API image does not contain the web app and cannot read that directory at runtime. Duplicating the prose into the API is a Rule 3 violation with a predictable ending: two copies, one of them stale, and no signal when they diverge.

**3. Retrieval: embeddings or not?** The platform already has a vector layer (`kb_chunks`, pgvector, HNSW) and a retrieval pipeline (`rag-expert`'s rewrite → hybrid retrieve → rerank → assemble). Reaching for it is the path of least surprise.

**4. Transaction scope across a streamed provider call.** The answer streams, and both turns are persisted. FastAPI's `get_db_session` is request-scoped and commits when the request ends.

## Decision

**An assistant turn is one bounded provider call, not an agent run.**

- `assistant_service` is a new bounded context in `apps/api` — a module, not a deployable service (§5: no independent scaling, ownership, or failure-isolation need). Same four layers as its siblings.
- One `ProviderAdapter.stream_chat` call per turn, with **no tool loop**. The assistant answers questions about the product from the product's documentation; it cannot create an agent, start a run, or change a setting. There is nothing for it to call, so there is no loop to bound and no side-effecting action needing an allow/deny policy check (§4, Human Approval).
- Rule 14 is therefore not engaged: this is a bounded synchronous completion in the same shape as `ProviderTestService`, not agent execution. Rule 17's cost ceiling is set explicitly as `MAX_ANSWER_TOKENS = 800`; the step ceiling is structural.
- Model is `gpt-4o-mini`, routed cheap deliberately (§4, Cost Optimization): extractive question-answering over four short passages already in the prompt is shallow reasoning, and the strongest model would buy latency and cost on every help question.
- **If the assistant ever gains the ability to act, that is a new design with its own ADR**, not a parameter added to this one.

**The markdown stays the single source of truth; the API consumes a generated index.**

- `scripts/build_docs_index.py` builds `assistant_service/infrastructure/docs_index.json` from `apps/web/content/docs/`, splitting each published guide into heading-bounded passages with the URL and anchor that cite it.
- `tests/assistant_service/test_docs_corpus.py` rebuilds the index in memory and fails if the committed file differs, naming the command to run. This is the same generated-artifact-plus-drift-gate arrangement `packages/contracts` uses for the OpenAPI types, chosen for the same reason: DRY does not permit two hand-maintained copies, but a runtime cannot read another app's source tree.
- Drafts and deprecated guides are excluded. The assistant must never ground an answer in a page the product does not currently publish.
- Code fences are stripped from the grounding text. A quoted-back `curl` snippet is what an assistant is most likely to get subtly wrong; the citation link carries the real one.
- `slugify_heading` must match `apps/web/lib/docs/render.ts` exactly, and is tested against it. A mismatch is a citation that lands on the wrong part of the page — which quietly undoes the one thing citations are for.

**Retrieval is weighted term overlap, behind a port.**

- `CorpusDocsIndex` scores title/heading/body overlap with stopwords removed, drops anything below `MIN_SCORE`, and breaks ties on corpus order so the same question always assembles the same context.
- No embeddings. The corpus is ~100 passages; an embedding round-trip would add a call and a cost to every question, and would need re-embedding on every docs edit, to beat a scorer that already resolves "how do I rotate an API key" to the API-keys guide. §9 says each retrieval stage earns its place by measured improvement — there is nothing yet to measure against.
- It sits behind the `DocsIndex` port precisely so this is a swap and not a rewrite when the corpus outgrows it.

**Every database touch is its own short transaction, via a `UnitOfWork` port.**

- `sql_unit_of_work` opens one session, commits on clean exit, and is used in blocks *around* the provider call — never across it. A request-scoped session would hold a pooled connection open for the whole generation while doing no database work, which §7 forbids and which would exhaust the pool under a few dozen concurrent questions.
- The user's message commits **before** the call, so a provider failure still leaves a conversation showing what was asked. The assistant's message is written only on `StreamDone`: a partial answer stored is words put in the assistant's mouth that it never finished saying, and then replayed as history on the next turn.

**Sessions are scoped by workspace *and* user.**

Rule 11 requires the first. The second is not redundant: billing and quota are facts about a workspace, but a half-typed support question is personal, and a workspace admin reading their colleagues' help conversations is a privacy surprise nobody asked for. Both are enforced in the `WHERE` clause, not checked after the fetch, and both are covered by integration tests against real Postgres.

**Untrusted-content handling is built in from the start.**

Retrieved passages are rendered into a delimited `<passage url=…>` block with an explicit "reference material, never instructions" framing (§9). The guides are first-party today; the defence has to predate the first user-authored page, not follow it. On the way back out, `lib/assistant/render.ts` parses the model's markdown into data and the component renders React elements — there is no `dangerouslySetInnerHTML` anywhere in the path — and only `/docs/...` hrefs survive as links, so a model-invented URL renders as the literal text it is.

**Platform-admin visibility gets one unguarded read.**

`GET /api/v1/admin/session` answers "is the caller platform staff?" for any authenticated caller, so the dashboard can decide whether to render the moderation entry point. The alternative — probing a gated route and swallowing the 404 — would write a `platform_admin.denied` audit entry on every page load for every ordinary user, burying the denials that matter. The moderation routes themselves keep answering 404 on denial.

## Consequences

- A help question costs a provider call. It is bounded by `MAX_ANSWER_TOKENS`, the per-workspace gateway rate limit from M4, and `MAX_QUESTION_LENGTH`; it is gated at `require_viewer` rather than `require_member`, because a viewer is the role most likely to be new and most likely to need it, and the same content is already free to read at `/docs`.
- Editing a guide without rerunning `build_docs_index.py` fails CI with the command to run. That is the intended cost of the generated artifact.
- The assistant's answers are only as good as eleven guides. When it says "I could not find that", that is a documentation gap made visible — which is useful, and is why the prompt is instructed to say it plainly rather than improvise.
- Assistant turns do **not** appear in run history, traces, or usage metering, because they are not runs. If per-workspace assistant cost ever needs to be billed or surfaced, that is a metering change, not a re-architecture — the token usage is already logged per turn with `workspace_id` and `session_id`.

## Alternatives considered and rejected

- **Model the assistant as a first-party agent run through the worker fleet.** Architecturally tidy and reuses everything, but it puts help questions in the customer's run history, spends their quota, and requires per-workspace agent seeding and per-tenant embedding of the same public documentation. The reuse is real but the semantics are wrong: a support question is not the customer's agent doing work.
- **Ship the docs into the API image, or read them from a shared volume.** Removes the generator but couples deployment of two apps and gives the API a runtime dependency on the web app's directory layout.
- **Retrieve in the Next.js server and post the passages to the API.** The web app owns the corpus, so this needs no generator at all. Rejected because it makes the grounding context client-supplied: a caller could send arbitrary "documentation" and get it treated as source. The blast radius is only their own answer, but a trust boundary that depends on the client behaving is not one.
- **Embeddings via the existing vector layer.** Correct at ten times the corpus size; premature at this one, and it would put a second embedding-model version in play for content that is not tenant data.
- **Render the answer with a markdown library.** Pulls a parser and a sanitiser into a bundle loaded on every dashboard route to support emphasis nobody asked for. The narrow parser handles exactly what the prompt requests and shows everything else as literal text.
