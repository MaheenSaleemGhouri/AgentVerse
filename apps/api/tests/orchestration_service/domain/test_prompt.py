"""Unit tests for `domain.prompt`'s transition rules — pure, zero I/O."""

from __future__ import annotations

import pytest

from agentverse_api.orchestration_service.domain.prompt import (
    InvalidPromptVersionTransitionError,
    PromptVersionStatus,
    assert_transition,
    can_transition,
)


class TestTransitions:
    def test_draft_can_go_active(self) -> None:
        assert can_transition(
            current=PromptVersionStatus.DRAFT, target=PromptVersionStatus.ACTIVE
        )

    def test_draft_can_be_archived_without_ever_activating(self) -> None:
        assert can_transition(
            current=PromptVersionStatus.DRAFT, target=PromptVersionStatus.ARCHIVED
        )

    def test_active_can_be_archived_by_a_newer_version(self) -> None:
        assert can_transition(
            current=PromptVersionStatus.ACTIVE, target=PromptVersionStatus.ARCHIVED
        )

    def test_active_cannot_go_back_to_draft(self) -> None:
        # Immutability once active (domain.prompt's own docstring) means
        # there is no path back to an editable state.
        assert not can_transition(
            current=PromptVersionStatus.ACTIVE, target=PromptVersionStatus.DRAFT
        )

    def test_archived_is_terminal(self) -> None:
        assert not can_transition(
            current=PromptVersionStatus.ARCHIVED, target=PromptVersionStatus.ACTIVE
        )
        assert not can_transition(
            current=PromptVersionStatus.ARCHIVED, target=PromptVersionStatus.DRAFT
        )

    def test_assert_transition_raises_with_both_states_on_an_illegal_move(self) -> None:
        with pytest.raises(InvalidPromptVersionTransitionError) as exc_info:
            assert_transition(
                current=PromptVersionStatus.ARCHIVED, target=PromptVersionStatus.ACTIVE
            )
        assert exc_info.value.current is PromptVersionStatus.ARCHIVED
        assert exc_info.value.target is PromptVersionStatus.ACTIVE

    def test_assert_transition_is_silent_on_a_legal_move(self) -> None:
        assert_transition(current=PromptVersionStatus.DRAFT, target=PromptVersionStatus.ACTIVE)
