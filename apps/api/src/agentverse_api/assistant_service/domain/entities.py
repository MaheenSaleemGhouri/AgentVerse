"""The assistant's domain: a session, its messages, and the doc passages
an answer is grounded in.

Zero framework imports, per the clean-architecture layering in
CLAUDE.md §3 — these types are shared by the application layer, the
repositories, and the prompt builder without any of them depending on
FastAPI or SQLAlchemy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

AssistantRole = Literal["user", "assistant"]

# Bounds. CLAUDE.md Rule 17 wants every reasoning loop bounded by step,
# cost, and time — an assistant turn is deliberately *one* provider call
# with no tool loop, so the step ceiling is structural (there is no loop
# to run away) and these three cap the rest.
MAX_QUESTION_LENGTH: Final[int] = 2_000
"""Free text reaching a prompt gets an enforced cap (CLAUDE.md §7)."""

MAX_ANSWER_TOKENS: Final[int] = 800
"""The cost ceiling. A help answer that needs more than this is a docs
page, and the assistant should link to it instead of reciting it."""

MAX_HISTORY_MESSAGES: Final[int] = 12
"""Six turns of context. Long enough to follow up ("and for teams?"),
short enough that a month-old session cannot grow an unbounded prompt."""

MAX_PASSAGES: Final[int] = 4
"""How many doc passages are assembled into one answer."""

MAX_SESSION_TITLE_LENGTH: Final[int] = 80


@dataclass(frozen=True, slots=True)
class DocPassage:
    """One heading-bounded section of a published guide.

    `url` is what the answer cites, so a reader can go check the claim —
    the transparency principle in CLAUDE.md §2 applied to the assistant:
    a grounded answer carries a link back to its source.
    """

    doc_title: str
    heading: str
    url: str
    text: str


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    id: str
    session_id: str
    role: AssistantRole
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AssistantSession:
    """A conversation, scoped to one workspace *and* one user.

    Workspace-scoped because Rule 11 admits no exceptions; additionally
    user-scoped because a help conversation is personal — a member's
    half-finished question is not something the rest of the workspace
    should read.
    """

    id: str
    workspace_id: str
    user_id: str
    title: str
    created_at: datetime
    last_message_at: datetime
