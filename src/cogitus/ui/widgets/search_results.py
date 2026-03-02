"""Dedicated active-search results view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.text import Text
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets._option_list import Option

if TYPE_CHECKING:
    from cogitus.models.idea import Idea
    from cogitus.search import SearchMatchFragment, SearchResult

_HIGHLIGHT_START = "[["
_HIGHLIGHT_END = "]]"


@dataclass(frozen=True)
class SearchResultSelection:
    """Selected match metadata in the search-results pane."""

    idea: Idea
    fragment: SearchMatchFragment | None


class SearchResultsList(OptionList):
    """Dedicated search-results list with idea headings and match rows."""

    class MatchHighlighted(Message):
        """Posted when a search match row becomes highlighted."""

        def __init__(self, selection: SearchResultSelection) -> None:
            """Initialize the message with the highlighted match selection."""
            self.selection = selection
            super().__init__()

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Initialize the dedicated search-results option list."""
        super().__init__(name=name, id=id, classes=classes)
        self._selections_by_option_id: dict[str, SearchResultSelection] = {}
        self._ordered_match_option_ids: tuple[str, ...] = ()

    def load_results(
        self,
        results: list[SearchResult],
        *,
        show_match_rows: bool,
    ) -> None:
        """Replace the option list contents with search results."""
        options: list[Option] = []
        selections: dict[str, SearchResultSelection] = {}
        ordered_ids: list[str] = []

        for result in results:
            if not show_match_rows or not result.matches:
                option_id = f"idea-{result.idea.pk}"
                options.append(
                    Option(
                        _render_idea_prompt(result),
                        id=option_id,
                    )
                )
                selections[option_id] = SearchResultSelection(
                    idea=result.idea,
                    fragment=None,
                )
                ordered_ids.append(option_id)
                continue
            options.append(
                Option(
                    _render_heading_prompt(result),
                    id=f"idea-heading-{result.idea.pk}",
                    disabled=True,
                )
            )
            for index, fragment in enumerate(result.matches):
                option_id = f"idea-{result.idea.pk}-match-{index}"
                options.append(
                    Option(
                        _render_match_prompt(fragment),
                        id=option_id,
                    )
                )
                selections[option_id] = SearchResultSelection(
                    idea=result.idea,
                    fragment=fragment,
                )
                ordered_ids.append(option_id)

        self._selections_by_option_id = selections
        self._ordered_match_option_ids = tuple(ordered_ids)
        self.set_options(options)
        if not ordered_ids:
            return
        self.highlighted = self.get_option_index(ordered_ids[0])

    def clear_results(self) -> None:
        """Clear the current search results."""
        self._selections_by_option_id.clear()
        self._ordered_match_option_ids = ()
        self.set_options([])

    def has_matches(self) -> bool:
        """Return whether the widget currently has selectable match rows."""
        return bool(self._ordered_match_option_ids)

    def is_first_match_selected(self) -> bool:
        """Return whether the first selectable match is highlighted."""
        current = self.current_selection()
        if current is None or not self._ordered_match_option_ids:
            return False
        return current[0] == self._ordered_match_option_ids[0]

    def has_next_match(self) -> bool:
        """Return whether a next selectable match exists."""
        return self.adjacent_match_id(1) is not None

    def current_selection(self) -> tuple[str, SearchResultSelection] | None:
        """Return the currently highlighted selectable match, if any."""
        if self.highlighted is None:
            return None
        option = self.get_option_at_index(self.highlighted)
        if option.id is None:
            return None
        selection = self._selections_by_option_id.get(option.id)
        if selection is None:
            return None
        return option.id, selection

    def adjacent_match_id(self, direction: int) -> str | None:
        """Return the adjacent match option ID for the current selection."""
        current = self.current_selection()
        if current is None:
            return None
        current_index = self._ordered_match_option_ids.index(current[0])
        next_index = current_index + direction
        if next_index < 0 or next_index >= len(self._ordered_match_option_ids):
            return None
        return self._ordered_match_option_ids[next_index]

    def get_selected_idea(self) -> Idea | None:
        """Return the idea backing the currently highlighted match row."""
        current = self.current_selection()
        return None if current is None else current[1].idea

    def get_selected_fragment(self) -> SearchMatchFragment | None:
        """Return the fragment backing the currently highlighted match row."""
        current = self.current_selection()
        return None if current is None else current[1].fragment

    def select_first_match_for_idea(self, idea_pk: int) -> bool:
        """Highlight the first selectable row for the given idea."""
        prefixes = (f"idea-{idea_pk}-match-", f"idea-{idea_pk}")
        for option_id in self._ordered_match_option_ids:
            if not option_id.startswith(prefixes):
                continue
            self.highlighted = self.get_option_index(option_id)
            return True
        return False

    def on_option_list_option_highlighted(
        self,
        event: OptionList.OptionHighlighted,
    ) -> None:
        """Translate highlighted option changes into match selections."""
        if event.option_id is None:
            return
        selection = self._selections_by_option_id.get(event.option_id)
        if selection is None:
            return
        self.post_message(self.MatchHighlighted(selection))

    def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        """Treat selecting a match row the same as highlighting it."""
        if event.option_id is None:
            return
        selection = self._selections_by_option_id.get(event.option_id)
        if selection is None:
            return
        self.post_message(self.MatchHighlighted(selection))


def _render_heading_prompt(result: SearchResult) -> Text:
    """Render one idea heading prompt."""
    prompt = Text(result.idea.title, style="bold")
    prompt.append("\n")
    prompt.append(result.idea.group.name, style="dim")
    return prompt


def _render_idea_prompt(result: SearchResult) -> Text:
    """Render one selectable idea row for structured-only results."""
    prompt = Text(result.idea.title, style="bold")
    prompt.append("\n")
    prompt.append(result.idea.group.name, style="dim")
    return prompt


def _render_match_prompt(fragment: SearchMatchFragment) -> Text:
    """Render one selectable match fragment prompt."""
    prompt = Text("  ")
    if fragment.source == "title":
        prompt.append("Title: ", style="dim")
    prompt.append_text(_marked_text_to_text(fragment.text))
    return prompt


def _marked_text_to_text(marked_text: str) -> Text:
    """Convert `[[...]]` highlight markers into styled Rich text."""
    text = Text()
    index = 0
    while index < len(marked_text):
        start = marked_text.find(_HIGHLIGHT_START, index)
        if start < 0:
            text.append(marked_text[index:])
            break
        if start > index:
            text.append(marked_text[index:start])
        end = marked_text.find(_HIGHLIGHT_END, start + len(_HIGHLIGHT_START))
        if end < 0:
            text.append(marked_text[start:])
            break
        text.append(
            marked_text[start + len(_HIGHLIGHT_START) : end],
            style="bold reverse",
        )
        index = end + len(_HIGHLIGHT_END)
    return text
