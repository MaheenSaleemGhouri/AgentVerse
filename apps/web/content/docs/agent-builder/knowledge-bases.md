---
title: Ground an agent in your documents
summary: Upload documents to a knowledge base so an agent answers from your content, with citations.
pillar: agent-builder
last_verified: "2026-08-07"
status: published
order: 3
---

A knowledge base is a collection of documents an agent can search while it runs. Attaching one turns an agent that answers from what the model was trained on into one that answers from what you gave it — and can point at the source.

## Prerequisites

- `member` or higher.
- Documents you want the agent to use.

## Create a knowledge base and add documents

1. Open **Knowledge** in the sidebar.
2. Create a knowledge base and give it a name and description.
3. Upload documents to it.

Uploaded files are split into chunks, embedded, and indexed. Until a document finishes indexing it is not searchable — a large upload is not instantly available, and the document list shows where each one is up to.

Chunking is content-aware rather than a fixed cut every N characters: prose is split at roughly paragraph scale with overlap, markdown at heading boundaries, code at function and class boundaries. That is why a retrieved chunk usually reads as a coherent passage instead of a sentence sliced in half.

## Attach it to an agent

Add the knowledge base's id to the agent's `knowledge_base_ids`. The agent can then retrieve from it during a run.

Then tell the agent to use it. Retrieval being available is not the same as the agent choosing to rely on it:

```text
Answer only from the retrieved documents. If the documents do not
contain the answer, say so — do not fall back on general knowledge.
Cite the document each claim came from.
```

## Citations

Retrieved chunks carry their source document through the whole pipeline, so a grounded answer can name where each claim came from. An agent that cites nothing is usually an agent whose instructions never asked it to.

## A note on installed templates

Installing a marketplace listing does **not** bring the publisher's knowledge bases with it. Those named documents in *their* workspace, and there is nothing in yours to point them at. An installed agent that was built around a knowledge base needs one of your own attached before it behaves as its author intended.

## Expected result

Asking the agent something answerable only from your documents produces an answer drawn from them, with the source named.

## Troubleshooting

**The agent ignores the documents.** Retrieval is available but not compulsory. Instruct it explicitly, as above.

**Nothing is retrieved.** Check the documents finished indexing. A document still processing is not yet searchable.

**Answers are drawn from the wrong passages.** Usually a query-phrasing mismatch: the words in the question are not the words in the document. Adding the vocabulary your documents actually use to the system instructions helps more than raising the number of chunks retrieved.

## Related guides

- [Build and run your first agent](/docs/agent-builder/quickstart)
- [Give an agent tools](/docs/agent-builder/tools)
