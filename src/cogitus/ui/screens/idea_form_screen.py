"""Modal screens for idea create/edit, delete confirm, help, and about."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, ClassVar, Literal

from rich.table import Table
from rich.text import Text
from textual import on
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    OptionList,
    ProgressBar,
    Rule,
    Select,
    Static,
)

from cogitus.backends import BackendConfig
from cogitus.config import (
    DEFAULT_EDIT_BODY_CURSOR_MODE,
    DataBackendMode,
    EditBodyCursorMode,
)
from cogitus.metadata import AppMetadata, get_about_entries
from cogitus.ui.widgets.autocomplete import (
    _AutocompleteState,
    apply_highlighted_autocomplete,
    autocomplete_is_visible,
    cycle_autocomplete,
    dismiss_autocomplete,
    should_keep_autocomplete_open,
    show_autocomplete,
)
from cogitus.ui.widgets.select_all import (
    SelectAllInput,
    handle_select_all_key,
    select_all_focused_text,
)
from cogitus.ui.widgets.text_area import CogitusTextArea

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult
    from textual.events import Key, Resize
    from textual.widget import Widget

    from cogitus.backends.protocols import IdeaBackend
    from cogitus.models.idea import Idea


@dataclass(frozen=True)
class _IdeaFormState:
    """Normalized form state used for unsaved-change detection."""

    title: str
    body: str
    tags: tuple[str, ...]
    group_pk: int | None


@dataclass(frozen=True)
class _IdeaSaveValues:
    """Validated form values ready for persistence."""

    title: str
    body: str
    tags: list[str]
    group_pk: int


class TagsInput(SelectAllInput):
    """Input that delegates comma-accept behavior to IdeaFormScreen."""

    def on_key(self, event: Key) -> None:
        """Intercept comma for autocomplete accept+next token."""
        if event.key in {",", "comma"}:
            # Contract: parent screen may implement
            # _accept_tag_suggestion_and_next_from_input() -> bool.
            handler = getattr(
                self.screen,
                "_accept_tag_suggestion_and_next_from_input",
                None,
            )
            if callable(handler) and handler():
                event.prevent_default()
                event.stop()
                return


class IdeaFormScreen(ModalScreen[int | None]):
    """Modal form for creating or editing an idea."""

    INLINE_TAGS_GROUP_MIN_WIDTH: ClassVar[int] = 90
    TAGS_AUTOCOMPLETE_LIMIT: ClassVar[int] = 20

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding(
            "f5",
            "save",
            "Save",
            show=False,
            priority=True,
        ),
        Binding(
            "ctrl+s",
            "save_and_close",
            "Save & Close",
            show=False,
            priority=True,
        ),
    ]

    def __init__(
        self,
        service: IdeaBackend,
        idea: Idea | None = None,
        *,
        initial_group_pk: int | None = None,
        edit_body_cursor_mode: EditBodyCursorMode = (
            DEFAULT_EDIT_BODY_CURSOR_MODE
        ),
        on_saved: Callable[[int], None] | None = None,
    ) -> None:
        """Initialize the idea form.

        Args:
            service: The idea backend instance.
            idea: Existing idea to edit, or None for new.
            initial_group_pk: Initial group pk for new-idea mode.
            edit_body_cursor_mode: Cursor mode for edit form body.
            on_saved: Optional callback for successful stay-open saves.
        """
        super().__init__()
        self._service = service
        self._idea = idea
        self._initial_group_pk = initial_group_pk
        self._edit_body_cursor_mode = edit_body_cursor_mode
        self._on_saved = on_saved
        self._tag_usage_by_name: tuple[tuple[str, int], ...] = ()
        self._tag_autocomplete_state: _AutocompleteState | None = None
        self._suspend_tag_autocomplete_sync = False
        self._initial_form_state = self._build_initial_form_state(idea)
        self._focus_after_cancel_reject: Widget | None = None

    def compose(self) -> ComposeResult:
        """Compose the idea form."""
        idea = self._idea
        is_edit = idea is not None
        form_title = "Edit Idea" if is_edit else "New Idea"
        group_value = self._get_existing_group_pk()
        group_options = self._group_options()

        with Vertical(id="idea-form-container"):
            yield Static(form_title, id="form-title")
            with VerticalScroll(id="idea-form-scroll"):
                yield Label("Title")
                yield SelectAllInput(
                    value=idea.title if idea else "",
                    placeholder="Idea title...",
                    id="title-input",
                )
                yield Label("Body (Markdown)")
                yield CogitusTextArea(
                    text=idea.body if idea else "",
                    id="body-input",
                    language="markdown",
                )
                with Container(id="tags-group-row"):
                    with Vertical(id="tags-column"):
                        yield Label("Tags (comma-separated)")
                        yield TagsInput(
                            value=(
                                self._get_existing_tags() if is_edit else ""
                            ),
                            placeholder=(
                                "python, architecture, performance..."
                            ),
                            id="tags-input",
                        )
                        yield OptionList(
                            id="tags-autocomplete",
                            classes="-hidden",
                        )
                    with Vertical(id="group-column"):
                        yield Label("Group")
                        yield Select[int](
                            options=group_options,
                            value=group_value,
                            allow_blank=False,
                            id="group-select",
                        )
            with Horizontal(id="form-buttons"):
                yield Button(
                    r"Save \[F5]",
                    variant="primary",
                    id="save-btn",
                )
                yield Button(
                    r"Save & Close \[Ctrl+s]",
                    variant="success",
                    id="save-close-btn",
                )
                yield Button(
                    r"Cancel \[Esc]",
                    variant="default",
                    id="cancel-btn",
                )

    def on_mount(self) -> None:
        """Initialize responsive layout and initial form focus."""
        self._update_tags_group_row_layout(self.size.width)
        self._load_tag_autocomplete_source()
        if self._idea is None:
            self._initial_form_state = self._current_form_state()
            title = self.query_one("#title-input", Input)
            title.focus()
            title.cursor_position = 0
            return

        body = self.query_one("#body-input", CogitusTextArea)
        body.focus()
        body.cursor_location = self._cursor_location_from_index(
            body.text,
            self._initial_edit_body_cursor_index(body),
        )

    def on_resize(self, event: Resize) -> None:
        """Stack tags/group controls on narrow viewports."""
        self._update_tags_group_row_layout(event.size.width)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update tags autocomplete when tags input value changes."""
        if event.input.id != "tags-input":
            return
        if self._suspend_tag_autocomplete_sync:
            self._suspend_tag_autocomplete_sync = False
            return
        self._sync_tag_autocomplete()

    def on_input_blurred(self, event: Input.Blurred) -> None:
        """Hide tags autocomplete when tags input loses focus."""
        if event.input.id == "tags-input":
            self.call_later(self._dismiss_tag_autocomplete_if_unfocused)

    def _dismiss_tag_autocomplete_if_unfocused(self) -> None:
        """Dismiss suggestions unless focus moved to input/autocomplete."""
        tags_input = self.query_one("#tags-input", Input)
        autocomplete = self.query_one("#tags-autocomplete", OptionList)
        if should_keep_autocomplete_open(
            focused=self.app.focused,
            input_widget=tags_input,
            autocomplete=autocomplete,
        ):
            return
        self.dismiss_tag_autocomplete()

    def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        """Apply selected tag suggestion and restore focus to tags input."""
        if event.option_list.id != "tags-autocomplete":
            return
        if self._apply_highlighted_tag_autocomplete():
            self.query_one("#tags-input", Input).focus()
        event.stop()

    def on_key(self, event: Key) -> None:
        """Handle form-level keyboard shortcuts."""
        if self._handle_select_all_key(event):
            return

        tags_input = self.query_one("#tags-input", Input)
        if (
            self.app.focused is tags_input
            and self._tag_autocomplete_is_visible()
        ):
            self._handle_tag_autocomplete_key(event)

    @on(SelectAllInput.SelectedAll, "#tags-input")
    def _handle_tags_select_all(
        self,
        event: SelectAllInput.SelectedAll,
    ) -> None:
        """Dismiss tag suggestions after selecting all tag text."""
        self.dismiss_tag_autocomplete()
        event.stop()

    def _handle_select_all_key(self, event: Key) -> bool:
        """Handle Ctrl+a/Ctrl+A select-all for focused form editors."""
        focused = self.app.focused
        if not handle_select_all_key(self, event):
            return False
        if focused is self.query_one("#tags-input", Input):
            self.dismiss_tag_autocomplete()
        return True

    def _handle_tag_autocomplete_key(self, event: Key) -> None:
        """Handle tag autocomplete navigation keys."""
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self._cycle_tag_autocomplete(1)
            return

        if event.key in {"shift+tab", "backtab"}:
            event.prevent_default()
            event.stop()
            self._cycle_tag_autocomplete(-1)
            return

        if event.key == "down":
            event.prevent_default()
            event.stop()
            self._cycle_tag_autocomplete(1)
            return

        if event.key == "up":
            event.prevent_default()
            event.stop()
            self._cycle_tag_autocomplete(-1)
            return

        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self._apply_highlighted_tag_autocomplete()
            return

        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.dismiss_tag_autocomplete()

    def _select_all_focused_editable(self) -> bool:
        """Select all text in the focused form editor when possible."""
        return select_all_focused_text(self)

    def _accept_tag_suggestion_and_next_from_input(self) -> bool:
        """Accept highlighted suggestion and insert comma+space suffix."""
        tags_input = self.query_one("#tags-input", Input)
        if (
            self.app.focused is not tags_input
            or not self._tag_autocomplete_is_visible()
        ):
            return False
        if not self._apply_highlighted_tag_autocomplete():
            return False
        # Textual 7.5 emits Input.Changed synchronously for
        # insert_text_at_cursor.
        # If this becomes async, this single-shot suppression may need redesign.
        self._suspend_tag_autocomplete_sync = True
        tags_input.insert_text_at_cursor(", ")
        return True

    def _update_tags_group_row_layout(self, width: int) -> None:
        """Toggle tags/group row between horizontal and stacked layout."""
        row = self.query_one("#tags-group-row", Container)
        row.set_class(width < self.INLINE_TAGS_GROUP_MIN_WIDTH, "narrow")

    def _load_tag_autocomplete_source(self) -> None:
        """Load tag suggestion names and usage counts from the service."""
        self._tag_usage_by_name = tuple(
            (tag.name, usage)
            for tag, usage in self._service.list_tags_with_usage()
        )

    def dismiss_tag_autocomplete(self) -> bool:
        """Hide tags autocomplete popup if currently visible."""
        autocomplete = self.query_one("#tags-autocomplete", OptionList)
        if not dismiss_autocomplete(autocomplete):
            return False
        self._tag_autocomplete_state = None
        return True

    def _tag_autocomplete_is_visible(self) -> bool:
        """Return whether tags autocomplete is visible."""
        autocomplete = self.query_one("#tags-autocomplete", OptionList)
        return autocomplete_is_visible(autocomplete)

    def _sync_tag_autocomplete(self) -> None:
        """Recompute tags autocomplete state for current token/cursor."""
        tags_input = self.query_one("#tags-input", Input)
        if self.app.focused is not tags_input:
            self.dismiss_tag_autocomplete()
            return
        state = self._resolve_tag_autocomplete_state(
            tags_input.value,
            cursor_position=tags_input.cursor_position,
        )
        if state is None:
            self.dismiss_tag_autocomplete()
            return
        self._tag_autocomplete_state = state
        autocomplete = self.query_one("#tags-autocomplete", OptionList)
        show_autocomplete(autocomplete, state)

    def _resolve_tag_autocomplete_state(
        self,
        value: str,
        *,
        cursor_position: int,
    ) -> _AutocompleteState | None:
        """Resolve candidates and replacement range for current tag token."""
        token_start, token_end = self._tag_token_bounds(value, cursor_position)
        token = value[token_start:token_end]
        normalized = token.strip().lower()
        if not normalized:
            return None
        candidates = self._tag_candidates_for(normalized)
        if not candidates:
            return None

        left_spaces = len(token) - len(token.lstrip())
        right_spaces = len(token) - len(token.rstrip())
        replace_start = token_start + left_spaces
        replace_end = token_end - right_spaces
        replace_end = max(replace_end, replace_start)
        return _AutocompleteState(
            candidates=candidates,
            replace_start=replace_start,
            replace_end=replace_end,
        )

    def _tag_candidates_for(self, normalized: str) -> tuple[str, ...]:
        """Return ranked tag candidates for the normalized token text."""
        prefix: list[tuple[str, int]] = []
        contains: list[tuple[str, int]] = []
        for name, usage in self._tag_usage_by_name:
            if name.startswith(normalized):
                prefix.append((name, usage))
                continue
            if normalized in name:
                contains.append((name, usage))

        def rank_key(item: tuple[str, int]) -> tuple[int, str]:
            """Sort by usage descending and then name ascending."""
            return (-item[1], item[0])

        prefix.sort(key=rank_key)
        contains.sort(key=rank_key)
        ranked = [name for name, _usage in prefix + contains]
        return tuple(ranked[: self.TAGS_AUTOCOMPLETE_LIMIT])

    @staticmethod
    def _tag_token_bounds(value: str, cursor_position: int) -> tuple[int, int]:
        """Return current comma-delimited token bounds around the cursor."""
        cursor = max(0, min(cursor_position, len(value)))
        start = cursor
        end = cursor
        while start > 0 and value[start - 1] != ",":
            start -= 1
        while end < len(value) and value[end] != ",":
            end += 1
        return start, end

    def _cycle_tag_autocomplete(self, direction: Literal[-1, 1]) -> None:
        """Move highlighted tag candidate with wrap-around."""
        autocomplete = self.query_one("#tags-autocomplete", OptionList)
        cycle_autocomplete(autocomplete, direction)

    def _apply_highlighted_tag_autocomplete(self) -> bool:
        """Apply highlighted candidate to current tag token."""
        autocomplete = self.query_one("#tags-autocomplete", OptionList)
        tags_input = self.query_one("#tags-input", Input)
        return apply_highlighted_autocomplete(
            state=self._tag_autocomplete_state,
            autocomplete=autocomplete,
            input_widget=tags_input,
            before_input_change=self._suspend_tag_autocomplete_sync_once,
        )

    def _suspend_tag_autocomplete_sync_once(self) -> None:
        """Suppress the next programmatic Input.Changed event."""
        # Textual 7.5 emits Input.Changed synchronously for value assignment.
        # If this becomes async, this single-shot suppression may need redesign.
        self._suspend_tag_autocomplete_sync = True

    def _initial_edit_body_cursor_index(self, body: CogitusTextArea) -> int:
        """Return initial cursor index for edit mode body."""
        body_len = len(body.text)
        if self._edit_body_cursor_mode == EditBodyCursorMode.START:
            return 0
        if self._edit_body_cursor_mode == EditBodyCursorMode.END:
            return body_len
        if self._idea is None:
            return 0
        remembered = self._service.get_idea_cursor_position(self._idea.pk)
        if remembered is None:
            return 0
        return max(0, min(body_len, remembered))

    def _persist_edit_cursor_position(self) -> None:
        """Persist current edit body cursor position when editing an idea."""
        if self._idea is None:
            return
        body = self.query_one("#body-input", CogitusTextArea)
        index = self._cursor_index_from_location(
            body.text, body.cursor_location
        )
        self._service.set_idea_cursor_position(self._idea.pk, index)

    @staticmethod
    def _cursor_location_from_index(text: str, index: int) -> tuple[int, int]:
        """Convert a linear cursor index to a (line, column) location."""
        clamped = max(0, min(len(text), index))
        line_no = 0
        column = 0
        for char in text[:clamped]:
            if char == "\n":
                line_no += 1
                column = 0
            else:
                column += 1
        return (line_no, column)

    @staticmethod
    def _cursor_index_from_location(
        text: str,
        location: tuple[int, int],
    ) -> int:
        """Convert a (line, column) cursor location to a linear index."""
        lines = text.split("\n")
        line_no = max(0, min(location[0], len(lines) - 1))
        column = max(0, min(location[1], len(lines[line_no])))
        line_prefix_len = sum(len(line) + 1 for line in lines[:line_no])
        return min(len(text), line_prefix_len + column)

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for dirty-state comparison."""
        return title.strip()

    @staticmethod
    def _normalize_tags(tags: list[str]) -> tuple[str, ...]:
        """Normalize tags to match save-time semantics."""
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            normalized = tag.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return tuple(result)

    def _build_initial_form_state(
        self,
        idea: Idea | None,
    ) -> _IdeaFormState | None:
        """Build the initial existing-idea snapshot for unsaved checks."""
        if idea is None:
            return None
        return _IdeaFormState(
            title=self._normalize_title(idea.title),
            body=idea.body,
            tags=self._normalize_tags(
                [tag.name for tag in idea.tags.fetch_all()]
            ),
            group_pk=idea.group.pk,
        )

    def _current_form_state(self) -> _IdeaFormState:
        """Return the normalized current state of the form."""
        group_value = self.query_one("#group-select", Select).value
        group_pk = group_value if isinstance(group_value, int) else None
        return _IdeaFormState(
            title=self._normalize_title(
                self.query_one("#title-input", Input).value
            ),
            body=self.query_one("#body-input", CogitusTextArea).text,
            tags=self._normalize_tags(
                self.query_one("#tags-input", Input).value.split(",")
            ),
            group_pk=group_pk,
        )

    def _has_unsaved_changes(self) -> bool:
        """Return whether the form differs from its initial state."""
        if self._initial_form_state is None:
            return False
        return self._current_form_state() != self._initial_form_state

    def _dismiss_canceled_form(self) -> None:
        """Persist edit cursor state and close the form."""
        self._persist_edit_cursor_position()
        self.dismiss(None)

    def _restore_focus_after_cancel_reject(self) -> None:
        """Restore focus to the pre-confirmation widget when possible."""
        focus_target = self._focus_after_cancel_reject
        self._focus_after_cancel_reject = None
        if focus_target is None or focus_target.screen is not self:
            return
        self.call_after_refresh(focus_target.focus)

    def _on_discard_confirm(self, *, confirmed: bool) -> None:
        """Handle the discard-changes confirmation result."""
        if confirmed:
            self._focus_after_cancel_reject = None
            self._dismiss_canceled_form()
            return
        self._restore_focus_after_cancel_reject()

    @staticmethod
    def _editable_focus_target(widget: Widget | None) -> Widget | None:
        """Return a focus target only for editable form controls."""
        if isinstance(widget, (Input, Select, CogitusTextArea)):
            return widget
        return None

    def _confirm_discard_changes(self) -> None:
        """Prompt before discarding unsaved form changes."""
        focused = self.app.focused
        if focused is not None and focused.screen is self:
            self._focus_after_cancel_reject = self._editable_focus_target(
                focused
            )
        else:
            self._focus_after_cancel_reject = None
        self.app.push_screen(
            ConfirmDialog("Discard unsaved changes?"),
            callback=lambda confirmed: self._on_discard_confirm(
                confirmed=confirmed
            ),
        )

    def _get_existing_tags(self) -> str:
        """Get comma-separated tags from the idea."""
        if self._idea is None:
            return ""
        tags = self._idea.tags.fetch_all()
        return ", ".join(t.name for t in tags)

    def _group_options(self) -> list[tuple[str, int]]:
        """Build Select options for available groups."""
        groups = self._service.list_groups()
        return [(group.name, group.pk) for group in groups]

    def _get_existing_group_pk(self) -> int:
        """Return selected group pk for edit mode or create defaults."""
        if self._idea is not None:
            return self._idea.group.pk
        if self._initial_group_pk is not None and self._is_existing_group_pk(
            self._initial_group_pk
        ):
            return self._initial_group_pk
        return self._get_default_group_pk()

    def _is_existing_group_pk(self, group_pk: int) -> bool:
        """Return whether the given group pk exists."""
        groups = self._service.list_groups()
        return any(group.pk == group_pk for group in groups)

    def _get_default_group_pk(self) -> int:
        """Return default group pk (fallback to first available group)."""
        groups = self._service.list_groups()
        if not groups:
            created = self._service.create_group(
                self._service.default_group_name
            )
            return created.pk
        for group in groups:
            if group.name == self._service.default_group_name:
                return group.pk
        return groups[0].pk

    @on(Button.Pressed, "#save-btn")
    def _handle_save_button(self) -> None:
        """Save the idea when the save button is pressed."""
        self.action_save()

    @on(Button.Pressed, "#save-close-btn")
    def _handle_save_close_button(self) -> None:
        """Save and close the form when the save-and-close button is pressed."""
        self.action_save_and_close()

    @on(Button.Pressed, "#cancel-btn")
    def _handle_cancel_button(self) -> None:
        """Cancel the form when the cancel button is pressed."""
        self.action_cancel()

    def _save_idea(self) -> tuple[bool, int | None]:
        """Persist form values and return success with the saved idea pk."""
        values = self._collect_save_values()
        if values is None:
            return (False, None)

        if self._idea is not None:
            return self._update_existing_idea(self._idea.pk, values)
        return self._create_new_idea(values)

    def _collect_save_values(self) -> _IdeaSaveValues | None:
        """Return validated form values or notify about validation failure."""
        title = self.query_one("#title-input", Input).value.strip()
        if not title:
            self.notify("Title is required", severity="error")
            self.query_one("#title-input", Input).focus()
            return None

        body = self.query_one("#body-input", CogitusTextArea).text
        tags_str = self.query_one("#tags-input", Input).value
        group_value = self.query_one("#group-select", Select).value
        tags = (
            [t.strip() for t in tags_str.split(",") if t.strip()]
            if tags_str.strip()
            else []
        )
        if not isinstance(group_value, int):
            self.notify("Invalid group selection", severity="error")
            return None

        return _IdeaSaveValues(
            title=title,
            body=body,
            tags=tags,
            group_pk=group_value,
        )

    def _update_existing_idea(
        self,
        idea_pk: int,
        values: _IdeaSaveValues,
    ) -> tuple[bool, int | None]:
        """Update the current idea and return success with saved idea pk."""
        try:
            result = self._service.update_idea(
                pk=idea_pk,
                title=values.title,
                body=values.body,
                tags=values.tags,
                group_pk=values.group_pk,
            )
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return (False, None)
        pk = result.pk if result else None
        if result is not None:
            self._idea = result
        self._persist_edit_cursor_position()
        return (True, pk)

    def _create_new_idea(
        self,
        values: _IdeaSaveValues,
    ) -> tuple[bool, int | None]:
        """Create an idea and return success with saved idea pk."""
        try:
            idea = self._service.create_idea(
                title=values.title,
                body=values.body,
                tags=values.tags or None,
                group_pk=values.group_pk,
            )
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return (False, None)
        self._idea = idea
        return (True, idea.pk)

    def action_save(self) -> None:
        """Save the idea and keep the form open."""
        saved, pk = self._save_idea()
        if not saved:
            return
        self._initial_form_state = self._current_form_state()
        self._load_tag_autocomplete_source()
        self.notify("Idea saved")
        if self._on_saved is not None and pk is not None:
            self._on_saved(pk)

    def action_save_and_close(self) -> None:
        """Save the idea and dismiss the form."""
        saved, pk = self._save_idea()
        if not saved:
            return
        self.dismiss(pk)

    def action_cancel(self) -> None:
        """Cancel and dismiss."""
        if self._has_unsaved_changes():
            self._confirm_discard_changes()
            return
        self._dismiss_canceled_form()


class ConfirmDialog(ModalScreen[bool]):
    """Simple yes/no confirmation dialog."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("y", "confirm", "Yes", show=False),
        Binding("n", "cancel", "No", show=False),
    ]

    def __init__(self, message: str) -> None:
        """Initialize the confirmation dialog.

        Args:
            message: The confirmation message to display.
        """
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        """Compose the confirmation dialog."""
        with Vertical(id="confirm-container"):
            yield Static(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button(
                    r"Yes \[Y]",
                    variant="error",
                    id="confirm-yes-btn",
                )
                yield Button(
                    r"No \[N]",
                    variant="default",
                    id="confirm-no-btn",
                )

    @on(Button.Pressed, "#confirm-yes-btn")
    def _handle_confirm_button(self) -> None:
        """Confirm the dialog when the yes button is pressed."""
        self.action_confirm()

    @on(Button.Pressed, "#confirm-no-btn")
    def _handle_cancel_button(self) -> None:
        """Cancel the dialog when the no button is pressed."""
        self.action_cancel()

    def action_confirm(self) -> None:
        """Confirm the action."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel the action."""
        self.dismiss(False)


class RemoteStartupRecoveryAction(str, Enum):
    """Actions offered when the initial remote sync fails."""

    RETRY = "retry"
    USE_CACHE = "use_cache"
    SWITCH_LOCAL = "switch_local"
    QUIT = "quit"


class RemoteStartupRecoveryScreen(
    ModalScreen[RemoteStartupRecoveryAction],
):
    """Recovery modal shown when remote mode fails during startup."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "retry", "Retry", show=False),
        Binding("c", "use_cache", "Use Cache", show=False),
        Binding("l", "switch_local", "Local Mode", show=False),
        Binding("q,escape", "quit_app", "Quit", show=False),
    ]

    def __init__(self, message: str) -> None:
        """Initialize the recovery modal with the sync failure message."""
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        """Compose the startup recovery dialog."""
        with Vertical(id="remote-startup-container"):
            yield Static("Remote Sync Failed", id="form-title")
            yield Static(
                (
                    f"{self._message}\n\n"
                    "Using cached remote data puts Cogitus into "
                    "READ-ONLY mode until remote sync succeeds again.\n"
                    "Cached remote data may be stale or empty.\n"
                    "Switching to local mode uses a separate local SQLite "
                    "database, which may differ from the remote data.\n"
                    "Local fallback only applies to this session and does "
                    "not sync changes back automatically."
                ),
                id="remote-startup-message",
            )
            with Horizontal(id="remote-startup-buttons"):
                yield Button(
                    r"Retry \[R]",
                    variant="primary",
                    id="retry-remote-btn",
                )
                yield Button(
                    r"Use Cache \[C]",
                    variant="default",
                    id="use-cache-btn",
                )
                yield Button(
                    r"Use Local \[L]",
                    variant="default",
                    id="use-local-btn",
                )
                yield Button(
                    r"Quit \[Q]",
                    variant="error",
                    id="quit-startup-btn",
                )

    @on(Button.Pressed, "#retry-remote-btn")
    def _handle_retry_button(self) -> None:
        """Retry the remote connection when requested."""
        self.action_retry()

    @on(Button.Pressed, "#use-cache-btn")
    def _handle_use_cache_button(self) -> None:
        """Continue with cached remote data when requested."""
        self.action_use_cache()

    @on(Button.Pressed, "#use-local-btn")
    def _handle_use_local_button(self) -> None:
        """Switch to session-local mode when requested."""
        self.action_switch_local()

    @on(Button.Pressed, "#quit-startup-btn")
    def _handle_quit_button(self) -> None:
        """Quit the application when requested."""
        self.action_quit_app()

    def action_retry(self) -> None:
        """Dismiss with the retry action."""
        self.dismiss(RemoteStartupRecoveryAction.RETRY)

    def action_use_cache(self) -> None:
        """Dismiss with the cached remote action."""
        self.dismiss(RemoteStartupRecoveryAction.USE_CACHE)

    def action_switch_local(self) -> None:
        """Dismiss with the session-local fallback action."""
        self.dismiss(RemoteStartupRecoveryAction.SWITCH_LOCAL)

    def action_quit_app(self) -> None:
        """Dismiss with the quit action."""
        self.dismiss(RemoteStartupRecoveryAction.QUIT)


class RemoteCloneModeAction(str, Enum):
    """Actions offered after cloning remote data into the local DB."""

    STAY_REMOTE = "stay_remote"
    SWITCH_LOCAL = "switch_local"


class RemoteCloneProgressScreen(ModalScreen[None]):
    """Modal progress view for remote-to-local clone operations."""

    def compose(self) -> ComposeResult:
        """Compose the clone-progress dialog."""
        with Vertical(id="remote-clone-container"):
            yield Static("Clone Remote To Local", id="form-title")
            yield Static(
                "Downloading remote snapshot...",
                id="remote-clone-status",
            )
            yield Label("Download")
            yield ProgressBar(
                total=None,
                show_eta=False,
                id="clone-download-progress",
            )
            yield Label("Groups")
            yield ProgressBar(
                total=1,
                show_eta=False,
                id="clone-groups-progress",
            )
            yield Label("Tags")
            yield ProgressBar(
                total=1,
                show_eta=False,
                id="clone-tags-progress",
            )
            yield Label("Ideas")
            yield ProgressBar(
                total=1,
                show_eta=False,
                id="clone-ideas-progress",
            )

    def mark_download_complete(self) -> None:
        """Mark the snapshot download phase as complete."""
        self.query_one("#remote-clone-status", Static).update(
            "Applying snapshot to local database..."
        )
        self.query_one("#clone-download-progress", ProgressBar).update(
            total=1,
            progress=1,
        )

    def update_stage_progress(
        self,
        *,
        stage: str,
        completed: int,
        total: int,
    ) -> None:
        """Update one of the per-section progress bars."""
        progress_bar = self.query_one(
            f"#clone-{stage.lower()}-progress",
            ProgressBar,
        )
        resolved_total = total if total > 0 else 1
        resolved_progress = completed if total > 0 else 1
        progress_bar.update(
            total=resolved_total,
            progress=resolved_progress,
        )


class RemoteCloneSwitchModeScreen(
    ModalScreen[RemoteCloneModeAction],
):
    """Prompt shown after cloning while currently in remote mode."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s,escape", "stay_remote", "Stay Remote", show=False),
        Binding("l", "switch_local", "Switch Local", show=False),
    ]

    def compose(self) -> ComposeResult:
        """Compose the post-clone mode choice dialog."""
        with Vertical(id="remote-clone-switch-container"):
            yield Static("Local Database Updated", id="form-title")
            yield Static(
                (
                    "The local database now matches the remote snapshot.\n\n"
                    "You are still using the remote backend for this session."
                ),
                id="remote-clone-switch-message",
            )
            with Horizontal(id="remote-clone-switch-buttons"):
                yield Button(
                    r"Stay Remote \[S]",
                    variant="default",
                    id="stay-remote-btn",
                )
                yield Button(
                    r"Use Local \[L]",
                    variant="primary",
                    id="switch-local-after-clone-btn",
                )

    @on(Button.Pressed, "#stay-remote-btn")
    def _handle_stay_remote_button(self) -> None:
        """Dismiss while keeping the current remote session."""
        self.action_stay_remote()

    @on(Button.Pressed, "#switch-local-after-clone-btn")
    def _handle_switch_local_button(self) -> None:
        """Dismiss and switch to local mode for this session."""
        self.action_switch_local()

    def action_stay_remote(self) -> None:
        """Dismiss while keeping the current remote backend active."""
        self.dismiss(RemoteCloneModeAction.STAY_REMOTE)

    def action_switch_local(self) -> None:
        """Dismiss and request a session-local switch."""
        self.dismiss(RemoteCloneModeAction.SWITCH_LOCAL)


