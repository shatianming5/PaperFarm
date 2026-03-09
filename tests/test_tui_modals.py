"""Tests for TUI modal screens."""


def test_goal_input_modal_import():
    """GoalInputModal should be importable."""
    from open_researcher.tui.modals import GoalInputModal

    modal = GoalInputModal()
    assert modal is not None


def test_goal_input_modal_is_modal_screen():
    """GoalInputModal should be a ModalScreen returning str or None."""
    from textual.screen import ModalScreen

    from open_researcher.tui.modals import GoalInputModal

    modal = GoalInputModal()
    assert isinstance(modal, ModalScreen)
