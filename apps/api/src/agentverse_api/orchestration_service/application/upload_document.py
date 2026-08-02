"""Upload admission: validate → store → record → enqueue.

The security posture here is the one `docs/roadmap.md` Phase 5 names as a
primary gate (CLAUDE.md §10):

- **Size-capped** before anything is written, so one upload cannot pin a
  worker's memory or run up unbounded embedding spend.
- **Content-sniffed**, never trusting the client's declared MIME type or
  file extension. A `.txt` that is really a PDF is stored and parsed as a
  PDF; a file we cannot positively identify must decode as UTF-8 text or
  it is rejected.
- **Generated filename** — the client's filename never influences the
  storage path (`build_storage_key`), only a cosmetic allowlisted
  extension.
- Stored outside any web-served directory; nothing serves these bytes
  back over HTTP.

Ingestion itself is a Phase 3 background job (Rule 14) — this function
returns as soon as the bytes are durable and the job is enqueued.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_shared.storage.document_store import DocumentStore, build_storage_key

from agentverse_api.orchestration_service.domain.knowledge_entities import KbDocument
from agentverse_api.orchestration_service.domain.ports.knowledge_repository import (
    KnowledgeRepository,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)

#: Magic-byte signatures we can positively identify. Deliberately short:
#: this is an admission check, not a parser. The worker's extractor
#: re-sniffs before choosing how to read the bytes, so a file that slips
#: through as "text" here still cannot reach the PDF parser there.
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"

#: Signatures that are definitively *not* documents. Checked explicitly so
#: the rejection message can say what was actually uploaded, rather than
#: the generic "not valid UTF-8" a binary would otherwise produce.
_REJECTED_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF8", "GIF image"),
    (b"\x7fELF", "Linux executable"),
    (b"MZ", "Windows executable"),
    (b"\x1f\x8b", "gzip archive"),
    (b"%!PS", "PostScript file"),
    (b"\xd0\xcf\x11\xe0", "legacy Office document (.doc/.xls) — save as .docx first"),
)

_DOCX_EXTENSIONS = (".docx", ".docm")


class UploadRejectedError(ValueError):
    """The upload cannot be accepted. Carries a message safe to show the
    user — it names what was wrong with *their* file and never leaks
    internal paths or parser internals.
    """


@dataclass(frozen=True, slots=True)
class UploadResult:
    document: KbDocument
    job_id: str


def sniff_content_type(data: bytes, *, filename: str) -> str:
    """Returns the type we will treat these bytes as.

    Raises `UploadRejectedError` for anything we cannot ingest. The
    declared content type is not an input — a client can set it to
    anything, so trusting it would make this check decorative.
    """
    if not data:
        raise UploadRejectedError("The file is empty.")

    if data.startswith(_PDF_MAGIC):
        return "application/pdf"

    if data.startswith(_ZIP_MAGIC):
        if not filename.lower().endswith(_DOCX_EXTENSIONS):
            raise UploadRejectedError("Zip-based files are only supported as .docx Word documents.")
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    for signature, label in _REJECTED_SIGNATURES:
        if data.startswith(signature):
            raise UploadRejectedError(f"{label} files cannot be added to a knowledge base.")

    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadRejectedError(
            "The file is not a supported document type. "
            "Supported: PDF, Word (.docx), and UTF-8 text (.txt, .md, .csv, .json)."
        ) from exc

    return _text_type_for(filename)


def _text_type_for(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".json"):
        return "application/json"
    if lowered.endswith((".csv", ".tsv")):
        return "text/csv"
    if lowered.endswith((".md", ".markdown", ".mdx")):
        return "text/markdown"
    return "text/plain"


async def upload_document(
    *,
    workspace_id: str,
    knowledge_base_id: str,
    filename: str,
    data: bytes,
    max_bytes: int,
    repo: KnowledgeRepository,
    store: DocumentStore,
    producer: JobQueueProducer,
    workspace_quota_bytes: int | None = None,
) -> UploadResult:
    """`max_bytes` caps a *single* file (a platform safety limit);
    `workspace_quota_bytes` caps the workspace's total stored bytes from
    its configured `storage_limit_mb`, or is `None` when the admin has
    set no limit. Both are checked before any byte is written.
    """
    if len(data) > max_bytes:
        raise UploadRejectedError(
            f"The file is {len(data) // (1024 * 1024)} MB. "
            f"The limit is {max_bytes // (1024 * 1024)} MB."
        )

    if workspace_quota_bytes is not None:
        used = await repo.sum_stored_bytes(workspace_id=workspace_id)
        if used + len(data) > workspace_quota_bytes:
            # Admission, not enforcement-after-the-fact: rejecting here
            # means the quota can never be exceeded, whereas a background
            # reconciler would let it be breached first.
            raise UploadRejectedError(
                f"This workspace has used {used // (1024 * 1024)} MB of its "
                f"{workspace_quota_bytes // (1024 * 1024)} MB storage limit, and this "
                f"file needs {max(len(data) // (1024 * 1024), 1)} MB more. "
                "Delete documents or raise the limit in workspace settings."
            )

    # Re-resolved from the caller's authenticated workspace, and checked
    # here rather than only in the router: a knowledge base belonging to
    # another tenant must be indistinguishable from one that doesn't
    # exist (Rule 11).
    kb = await repo.get_knowledge_base(
        workspace_id=workspace_id, knowledge_base_id=knowledge_base_id
    )
    if kb is None:
        raise KnowledgeBaseNotFoundError(knowledge_base_id)

    content_type = sniff_content_type(data, filename=filename)
    storage_key = build_storage_key(workspace_id=workspace_id, original_filename=filename)

    # Bytes are written before the row exists. The reverse order would
    # leave a `pending` document whose file is missing if the write
    # failed, and the ingestion job would have to distinguish "not
    # uploaded yet" from "lost". An orphaned file, by contrast, is inert.
    await store.put(storage_key, data)

    document = await repo.create_document(
        workspace_id=workspace_id,
        knowledge_base_id=knowledge_base_id,
        storage_key=storage_key,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(data),
    )
    job_id, _ = await producer.enqueue_kb_ingest(kb_document_id=document.id)
    return UploadResult(document=document, job_id=job_id)


class KnowledgeBaseNotFoundError(LookupError):
    def __init__(self, knowledge_base_id: str) -> None:
        super().__init__(f"knowledge base {knowledge_base_id} not found")
        self.knowledge_base_id = knowledge_base_id