class GroupFormScreen(ModalScreen[int | None]):
    """Modal form for creating a group."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding(
            "ctrl+s",
            "save",
            "Save",
            show=False,
            priority=True,
        ),
    ]

    def __init__(self, service: IdeaBackend) -> None:
        """Initialize the group form."""
        super().__init__()
        self._service = service

    def compose(self) -> ComposeResult:
        """Compose the group form."""
        with Vertical(id="confirm-container"):
            yield Static("New Group", id="form-title")
            yield SelectAllInput(
                placeholder="Group name...",
                id="group-name-input",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button(
                    r"Save \[Ctrl+s]",
                    variant="primary",
                    id="save-group-btn",
                )
                yield Button(
                    r"Cancel \[Esc]",
                    variant="default",
                    id="cancel-group-btn",
                )

    @on(Button.Pressed, "#save-group-btn")
    def _handle_save_button(self) -> None:
        """Create the group when the save button is pressed."""
        self.action_save()

    @on(Button.Pressed, "#cancel-group-btn")
    def _handle_cancel_button(self) -> None:
        """Cancel the group form when the cancel button is pressed."""
        self.action_cancel()

    def on_key(self, event: Key) -> None:
        """Handle text-field shortcuts."""
        handle_select_all_key(self, event)

    def action_save(self) -> None:
        """Create the group and close."""
        name = self.query_one("#group-name-input", Input).value.strip()
        if not name:
            self.notify("Group name is required", severity="error")
            return
        try:
            group = self._service.create_group(name)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self.dismiss(group.pk)

    def action_cancel(self) -> None:
        """Cancel and dismiss."""
        self.dismiss(None)


class NameInputScreen(ModalScreen[str | None]):
    """Simple modal for entering or editing a single name field."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding(
            "ctrl+s",
            "save",
            "Save",
            show=False,
            priority=True,
        ),
    ]

    def __init__(
        self,
        *,
        title: str,
        initial_value: str = "",
        placeholder: str,
        save_label: str = r"Save \[Enter/Ctrl+s]",
    ) -> None:
        """Initialize the modal with labels and initial input value."""
        super().__init__()
        self._title = title
        self._initial_value = initial_value
        self._placeholder = placeholder
        self._save_label = save_label

    def compose(self) -> ComposeResult:
        """Compose the name input modal."""
        with Vertical(id="name-input-container"):
            yield Static(self._title, id="form-title")
            yield SelectAllInput(
                value=self._initial_value,
                placeholder=self._placeholder,
                id="name-input",
            )
            with Horizontal(id="name-input-buttons"):
                yield Button(
                    self._save_label,
                    variant="primary",
                    id="save-name-btn",
                )
                yield Button(
                    r"Cancel \[Esc]",
                    variant="default",
                    id="cancel-name-btn",
                )

    def on_mount(self) -> None:
        """Focus the input and place the cursor at the end."""
        name_input = self.query_one("#name-input", Input)
        name_input.focus()
        name_input.cursor_position = len(name_input.value)

    @on(Button.Pressed, "#save-name-btn")
    def _handle_save_button(self) -> None:
        """Save the entered name when the save button is pressed."""
        self.action_save()

    @on(Button.Pressed, "#cancel-name-btn")
    def _handle_cancel_button(self) -> None:
        """Cancel the name input when the cancel button is pressed."""
        self.action_cancel()

    @on(Input.Submitted, "#name-input")
    def _handle_input_submitted(self) -> None:
        """Submit the modal when Enter is pressed in the name input."""
        self.action_save()

    def on_key(self, event: Key) -> None:
        """Handle text-field shortcuts."""
        handle_select_all_key(self, event)

    def action_save(self) -> None:
        """Validate and return the entered name."""
        name = self.query_one("#name-input", Input).value.strip()
        if not name:
            self.notify("Name is required", severity="error")
            self.query_one("#name-input", Input).focus()
            return
        self.dismiss(name)

    def action_cancel(self) -> None:
        """Cancel and dismiss."""
        self.dismiss(None)


