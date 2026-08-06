"""Installing a listing into a workspace.

Pure — no I/O, no framework.

**An installed config is untrusted input.** A listing's version snapshot
was authored in someone else's workspace and is about to become an agent
in the installer's. Copying it verbatim would carry two problems across
that boundary:

- `knowledge_base_ids` naming the *publisher's* knowledge bases. Those
  ids mean nothing in the installing workspace at best, and are a
  cross-tenant reference at worst. They are dropped, not remapped —
  there is nothing to remap them to.
- unbounded free text reaching a model prompt. `system_instructions` is
  capped here, because §7 requires every free-text field that reaches an
  LLM prompt to have an enforced size cap.

`sanitize_config` is where both happen, once, so no caller can install a
snapshot without passing through it.

**Installing copies; it does not link.** The installed agent has no
ongoing relationship with the listing. The publisher can unlist, rewrite
or delete their source agent and the install keeps working — which is
the only way a marketplace can be trusted. `MarketplaceInstall` records
where a copy came from so its provenance stays explicable, and nothing
reads back through it at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

#: Caps on the fields that reach a model prompt. Generous enough that no
#: real listing hits them, small enough that a hostile snapshot cannot
#: turn one install into an expensive run.
MAX_SYSTEM_INSTRUCTIONS = 20_000
MAX_TOOLS = 32
MAX_MODEL_NAME = 64

#: Ceilings on the sampling parameters, mirroring what the agent builder
#: itself accepts. A snapshot claiming `max_output_tokens: 10_000_000`
#: would otherwise be installed and then fail at run time, in the
#: installer's workspace, on the installer's bill.
MAX_OUTPUT_TOKENS_CEILING = 32_000


class UninstallableConfigError(Exception):
    """The snapshot cannot become an agent. Maps to HTTP 422.

    Carries every problem rather than the first: a listing whose snapshot
    is broken is the publisher's bug, and the installer reporting it
    needs to be able to say what is actually wrong.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True, slots=True)
class ImportedConfig:
    """A snapshot validated and reduced to what may cross the boundary.

    Deliberately not the publisher's dict: anything this dataclass does
    not name is dropped, so a field added to agent configuration in the
    future cannot ride into another workspace through an old snapshot
    until someone decides it should.
    """

    model: str
    system_instructions: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    tools: list[str] = field(default_factory=list)


def sanitize_config(raw: dict[str, object]) -> ImportedConfig:
    """Validate a version snapshot into something installable.

    Rejects rather than repairs where the value is meaningful (a missing
    model, an out-of-range temperature) and drops silently only where the
    field cannot mean anything in the installing workspace
    (`knowledge_base_ids`).
    """
    problems: list[str] = []

    model = raw.get("model")
    if not isinstance(model, str) or not model.strip():
        problems.append("The published version names no model, so it cannot be run.")
        model = ""
    elif len(model) > MAX_MODEL_NAME:
        problems.append(f"Model name exceeds {MAX_MODEL_NAME} characters.")

    instructions = raw.get("system_instructions", "")
    if not isinstance(instructions, str):
        problems.append("System instructions must be text.")
        instructions = ""
    elif len(instructions) > MAX_SYSTEM_INSTRUCTIONS:
        problems.append(f"System instructions exceed {MAX_SYSTEM_INSTRUCTIONS} characters.")

    temperature = raw.get("temperature")
    if temperature is not None:
        if not isinstance(temperature, int | float) or isinstance(temperature, bool):
            problems.append("Temperature must be a number.")
            temperature = None
        elif not 0.0 <= float(temperature) <= 2.0:
            problems.append("Temperature must be between 0 and 2.")
            temperature = None

    max_tokens = raw.get("max_output_tokens")
    if max_tokens is not None:
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
            problems.append("Maximum output tokens must be a whole number.")
            max_tokens = None
        elif not 1 <= max_tokens <= MAX_OUTPUT_TOKENS_CEILING:
            problems.append(
                f"Maximum output tokens must be between 1 and {MAX_OUTPUT_TOKENS_CEILING}."
            )
            max_tokens = None

    raw_tools = raw.get("tools", [])
    tools: list[str] = []
    if raw_tools is not None:
        if not isinstance(raw_tools, list):
            problems.append("Tools must be a list.")
        else:
            tools = [tool for tool in raw_tools if isinstance(tool, str) and tool.strip()]
            if len(tools) != len(raw_tools):
                problems.append("Every tool must be named as text.")
            if len(tools) > MAX_TOOLS:
                problems.append(f"A published version may declare at most {MAX_TOOLS} tools.")

    if problems:
        raise UninstallableConfigError(problems)

    return ImportedConfig(
        model=str(model),
        system_instructions=str(instructions),
        temperature=float(temperature) if temperature is not None else None,
        max_output_tokens=int(max_tokens) if max_tokens is not None else None,
        tools=tools,
        # `knowledge_base_ids` is absent by construction. It named the
        # publisher's knowledge bases, and there is nothing in the
        # installing workspace to remap it to.
    )


@dataclass(frozen=True, slots=True)
class MarketplaceInstall:
    """Provenance for one copy: which listing, at which version, became
    which agent in which workspace.

    Nothing reads back through this at run time — the installed agent is
    a copy and stands alone. It exists so a workspace can answer "where
    did this agent come from, and is there a newer version?" and so the
    catalog's install count can be reconciled against real rows.
    """

    id: str
    workspace_id: str
    listing_id: str
    version_number: int
    #: The agent this became. Nullable because agents are deletable and
    #: the provenance record outlives them — a dangling id here means the
    #: installer removed the copy, not that the install never happened.
    agent_id: str | None
    installed_by_user_id: str
    created_at: datetime
    updated_at: datetime


def is_upgrade(*, installed_version: int, latest_version: int) -> bool:
    """Is there a newer published version than the one installed?

    Strictly greater: re-installing the same version is not an upgrade,
    and offering "update" for it would be a button that does nothing.
    """
    return latest_version > installed_version
