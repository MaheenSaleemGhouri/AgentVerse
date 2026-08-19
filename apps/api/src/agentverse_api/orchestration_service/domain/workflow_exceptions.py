"""Domain-level errors for workflow authoring/execution. The interface
layer translates these to HTTP status codes (CLAUDE.md's shared error
envelope) — this layer never imports FastAPI/Starlette directly.
"""

from __future__ import annotations


class WorkflowNotRunnableError(Exception):
    """The workflow doesn't exist for this workspace, or has no
    published version yet. Maps to 404/409 at the interface layer,
    exactly mirroring `AgentNotRunnableError`.
    """

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"Workflow {workflow_id!r} is not runnable")


class InvalidWorkflowGraphError(Exception):
    """A submitted node/edge graph fails structural validation — a
    dangling edge reference, a cycle, a node/agent-or-team mismatch, or
    no start node. Raised before anything is persisted, so the author
    learns why at save time rather than from a run that can never
    complete (`workflow_graph.validate_workflow_graph`).
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
