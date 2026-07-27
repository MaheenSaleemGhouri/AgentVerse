"""Stage 4 — context assembly within the target model's real budget.

The roadmap's acceptance criterion for this stage is explicit: the total
token count must respect the target model's *real* budget, with the
system prompt, conversation history, and reserved output all accounted
for. So the budget is computed by subtraction from the model's context
window, never taken as a hand-passed constant — a caller who forgot to
subtract reserved output would produce a prompt that fits the window and
then truncates the model's answer mid-sentence, which looks like a model
failure rather than a budgeting bug.

Chunks are emitted in relevance order (best first). `rag-expert` orders
by relevance rather than by document position because attention degrades
toward the middle of a long context; the chunk most likely to contain
the answer should not land there.
"""

from __future__ import annotations

from agentverse_shared.retrieval.types import AssembledContext, Citation, ScoredChunk
from agentverse_shared.text.tokenizer import TokenCounter

#: Wrapper text delimiting each chunk. Structural delimiting, not
#: concatenation: retrieved documents are untrusted content and must
#: never be blurred into the instruction stream (CLAUDE.md §9/§10 —
#: prompt injection). The source id is inside the block so the model can
#: attribute a claim, and so a chunk that *tries* to impersonate an
#: instruction is visibly inside a data block.
_BLOCK_HEADER = "<document id={document_id} chunk={chunk_index}>"
_BLOCK_FOOTER = "</document>"
_SEPARATOR = "\n\n"


class ContextBudgetError(ValueError):
    """Raised when the computed budget is non-positive — i.e. the system
    prompt plus history plus reserved output already exceed the model's
    window. That is a caller bug (or an over-long conversation that needs
    trimming upstream), and failing loudly beats silently retrieving
    nothing and producing an ungrounded answer that looks fine.
    """


def compute_context_budget(
    *,
    model_context_window: int,
    system_prompt_tokens: int,
    history_tokens: int,
    reserved_output_tokens: int,
    safety_margin_tokens: int = 128,
) -> int:
    """Tokens actually available for retrieved context.

    `safety_margin_tokens` absorbs the per-message and per-role scaffold
    tokens the chat format adds on top of raw content, which our own
    counting does not model. Small and explicit rather than a fudge
    factor buried in a magic number.
    """
    budget = (
        model_context_window
        - system_prompt_tokens
        - history_tokens
        - reserved_output_tokens
        - safety_margin_tokens
    )
    if budget <= 0:
        raise ContextBudgetError(
            f"No context budget left: window={model_context_window}, "
            f"system={system_prompt_tokens}, history={history_tokens}, "
            f"reserved_output={reserved_output_tokens}, margin={safety_margin_tokens}"
        )
    return budget


def assemble_context(
    chunks: list[ScoredChunk],
    *,
    budget_tokens: int,
    counter: TokenCounter,
) -> AssembledContext:
    """Packs chunks best-first until the budget is exhausted.

    A chunk that does not fit is skipped and the next one is tried rather
    than stopping the loop: a single oversized chunk in the middle of the
    ranking must not starve every smaller, still-relevant chunk behind
    it. Chunks are never truncated — half a passage is a half-true
    citation, and a citation that doesn't support its claim is worse than
    no citation.
    """
    used = 0
    kept: list[ScoredChunk] = []
    blocks: list[str] = []
    dropped = 0

    for scored in chunks:
        block = _render_block(scored)
        # Measured on the rendered block, including delimiters and the
        # separator: the budget is about what actually reaches the model,
        # not about the bare chunk text.
        cost = counter.count(block) + (counter.count(_SEPARATOR) if blocks else 0)
        if used + cost > budget_tokens:
            dropped += 1
            continue
        used += cost
        blocks.append(block)
        kept.append(scored)

    return AssembledContext(
        context_text=_SEPARATOR.join(blocks),
        citations=[_citation(s) for s in kept],
        used_tokens=used,
        budget_tokens=budget_tokens,
        dropped_chunk_count=dropped,
        chunks=kept,
    )


def _render_block(scored: ScoredChunk) -> str:
    chunk = scored.chunk
    header = _BLOCK_HEADER.format(document_id=chunk.kb_document_id, chunk_index=chunk.chunk_index)
    return f"{header}\n{chunk.content}\n{_BLOCK_FOOTER}"


def _citation(scored: ScoredChunk) -> Citation:
    chunk = scored.chunk
    return Citation(
        chunk_id=chunk.chunk_id,
        kb_document_id=chunk.kb_document_id,
        knowledge_base_id=chunk.knowledge_base_id,
        chunk_index=chunk.chunk_index,
    )