class BackendConfigScreen(ModalScreen[BackendConfig | None]):
    """Modal dialog for choosing the active Cogitus backend."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding(
            "ctrl+s",
            "save",
            "Save",
            show=False,
            priority=True,
        ),
    ]

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the backend config modal with existing values."""
        super().__init__()
        self._config = config

    def on_mount(self) -> None:
        """Focus the backend mode select widget."""
        self.query_one("#backend-mode-select", Select).focus()

    def compose(self) -> ComposeResult:
        """Compose the backend settings form."""
        with VerticalScroll(id="backend-config-container"):
            yield Static("Connection Settings", id="form-title")
            yield Label("Backend")
            yield Select[DataBackendMode](
                options=[
                    ("Local SQLite", DataBackendMode.LOCAL),
                    ("Remote API", DataBackendMode.API),
                ],
                value=self._config.mode,
                allow_blank=False,
                id="backend-mode-select",
            )
            yield Label("Remote API URL")
            yield SelectAllInput(
                value=self._config.api_base_url,
                placeholder="http://127.0.0.1:8000",
                id="backend-api-url",
            )
            yield Label("Remote API Username")
            yield SelectAllInput(
                value=self._config.api_username,
                placeholder="api user",
                id="backend-api-username",
            )
            yield Label("Remote API Password")
            yield SelectAllInput(
                value=self._config.api_password,
                placeholder="api password",
                password=True,
                id="backend-api-password",
            )
            with Horizontal(id="name-input-buttons"):
                yield Button(
                    r"Save \[Ctrl+s]",
                    variant="primary",
                    id="save-backend-btn",
                )
                yield Button(
                    r"Cancel \[Esc]",
                    variant="default",
                    id="cancel-backend-btn",
                )

    @on(Button.Pressed, "#save-backend-btn")
    def _handle_save_backend_button(self) -> None:
        """Save backend configuration when the primary button is pressed."""
        self.action_save()

    @on(Button.Pressed, "#cancel-backend-btn")
    def _handle_cancel_backend_button(self) -> None:
        """Cancel backend configuration changes."""
        self.action_cancel()

    def on_key(self, event: Key) -> None:
        """Handle text-field shortcuts."""
        handle_select_all_key(self, event)

    def action_save(self) -> None:
        """Validate and return the selected backend configuration."""
        mode = self.query_one("#backend-mode-select", Select).value
        if not isinstance(mode, DataBackendMode):
            self.notify("Select a backend mode", severity="error")
            return

        api_base_url = self.query_one("#backend-api-url", Input).value
        api_username = self.query_one("#backend-api-username", Input).value
        api_password = self.query_one("#backend-api-password", Input).value

        if mode == DataBackendMode.API and not (
            api_base_url.strip() and api_username.strip() and api_password
        ):
            self.notify(
                "Remote API mode requires URL, username, and password",
                severity="error",
            )
            return

        self.dismiss(
            BackendConfig(
                mode=mode,
                api_base_url=api_base_url.strip(),
                api_username=api_username.strip(),
                api_password=api_password,
            )
        )

    def action_cancel(self) -> None:
        """Cancel and dismiss the backend config modal."""
        self.dismiss(None)


