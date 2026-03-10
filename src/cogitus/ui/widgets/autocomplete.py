"""Shared helpers for input-driven autocomplete widgets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.widget import Widget
    from textual.widgets import Input, OptionList


@dataclass(frozen=True)
class _AutocompleteState:
    """Resolved autocomplete candidates and replacement target."""

    candidates: tuple[str, ...]
    replace_start: int
    replace_end: int


def autocomplete_is_visible(autocomplete: OptionList) -> bool:
    """Return whether an autocomplete popup is currently visible."""
    return not autocomplete.has_class("-hidden")


def dismiss_autocomplete(autocomplete: OptionList) -> bool:
    """Hide an autocomplete popup if it is currently visible."""
    if not autocomplete_is_visible(autocomplete):
        return False
    autocomplete.add_class("-hidden")
    autocomplete.clear_options()
    return True


def should_keep_autocomplete_open(
    *,
    focused: Widget | None,
    input_widget: Widget,
    autocomplete: OptionList,
) -> bool:
    """Return whether focus still lives inside the autocomplete flow."""
    if focused in {input_widget, autocomplete}:
        return True
    return focused is not None and autocomplete in focused.ancestors


def show_autocomplete(
    autocomplete: OptionList,
    state: _AutocompleteState,
) -> None:
    """Populate and show autocomplete suggestions for the given state."""
    autocomplete.set_options(state.candidates)
    autocomplete.highlighted = 0
    autocomplete.remove_class("-hidden")


def cycle_autocomplete(
    autocomplete: OptionList,
    direction: Literal[-1, 1],
) -> None:
    """Move the highlighted autocomplete candidate with wrap-around."""
    count = autocomplete.option_count
    if count == 0:
        return
    highlighted = autocomplete.highlighted
    if highlighted is None:
        autocomplete.highlighted = 0
        return
    autocomplete.highlighted = (highlighted + direction) % count


def apply_highlighted_autocomplete(
    *,
    state: _AutocompleteState | None,
    autocomplete: OptionList,
    input_widget: Input,
    before_input_change: Callable[[], None] | None = None,
) -> bool:
    """Apply the highlighted candidate to the input widget."""
    if state is None:
        return False
    highlighted = autocomplete.highlighted
    if highlighted is None or highlighted >= len(state.candidates):
        return False

    suggestion = state.candidates[highlighted]
    before = input_widget.value[: state.replace_start]
    after = input_widget.value[state.replace_end :]
    if before_input_change is not None:
        before_input_change()
    input_widget.value = f"{before}{suggestion}{after}"
    input_widget.cursor_position = state.replace_start + len(suggestion)
    dismiss_autocomplete(autocomplete)
    return True