class GroupDeleteReassignScreen(ModalScreen[int | None]):
    """Modal dialog to choose destination group when deleting a group."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+s", "save", "Move+Delete", show=False, priority=True),
    ]

    def __init__(
        self,
        source_group_name: str,
        destination_options: list[tuple[str, int]],
    ) -> None:
        """Initialize with source and destination groups."""
        super().__init__()
        self._source_group_name = source_group_name
        self._destination_options = destination_options

    def compose(self) -> ComposeResult:
        """Compose the reassign modal."""
        with Vertical(id="confirm-container"):
            yield Static(
                f'Delete "{self._source_group_name}" and move ideas to:',
                id="confirm-message",
            )
            yield Select[int](
                options=self._destination_options,
                allow_blank=False,
                id="move-group-select",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button(
                    r"Move + Delete \[Ctrl+s]",
                    variant="error",
                    id="move-delete-btn",
                )
                yield Button(
                    r"Cancel \[Esc]",
                    variant="default",
                    id="cancel-move-btn",
                )

    @on(Button.Pressed, "#move-delete-btn")
    def _handle_save_button(self) -> None:
        """Confirm reassignment when the destructive button is pressed."""
        self.action_save()

    @on(Button.Pressed, "#cancel-move-btn")
    def _handle_cancel_button(self) -> None:
        """Cancel the reassignment dialog when cancel is pressed."""
        self.action_cancel()

    def action_save(self) -> None:
        """Return selected destination group pk."""
        value = self.query_one("#move-group-select", Select).value
        if not isinstance(value, int):
            self.notify("Select a destination group", severity="error")
            return
        self.dismiss(value)

    def action_cancel(self) -> None:
        """Cancel and dismiss."""
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    """Help overlay showing keyboard shortcuts."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding(
            "question_mark",
            "close",
            "Close",
            show=False,
        ),
    ]

    HELP_TEXT = (
        "[bold]Navigation[/bold]\n"
        "  Up/Down or j/k  Navigate ideas\n"
        "  Tab              Switch between panes\n"
        "  Enter            Select idea\n"
        "\n"
        "[bold]Actions[/bold]\n"
        "  n                New idea\n"
        "  e                Edit selected idea\n"
        "  r                Rename selected item\n"
        "  d                Delete selected idea\n"
        "  g                New group\n"
        "  G                Delete selected group\n"
        "  y                Copy idea body\n"
        "  /                Focus search\n"
        "  Escape           Clear search / close\n"
        "\n"
        "[bold]Form[/bold]\n"
        "  F5               Save and keep open\n"
        "  Ctrl+s           Save and close\n"
        "  Ctrl+a           Select all focused form text\n"
        "  Tab/Shift+Tab    Cycle tag suggestions (when open)\n"
        "  Enter            Accept tag suggestion\n"
        "  ,                Accept suggestion and add next tag\n"
        "  y (selection)    Copy selected text\n"
        "  Escape           Cancel (confirm if edit is dirty)\n"
        "\n"
        "[bold]General[/bold]\n"
        "  c                Connection settings\n"
        "  a                About\n"
        "  ?                Toggle this help\n"
        "  q                Quit"
    )

    def compose(self) -> ComposeResult:
        """Compose the help overlay."""
        with Vertical(id="help-container"):
            yield Static("Keyboard Shortcuts", id="help-title")
            with VerticalScroll(id="help-content"):
                yield Static(self.HELP_TEXT, id="help-body", markup=True)

    def action_close(self) -> None:
        """Close the help overlay."""
        self.dismiss(None)


class AboutScreen(ModalScreen[None]):
    """About overlay showing app metadata and support links."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("a", "close", "Close", show=False),
    ]

    def __init__(self, app_metadata: AppMetadata) -> None:
        """Initialize the About modal."""
        super().__init__()
        self._app_metadata = app_metadata

    def _build_about_table(self) -> Table:
        """Build a borderless Rich table for About metadata rows."""
        table = Table.grid(padding=(0, 2), expand=True)
        table.add_column(no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        for label, value in get_about_entries(self._app_metadata):
            table.add_row(
                Text(f"{label}:", style="dim"),
                Text(value),
            )
        return table

    def compose(self) -> ComposeResult:
        """Compose the About overlay."""
        with Vertical(id="about-container"):
            yield Static(f"About {self._app_metadata.title}", id="about-title")
            yield Rule(id="about-separator")
            with VerticalScroll(id="about-content-scroll"):
                if self._app_metadata.summary:
                    yield Static(
                        self._app_metadata.summary,
                        id="about-summary",
                    )
                yield Static(self._build_about_table(), id="about-metadata")

    def action_close(self) -> None:
        """Close the About overlay."""
        self.dismiss(None)
