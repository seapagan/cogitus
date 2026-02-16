"""Tests for Textual screens and app integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from unittest.mock import PropertyMock

import pytest
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Input, OptionList, Select, TextArea, Tree

from cogitus.app import CogitusApp
from cogitus.config import EditBodyCursorMode, NewIdeaGroupMode
from cogitus.ui.screens.idea_form_screen import (
    ConfirmDialog,
    GroupDeleteReassignScreen,
    GroupFormScreen,
    HelpScreen,
    IdeaFormScreen,
)
from cogitus.ui.screens.main_screen import MainScreen
from cogitus.ui.widgets.idea_list import IdeaListPanel
from cogitus.ui.widgets.idea_view import IdeaView
from cogitus.ui.widgets.text_area import CogitusTextArea

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture
    from sqliter import SqliterDB
    from textual.screen import Screen

    from cogitus.services.idea_service import IdeaService


class _SingleScreenApp(App[None]):
    """Host app that mounts a screen on start."""

    def __init__(self, screen: Screen[Any]) -> None:
        super().__init__()
        self._screen = screen

    def compose(self) -> ComposeResult:
        """Compose root (no widgets required)."""
        if False:
            yield

    def on_mount(self) -> None:
        """Push the test screen."""
        self.push_screen(self._screen)


class _FakeSettings:
    """Minimal settings double for CogitusApp tests."""

    def __init__(
        self,
        last_viewed_idea_pk: int = 0,
        edit_body_cursor_mode: str = "remember",
        new_idea_group_mode: str = "contextual",
        default_group_name: str = "default",
    ) -> None:
        self.last_viewed_idea_pk = last_viewed_idea_pk
        self.edit_body_cursor_mode = edit_body_cursor_mode
        self.new_idea_group_mode = new_idea_group_mode
        self.default_group_name = default_group_name
        self.saved = False

    def save(self) -> None:
        """Record save invocation."""
        self.saved = True


@pytest.mark.asyncio
async def test_idea_form_screen_create_and_validation(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Form should validate title and create ideas."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        assert screen._get_existing_tags() == ""
        assert screen.query_one("#idea-form-scroll") is not None
        assert screen.query_one("#form-buttons") is not None
        tags_group_row = screen.query_one("#tags-group-row", Container)
        assert tags_group_row.query_one("#tags-input", Input) is not None
        assert tags_group_row.query_one("#group-select", Select) is not None

        dismiss = mocker.patch.object(screen, "dismiss")
        notify = mocker.patch.object(screen, "notify")

        screen.query_one("#title-input", Input).value = "  "
        screen.action_save()
        notify.assert_called_once()
        dismiss.assert_not_called()

        screen.query_one("#title-input", Input).value = "My Idea"
        screen.query_one("#body-input", TextArea).text = "Body"
        screen.query_one("#tags-input", Input).value = "python, testing"
        screen.action_save()

        dismiss.assert_called_once()
        pk = dismiss.call_args.args[0]
        created = service.get_idea(pk)
        assert created is not None
        assert created.title == "My Idea"
        assert {tag.name for tag in created.tags.fetch_all()} == {
            "python",
            "testing",
        }
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_screen_edit_and_buttons(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Form should support editing and button dispatch."""
    idea = service.create_idea("Original", body="old", tags=["one", "two"])
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        assert "one, two" in screen._get_existing_tags()

        dismiss = mocker.patch.object(screen, "dismiss")
        screen.query_one("#title-input", Input).value = "Updated"
        screen.query_one("#body-input", TextArea).text = "new"
        screen.query_one("#tags-input", Input).value = "three"
        screen.action_save()
        dismiss.assert_called_once()

        updated = service.get_idea(idea.pk)
        assert updated is not None
        assert updated.title == "Updated"

        save_action = mocker.patch.object(screen, "action_save")
        cancel_action = mocker.patch.object(screen, "action_cancel")
        await pilot.click("#save-btn")
        save_action.assert_called_once()
        await pilot.click("#cancel-btn")
        cancel_action.assert_called_once()

        dismiss.reset_mock()
        IdeaFormScreen.action_cancel(screen)
        dismiss.assert_called_once_with(None)
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_screen_invalid_group_selection(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Invalid group selection should block save."""
    idea = service.create_idea("Original", body="old")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        dismiss = mocker.patch.object(screen, "dismiss")
        screen.query_one("#title-input", Input).value = "Updated"
        group_select = screen.query_one("#group-select", Select)
        mocker.patch.object(
            type(group_select),
            "value",
            new_callable=PropertyMock,
            return_value=Select.BLANK,
        )

        screen.action_save()

        notify.assert_called_once_with(
            "Invalid group selection",
            severity="error",
        )
        dismiss.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_tags_group_row_responsive_layout(
    service: IdeaService,
) -> None:
    """Tags/group row should stack only on narrow widths."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        row = screen.query_one("#tags-group-row", Container)
        screen._update_tags_group_row_layout(
            screen.INLINE_TAGS_GROUP_MIN_WIDTH - 1
        )
        assert row.has_class("narrow")

        screen._update_tags_group_row_layout(
            screen.INLINE_TAGS_GROUP_MIN_WIDTH + 1
        )
        assert not row.has_class("narrow")

        # Exact threshold should remain inline.
        screen._update_tags_group_row_layout(screen.INLINE_TAGS_GROUP_MIN_WIDTH)
        assert not row.has_class("narrow")
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_initial_focus_new_mode(
    service: IdeaService,
) -> None:
    """New idea mode should focus title input on mount."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        title = screen.query_one("#title-input", Input)
        assert app.focused is title
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_initial_focus_edit_mode(
    service: IdeaService,
) -> None:
    """Edit mode should focus body editor on mount."""
    idea = service.create_idea("Original", body="old")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        assert app.focused is body
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_tags_autocomplete_keys_and_accept(
    service: IdeaService,
) -> None:
    """Tags input should support ranked autocomplete and keyboard acceptance."""
    service.create_idea("A", tags=["alpha", "api", "python"])
    service.create_idea("B", tags=["alpha", "beta"])
    stale = service.create_idea("C", tags=["aold"])
    service.update_idea(stale.pk, "C", "", tags=[])

    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        tags_input = screen.query_one("#tags-input", Input)
        autocomplete = screen.query_one("#tags-autocomplete", OptionList)
        tags_input.focus()
        await pilot.pause()

        await pilot.press("a")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")
        options = [str(option.prompt) for option in autocomplete.options]
        assert options[:3] == ["alpha", "api", "aold"]

        await pilot.press("tab")
        await pilot.pause()
        assert autocomplete.highlighted == 1
        assert app.focused is tags_input

        await pilot.press("shift+tab")
        await pilot.pause()
        assert autocomplete.highlighted == 0

        await pilot.press("down")
        await pilot.pause()
        assert autocomplete.highlighted == 1

        await pilot.press("up")
        await pilot.pause()
        assert autocomplete.highlighted == 0

        await pilot.press("enter")
        await pilot.pause()
        assert tags_input.value == "alpha"
        assert autocomplete.has_class("-hidden")

        tags_input.value = ""
        tags_input.cursor_position = 0
        await pilot.pause()

        await pilot.press("p")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")
        prompts = (str(option.prompt) for option in autocomplete.options)
        assert next(prompts) == "python"

        await pilot.press(",")
        await pilot.pause()
        assert tags_input.value == "python, "
        assert autocomplete.has_class("-hidden")

        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not tags_input


@pytest.mark.asyncio
async def test_idea_form_tags_autocomplete_defensive_branches(
    service: IdeaService,
) -> None:
    """Defensive autocomplete paths should return without side effects."""
    service.create_idea("A", tags=["alpha"])
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        tags_input = screen.query_one("#tags-input", Input)
        title_input = screen.query_one("#title-input", Input)
        autocomplete = screen.query_one("#tags-autocomplete", OptionList)

        # on_key early return when tags input is not focused.
        title_input.focus()
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        assert app.focused is title_input

        # _accept_tag_suggestion... false when not focused/visible.
        assert screen._accept_tag_suggestion_and_next_from_input() is False

        # _accept_tag_suggestion... false when apply fails.
        tags_input.focus()
        await pilot.pause()
        screen._tag_autocomplete_state = None
        autocomplete.set_options(["alpha"])
        autocomplete.highlighted = 0
        autocomplete.remove_class("-hidden")
        assert screen._accept_tag_suggestion_and_next_from_input() is False

        # _cycle_tag_autocomplete: count == 0 branch.
        autocomplete.set_options([])
        screen._cycle_tag_autocomplete(1)

        # _cycle_tag_autocomplete: highlighted is None branch.
        autocomplete.set_options(["alpha"])
        autocomplete.highlighted = None
        screen._cycle_tag_autocomplete(1)
        assert autocomplete.highlighted == 0

        # _apply_highlighted_tag_autocomplete: state is None branch.
        screen._tag_autocomplete_state = None
        assert screen._apply_highlighted_tag_autocomplete() is False

        # _apply_highlighted_tag_autocomplete: highlighted is None branch.
        screen._tag_autocomplete_state = screen._resolve_tag_autocomplete_state(
            "a",
            cursor_position=1,
        )
        autocomplete.highlighted = None
        assert screen._apply_highlighted_tag_autocomplete() is False

        # _resolve_tag_autocomplete_state: no candidate branch.
        assert (
            screen._resolve_tag_autocomplete_state("zzz", cursor_position=3)
            is None
        )

        # _tag_token_bounds should consume token until comma.
        assert screen._tag_token_bounds("alpha,beta", 6) == (6, 10)


@pytest.mark.asyncio
async def test_idea_form_escape_closes_tags_autocomplete_before_cancel(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Esc should close tags autocomplete before dismissing the form."""
    service.create_idea("A", tags=["alpha"])
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        tags_input = screen.query_one("#tags-input", Input)
        autocomplete = screen.query_one("#tags-autocomplete", OptionList)

        tags_input.focus()
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        await pilot.press("escape")
        await pilot.pause()
        assert autocomplete.has_class("-hidden")
        dismiss.assert_not_called()

        await pilot.press("escape")
        await pilot.pause()
        dismiss.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_idea_form_blur_defers_for_tag_option_selection(
    service: IdeaService,
) -> None:
    """Blur should defer dismissal long enough for option selection."""
    service.create_idea("A", tags=["alpha", "api"])
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        tags_input = screen.query_one("#tags-input", Input)
        autocomplete = screen.query_one("#tags-autocomplete", OptionList)

        tags_input.focus()
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        autocomplete.focus()
        await pilot.pause()

        screen.on_input_blurred(Input.Blurred(tags_input, tags_input.value))
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        tags_input.value = ""
        tags_input.cursor_position = 0
        tags_input.focus()
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        screen.on_option_list_option_selected(
            OptionList.OptionSelected(
                autocomplete,
                autocomplete.options[0],
                0,
            ),
        )
        await pilot.pause()

        assert tags_input.value == "alpha"
        assert autocomplete.has_class("-hidden")
        assert app.focused is tags_input


@pytest.mark.asyncio
async def test_main_screen_toggle_focus_noop_when_search_focused(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Toggle focus should no-op while the search input is focused."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        view = screen.query_one("#content-panel", IdeaView)
        tree = panel.query_one("#idea-list", Tree)

        screen.action_focus_search()
        await pilot.pause()
        assert app.focused is search

        content_focus = mocker.patch.object(view, "focus")
        tree_focus = mocker.patch.object(tree, "focus")
        screen.action_toggle_focus()

        content_focus.assert_not_called()
        tree_focus.assert_not_called()
        assert app.focused is search


@pytest.mark.asyncio
async def test_idea_form_edit_cursor_mode_start(
    service: IdeaService,
) -> None:
    """Start mode should place edit body cursor at index zero."""
    idea = service.create_idea("Original", body="abcdef")
    screen = IdeaFormScreen(
        service,
        idea=idea,
        edit_body_cursor_mode=EditBodyCursorMode.START,
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        assert (
            screen._cursor_index_from_location(body.text, body.cursor_location)
            == 0
        )
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_edit_cursor_mode_end(
    service: IdeaService,
) -> None:
    """End mode should place edit body cursor at end of text."""
    idea = service.create_idea("Original", body="abcdef")
    screen = IdeaFormScreen(
        service,
        idea=idea,
        edit_body_cursor_mode=EditBodyCursorMode.END,
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        assert screen._cursor_index_from_location(
            body.text,
            body.cursor_location,
        ) == len(body.text)
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_edit_cursor_mode_remember(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Remember mode should use saved cursor position when available."""
    idea = service.create_idea("Original", body="abcdef")
    get_cursor = mocker.patch.object(
        service,
        "get_idea_cursor_position",
        return_value=4,
    )
    screen = IdeaFormScreen(
        service,
        idea=idea,
        edit_body_cursor_mode=EditBodyCursorMode.REMEMBER,
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        assert (
            screen._cursor_index_from_location(body.text, body.cursor_location)
            == 4
        )
        get_cursor.assert_called_once_with(idea.pk)
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_edit_cursor_mode_remember_clamps_out_of_range(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Remember mode should clamp stored cursor positions to text bounds."""
    idea = service.create_idea("Original", body="abc")
    mocker.patch.object(
        service,
        "get_idea_cursor_position",
        return_value=999,
    )
    screen = IdeaFormScreen(
        service,
        idea=idea,
        edit_body_cursor_mode=EditBodyCursorMode.REMEMBER,
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        assert screen._cursor_index_from_location(
            body.text,
            body.cursor_location,
        ) == len(body.text)
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_persists_cursor_position_on_edit_save(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Edit save should persist current body cursor position."""
    idea = service.create_idea("Original", body="abcdef")
    set_cursor = mocker.patch.object(service, "set_idea_cursor_position")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        body.cursor_location = screen._cursor_location_from_index(body.text, 2)
        screen.query_one("#title-input", Input).value = "Updated"

        screen.action_save()

        set_cursor.assert_called_with(idea.pk, 2)
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_persists_cursor_position_on_edit_cancel(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Edit cancel should persist current body cursor position."""
    idea = service.create_idea("Original", body="abcdef")
    set_cursor = mocker.patch.object(service, "set_idea_cursor_position")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        body.cursor_location = screen._cursor_location_from_index(body.text, 5)

        screen.action_cancel()

        set_cursor.assert_called_with(idea.pk, 5)
        await pilot.pause()


def test_idea_form_default_group_fallback(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Fallback should return first group when default name is missing."""
    screen = IdeaFormScreen(service)
    fake_group = mocker.Mock()
    fake_group.name = "not-default"
    fake_group.pk = 99
    mocker.patch.object(service, "list_groups", return_value=[fake_group])

    assert screen._get_default_group_pk() == 99


def test_idea_form_create_mode_uses_initial_group_pk(
    service: IdeaService,
) -> None:
    """Create mode should use initial group pk when it exists."""
    backend = service.create_group("backend")
    screen = IdeaFormScreen(service, initial_group_pk=backend.pk)

    assert screen._get_existing_group_pk() == backend.pk


def test_idea_form_create_mode_invalid_initial_group_falls_back_default(
    service: IdeaService,
) -> None:
    """Invalid initial group pk should fallback to default group logic."""
    screen = IdeaFormScreen(service, initial_group_pk=999_999)

    assert screen._get_existing_group_pk() == screen._get_default_group_pk()


def test_idea_form_initial_edit_cursor_index_for_new_mode(
    service: IdeaService,
) -> None:
    """New mode should return cursor index zero for edit helper."""
    screen = IdeaFormScreen(service)
    body = CogitusTextArea("abc")
    assert screen._initial_edit_body_cursor_index(body) == 0


def test_idea_form_persist_cursor_noop_for_new_mode(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Persist helper should no-op when no existing idea is being edited."""
    screen = IdeaFormScreen(service)
    set_cursor = mocker.patch.object(service, "set_idea_cursor_position")
    screen._persist_edit_cursor_position()
    set_cursor.assert_not_called()


def test_idea_form_cursor_location_from_index_handles_newlines(
    service: IdeaService,
) -> None:
    """Index-to-location conversion should step lines on newline chars."""
    screen = IdeaFormScreen(service)
    assert screen._cursor_location_from_index("ab\ncd", 3) == (1, 0)


def test_idea_form_default_group_created_when_missing(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Should create default group when no groups are available."""
    screen = IdeaFormScreen(service)
    created = mocker.Mock()
    created.pk = 123
    create_group = mocker.patch.object(
        service,
        "create_group",
        return_value=created,
    )
    mocker.patch.object(service, "list_groups", return_value=[])

    assert screen._get_default_group_pk() == 123
    create_group.assert_called_once_with(service.default_group_name)


@pytest.mark.asyncio
async def test_confirm_dialog_actions(mocker: MockerFixture) -> None:
    """Confirmation dialog actions should dismiss correctly."""
    confirm = ConfirmDialog("Are you sure?")
    app = _SingleScreenApp(confirm)
    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(confirm, "dismiss")
        await pilot.click("#confirm-yes-btn")
        dismiss.assert_called_once_with(True)

        dismiss.reset_mock()
        await pilot.click("#confirm-no-btn")
        dismiss.assert_called_once_with(False)
        await pilot.pause()


@pytest.mark.asyncio
async def test_group_form_and_reassign_cancel_actions(
    mocker: MockerFixture,
) -> None:
    """Group-related modal cancel actions should dismiss correctly."""
    group_form = GroupFormScreen(service=mocker.Mock())
    app_group = _SingleScreenApp(group_form)
    async with app_group.run_test() as pilot:
        dismiss = mocker.patch.object(group_form, "dismiss")
        group_form.action_cancel()
        dismiss.assert_called_once_with(None)
        await pilot.pause()

    reassign = GroupDeleteReassignScreen(
        "source",
        [("default", 1), ("target", 2)],
    )
    app_reassign = _SingleScreenApp(reassign)
    async with app_reassign.run_test() as pilot:
        dismiss = mocker.patch.object(reassign, "dismiss")
        reassign.action_cancel()
        dismiss.assert_called_once_with(None)
        await pilot.pause()


@pytest.mark.asyncio
async def test_help_screen_close_action(mocker: MockerFixture) -> None:
    """Help modal close action should dismiss correctly."""
    help_screen = HelpScreen()
    app2 = _SingleScreenApp(help_screen)
    async with app2.run_test() as pilot:
        dismiss = mocker.patch.object(help_screen, "dismiss")
        help_screen.action_close()
        dismiss.assert_called_once_with(None)
        await pilot.pause()


@pytest.mark.asyncio
async def test_group_form_and_reassign_validation_branches(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Group form and reassign screen should validate and route buttons."""
    group_form = GroupFormScreen(service=service)
    app_group = _SingleScreenApp(group_form)
    async with app_group.run_test() as pilot:
        notify = mocker.patch.object(group_form, "notify")
        dismiss = mocker.patch.object(group_form, "dismiss")

        # Empty name
        group_form.query_one("#group-name-input", Input).value = "   "
        group_form.action_save()
        notify.assert_called_once()
        dismiss.assert_not_called()

        # Duplicate name
        service.create_group("backend")
        notify.reset_mock()
        group_form.query_one("#group-name-input", Input).value = "backend"
        group_form.action_save()
        notify.assert_called_once()
        dismiss.assert_not_called()

        # Success
        notify.reset_mock()
        group_form.query_one("#group-name-input", Input).value = "frontend"
        group_form.action_save()
        dismiss.assert_called_once()

        # on_button_pressed routes both paths
        save_action = mocker.patch.object(group_form, "action_save")
        cancel_action = mocker.patch.object(group_form, "action_cancel")
        group_form.on_button_pressed(
            Button.Pressed(group_form.query_one("#save-group-btn", Button))
        )
        group_form.on_button_pressed(
            Button.Pressed(group_form.query_one("#cancel-group-btn", Button))
        )
        save_action.assert_called_once()
        cancel_action.assert_called_once()
        await pilot.pause()

    reassign = GroupDeleteReassignScreen(
        "source",
        cast("list[tuple[str, int]]", [("bad", "x")]),
    )
    app_reassign = _SingleScreenApp(reassign)
    async with app_reassign.run_test() as pilot:
        notify = mocker.patch.object(reassign, "notify")
        dismiss = mocker.patch.object(reassign, "dismiss")

        # Invalid selection branch (selected value is non-int).
        select = reassign.query_one("#move-group-select", Select)
        reassign.action_save()
        notify.assert_called_once()
        dismiss.assert_not_called()

        # Valid save
        notify.reset_mock()
        select.set_options([("default", 1), ("x", 2)])
        select.value = 1
        reassign.action_save()
        dismiss.assert_called_once_with(1)

        # on_button_pressed routes save/cancel
        save_action = mocker.patch.object(reassign, "action_save")
        cancel_action = mocker.patch.object(reassign, "action_cancel")
        reassign.on_button_pressed(
            Button.Pressed(reassign.query_one("#move-delete-btn", Button))
        )
        reassign.on_button_pressed(
            Button.Pressed(reassign.query_one("#cancel-move-btn", Button))
        )
        save_action.assert_called_once()
        cancel_action.assert_called_once()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_selection_and_search(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Main screen should handle selection and search refresh paths."""
    first = service.create_idea("First")
    second = service.create_idea("Second")
    selected: list[int | None] = []
    screen = MainScreen(
        service,
        initial_select_pk=second.pk,
        on_selected_idea_changed=selected.append,
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        assert app.focused is panel.query_one("#idea-list")
        assert panel.get_selected_idea() is not None

        screen.on_idea_list_panel_idea_selected(
            IdeaListPanel.IdeaSelected(first)
        )
        get_idea = mocker.patch.object(
            screen._service, "get_idea", return_value=None
        )
        screen.on_idea_list_panel_idea_selected(
            IdeaListPanel.IdeaSelected(first)
        )
        get_idea.assert_called()

        search = mocker.patch.object(
            screen._service,
            "list_ideas_grouped",
            return_value=[(first.group, [first])],
        )
        selected_view = mocker.patch.object(
            screen.query_one("#content-panel", IdeaView),
            "show_idea",
        )
        mocker.patch.object(panel, "get_selected_idea", return_value=first)
        screen.on_idea_list_panel_search_changed(
            IdeaListPanel.SearchChanged("fir")
        )
        search.assert_called_once_with("fir")
        selected_view.assert_called_once_with(first)

        search.reset_mock()
        screen.on_idea_list_panel_search_changed(
            IdeaListPanel.SearchChanged("tag:python and group:backend")
        )
        search.assert_called_once_with("tag:python and group:backend")

        list_all = mocker.patch.object(
            screen._service,
            "list_ideas_grouped",
            return_value=[(first.group, [first])],
        )
        empty_view = mocker.patch.object(
            screen.query_one("#content-panel", IdeaView),
            "show_empty",
        )
        mocker.patch.object(panel, "get_selected_idea", return_value=None)
        screen.on_idea_list_panel_search_changed(
            IdeaListPanel.SearchChanged(" ")
        )
        list_all.assert_called()
        empty_view.assert_called_once()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_create_edit_delete_and_form_result(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Main screen should cover create/edit/delete branches."""
    first = service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        push = mocker.patch.object(app, "push_screen")
        screen.action_new_idea()
        push.assert_called()

        screen.refresh_ideas(select_pk=first.pk)
        panel.select_idea(first.pk)
        await pilot.pause()

        push.reset_mock()
        screen.action_edit_idea()
        push.assert_called()

        mocker.patch.object(panel, "get_selected_idea", return_value=None)
        notify = mocker.patch.object(screen, "notify")
        screen.action_edit_idea()
        notify.assert_called_with("No idea selected", severity="warning")

        mocker.patch.object(panel, "get_selected_idea", return_value=first)
        notify.reset_mock()
        mocker.patch.object(screen._service, "get_idea", return_value=None)
        screen.action_edit_idea()
        notify.assert_called_with("Idea not found", severity="error")

        mocker.patch.object(panel, "get_selected_idea", return_value=None)
        notify.reset_mock()
        screen.action_delete_idea()
        notify.assert_called_with("No idea selected", severity="warning")

        mocker.patch.object(panel, "get_selected_idea", return_value=first)
        push.reset_mock()
        screen.action_delete_idea()
        callback = push.call_args.kwargs["callback"]

        delete = mocker.patch.object(screen._service, "delete_idea")
        refresh = mocker.patch.object(screen, "refresh_ideas")
        callback(False)
        delete.assert_not_called()
        callback(True)
        delete.assert_called_once_with(first.pk)
        refresh.assert_called()

        refresh.reset_mock()
        screen._on_form_dismiss(None)
        refresh.assert_not_called()
        screen._on_form_dismiss(first.pk)
        refresh.assert_called_once_with(select_pk=first.pk)


@pytest.mark.asyncio
async def test_main_screen_new_idea_uses_contextual_group_selection(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """New idea should seed group from selected group or selected idea."""
    backend = service.create_group("backend")
    idea = service.create_idea("Grouped", group_pk=backend.pk)
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        push = mocker.patch.object(app, "push_screen")
        selected_group = mocker.patch.object(panel, "get_selected_group_pk")
        selected_idea = mocker.patch.object(panel, "get_selected_idea")

        selected_group.return_value = backend.pk
        selected_idea.return_value = None
        screen.action_new_idea()
        form = push.call_args.args[0]
        assert isinstance(form, IdeaFormScreen)
        assert form._initial_group_pk == backend.pk

        push.reset_mock()
        selected_group.return_value = None
        selected_idea.return_value = idea
        screen.action_new_idea()
        form = push.call_args.args[0]
        assert isinstance(form, IdeaFormScreen)
        assert form._initial_group_pk == backend.pk

        push.reset_mock()
        selected_group.return_value = None
        selected_idea.return_value = None
        screen.action_new_idea()
        form = push.call_args.args[0]
        assert isinstance(form, IdeaFormScreen)
        assert form._initial_group_pk is None
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_new_idea_default_group_mode_ignores_context(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Default-group mode should ignore contextual selection."""
    backend = service.create_group("backend")
    idea = service.create_idea("Grouped", group_pk=backend.pk)
    screen = MainScreen(
        service,
        new_idea_group_mode=(NewIdeaGroupMode.DEFAULT_GROUP),
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        push = mocker.patch.object(app, "push_screen")
        mocker.patch.object(panel, "get_selected_group_pk", return_value=1)
        mocker.patch.object(panel, "get_selected_idea", return_value=idea)

        screen.action_new_idea()

        form = push.call_args.args[0]
        assert isinstance(form, IdeaFormScreen)
        assert form._initial_group_pk is None
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_group_actions(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Main screen should open create/delete group flows."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        push = mocker.patch.object(app, "push_screen")
        notify = mocker.patch.object(screen, "notify")

        screen.action_new_group()
        push.assert_called()

        notify.reset_mock()
        mocker.patch.object(panel, "get_selected_group_pk", return_value=None)
        screen.action_delete_group()
        notify.assert_called_with("No group selected", severity="warning")

        notify.reset_mock()
        mocker.patch.object(panel, "get_selected_group_pk", return_value=12345)
        screen.action_delete_group()
        notify.assert_called_with("Group not found", severity="error")

        backend = service.create_group("backend")
        service.create_idea("Grouped", group_pk=backend.pk)
        mocker.patch.object(
            panel,
            "get_selected_group_pk",
            return_value=backend.pk,
        )
        push.reset_mock()
        screen.action_delete_group()
        assert push.call_args.args
        assert isinstance(
            push.call_args.args[0],
            ConfirmDialog | GroupDeleteReassignScreen,
        )

        # Empty group takes confirm-delete branch.
        empty_group = service.create_group("empty")
        mocker.patch.object(
            panel,
            "get_selected_group_pk",
            return_value=empty_group.pk,
        )
        push.reset_mock()
        screen.action_delete_group()
        assert push.call_args.args
        assert isinstance(push.call_args.args[0], ConfirmDialog)

        # Default group delete guard
        default = next(
            group
            for group in service.list_groups()
            if group.name == service.default_group_name
        )
        notify.reset_mock()
        mocker.patch.object(
            panel,
            "get_selected_group_pk",
            return_value=default.pk,
        )
        screen.action_delete_group()
        notify.assert_called_with(
            "Default group cannot be deleted",
            severity="warning",
        )
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_refresh_empty_selection_branch(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """refresh_ideas should clear selection when no idea is selected."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        view = screen.query_one("#content-panel", IdeaView)
        search = panel.query_one("#search-input", Input)
        mocker.patch.object(panel, "get_selected_idea", return_value=None)
        set_selected = mocker.patch.object(screen, "_set_selected_idea")
        show_empty = mocker.patch.object(view, "show_empty")
        list_grouped = mocker.patch.object(
            screen._service,
            "list_ideas_grouped",
            wraps=screen._service.list_ideas_grouped,
        )

        search.value = "First"
        list_grouped.reset_mock()
        screen.refresh_ideas()

        list_grouped.assert_called_once_with("First")
        set_selected.assert_called_with(None)
        show_empty.assert_called()
        await pilot.pause()


def test_main_screen_group_helper_branches(mocker: MockerFixture) -> None:
    """Internal group callbacks should cover all branch paths."""
    # These callbacks are intentionally exercised without mounting the screen.
    # If callbacks start querying widgets, this test should be converted to
    # a mounted async screen test.
    service = mocker.Mock()
    screen = MainScreen(service)
    service_mock = mocker.Mock()
    screen._service = service_mock
    notify = mocker.patch.object(screen, "notify")
    refresh = mocker.patch.object(screen, "refresh_ideas")

    screen._on_group_form_dismiss(None)
    notify.assert_not_called()
    refresh.assert_not_called()

    screen._on_group_form_dismiss(1)
    notify.assert_called_with("Group created")
    refresh.assert_called_once()

    # delete confirm: cancelled
    notify.reset_mock()
    refresh.reset_mock()
    service_mock.delete_group.reset_mock()
    screen._on_delete_group_confirm(1, confirmed=False)
    service_mock.delete_group.assert_not_called()
    notify.assert_not_called()
    refresh.assert_not_called()

    # delete confirm: success
    notify.reset_mock()
    refresh.reset_mock()
    screen._on_delete_group_confirm(1, confirmed=True)
    service_mock.delete_group.assert_called_once_with(1)
    notify.assert_called_with("Group deleted")
    refresh.assert_called_once()

    # delete confirm: error
    notify.reset_mock()
    refresh.reset_mock()
    service_mock.delete_group.side_effect = ValueError("boom")
    screen._on_delete_group_confirm(1, confirmed=True)
    notify.assert_called_with("boom", severity="error")
    refresh.assert_not_called()

    # reassign: target None
    notify.reset_mock()
    refresh.reset_mock()
    screen._on_delete_group_reassign(1, None)
    notify.assert_not_called()
    refresh.assert_not_called()

    service_mock.delete_group.side_effect = ValueError("bad move")
    screen._on_delete_group_reassign(1, 2)
    notify.assert_called_with("bad move", severity="error")

    notify.reset_mock()
    refresh.reset_mock()
    service_mock.delete_group.side_effect = None
    screen._on_delete_group_reassign(1, 2)
    notify.assert_called_with("Group deleted and ideas moved")
    refresh.assert_called_once()


@pytest.mark.asyncio
async def test_main_screen_focus_toggle_help_quit_and_callback(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Main screen should handle focus, help, quit, and callback updates."""
    first = service.create_idea("First")
    selected: list[int | None] = []
    screen = MainScreen(service, on_selected_idea_changed=selected.append)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        view = screen.query_one("#content-panel", IdeaView)

        screen.action_focus_search()
        await pilot.pause()
        assert app.focused is panel.query_one("#search-input")

        push = mocker.patch.object(app, "push_screen")
        screen.action_show_help()
        push.assert_called()

        panel.query_one("#idea-list", Tree).focus()
        await pilot.pause()

        content_focus = mocker.patch.object(view, "focus")
        list_focus = mocker.patch.object(
            panel.query_one("#idea-list"),
            "focus",
        )
        mocker.patch.object(
            type(panel),
            "has_focus_within",
            new_callable=PropertyMock,
            return_value=True,
        )
        screen.action_toggle_focus()
        content_focus.assert_called_once_with()

        content_focus.reset_mock()
        mocker.patch.object(
            type(panel),
            "has_focus_within",
            new_callable=PropertyMock,
            return_value=False,
        )
        screen.action_toggle_focus()
        list_focus.assert_called_once_with()

        exit_mock = mocker.patch.object(app, "exit")
        screen.action_quit_app()
        exit_mock.assert_called_once()

        screen._set_selected_idea(first.pk)
        assert selected[-1] == first.pk


@pytest.mark.asyncio
async def test_main_screen_cancel_search_closes_autocomplete_first(
    service: IdeaService,
) -> None:
    """First Esc should close autocomplete before clearing search."""
    service.create_idea("First", tags=["python"])
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        tree = panel.query_one("#idea-list", Tree)
        autocomplete = panel.query_one("#search-autocomplete", OptionList)

        screen.action_focus_search()
        await pilot.pause()
        assert app.focused is search

        search.value = "t"
        search.cursor_position = len(search.value)
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        screen.action_cancel_search()
        await pilot.pause()
        assert autocomplete.has_class("-hidden")
        assert search.value == "t"
        assert app.focused is search

        screen.action_cancel_search()
        await pilot.pause()
        assert search.value == ""
        assert app.focused is tree


@pytest.mark.asyncio
async def test_main_screen_search_cancel_restores_previous_focus(
    service: IdeaService,
) -> None:
    """Esc clears search and restores panel active before slash."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        content = screen.query_one("#content-panel", IdeaView)
        search = panel.query_one("#search-input", Input)
        tree = panel.query_one("#idea-list", Tree)

        screen._active_pane = "content"
        screen.action_focus_search()
        await pilot.pause()
        assert app.focused is search
        search.value = "abc"
        screen.action_cancel_search()
        await pilot.pause()
        assert search.value == ""
        assert app.focused is content

        screen._active_pane = "list"
        screen.action_focus_search()
        await pilot.pause()
        assert app.focused is search
        search.value = "xyz"
        screen.action_cancel_search()
        await pilot.pause()
        assert search.value == ""
        assert app.focused is tree


@pytest.mark.asyncio
async def test_main_screen_cancel_search_noop_when_search_not_focused(
    service: IdeaService,
) -> None:
    """Cancel search should no-op when focus is not on search input."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        tree = panel.query_one("#idea-list", Tree)

        tree.focus()
        await pilot.pause()
        search.value = "keep"
        screen.action_cancel_search()
        await pilot.pause()

        assert search.value == "keep"
        assert app.focused is tree


@pytest.mark.asyncio
async def test_main_screen_toggle_list_panel(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """List panel should collapse and expand via action."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        content = screen.query_one("#content-panel", IdeaView)
        tree = panel.query_one("#idea-list", Tree)

        content_focus = mocker.patch.object(content, "focus")
        list_focus = mocker.patch.object(tree, "focus")

        assert not panel.has_class("collapsed")
        screen.action_toggle_list_panel()
        assert panel.has_class("collapsed")
        content_focus.assert_called_once_with()

        screen.action_toggle_list_panel()
        assert not panel.has_class("collapsed")
        list_focus.assert_called_once_with()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_mount_and_exit(db: SqliterDB) -> None:
    """Cogitus app should restore and persist last viewed idea."""
    settings = _FakeSettings(last_viewed_idea_pk=0)
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        assert isinstance(app.screen, MainScreen)
        assert app.screen._new_idea_group_mode == (NewIdeaGroupMode.CONTEXTUAL)
        app._on_selected_idea_changed(7)
        app.exit()
        await pilot.pause()

    assert settings.last_viewed_idea_pk == 7
    assert settings.saved is True


@pytest.mark.asyncio
async def test_cogitus_app_mount_uses_configured_new_idea_group_mode(
    db: SqliterDB,
) -> None:
    """Cogitus app should pass configured new-idea group mode to screen."""
    settings = _FakeSettings(
        new_idea_group_mode=(NewIdeaGroupMode.DEFAULT_GROUP.value)
    )
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        assert isinstance(app.screen, MainScreen)
        assert app.screen._new_idea_group_mode == (
            NewIdeaGroupMode.DEFAULT_GROUP
        )
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_mount_uses_configured_default_group_name(
    db: SqliterDB,
) -> None:
    """Cogitus app should reconcile injected DB with configured default."""
    settings = _FakeSettings(default_group_name="Inbox")
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        assert app._service.default_group_name == "inbox"
        group_names = {group.name for group in app._service.list_groups()}
        assert "inbox" in group_names
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_mount_warns_on_invalid_new_idea_group_mode(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Invalid new-idea mode should notify and fallback to contextual."""
    settings = _FakeSettings(new_idea_group_mode="broken-mode")
    app = CogitusApp(db=db, settings=settings)
    notify = mocker.patch.object(app, "notify")

    async with app.run_test() as pilot:
        assert isinstance(app.screen, MainScreen)
        assert app.screen._new_idea_group_mode == (NewIdeaGroupMode.CONTEXTUAL)
        valid_values = ", ".join(f"'{mode.value}'" for mode in NewIdeaGroupMode)
        notify.assert_called_once_with(
            "Invalid config "
            "'new_idea_group_mode=broken-mode'; "
            "using 'contextual'. "
            f"Valid values: {valid_values}.",
            severity="warning",
        )
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_mount_warns_on_invalid_default_group_name(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Invalid default group name should notify and fallback to default."""
    settings = _FakeSettings(default_group_name="   ")
    app = CogitusApp(db=db, settings=settings)
    notify = mocker.patch.object(app, "notify")

    async with app.run_test() as pilot:
        assert app._service.default_group_name == "default"
        notify.assert_called_once_with(
            "Invalid config 'default_group_name=   '; using 'default'.",
            severity="warning",
        )
        app.exit()
        await pilot.pause()


def test_cogitus_app_init_uses_db_path(
    mocker: MockerFixture,
    db: SqliterDB,
    tmp_path: Path,
) -> None:
    """App should call get_db with db_path when provided."""
    get_db = mocker.patch("cogitus.app.get_db", return_value=db)
    settings = _FakeSettings()
    db_path = str(tmp_path / "cogitus.db")

    CogitusApp(db_path=db_path, settings=settings)

    get_db.assert_called_once_with(
        db_path,
        default_group_name="default",
    )


def test_cogitus_app_init_uses_default_db(
    mocker: MockerFixture,
    db: SqliterDB,
) -> None:
    """App should call get_db with default args when db_path is missing."""
    get_db = mocker.patch("cogitus.app.get_db", return_value=db)
    settings = _FakeSettings()

    CogitusApp(settings=settings)

    get_db.assert_called_once_with(default_group_name="default")


def test_cogitus_app_init_normalizes_configured_default_group_name(
    mocker: MockerFixture,
    db: SqliterDB,
) -> None:
    """App should pass normalized configured default group name to DB."""
    get_db = mocker.patch("cogitus.app.get_db", return_value=db)
    settings = _FakeSettings(default_group_name="  Inbox  ")

    CogitusApp(settings=settings)

    get_db.assert_called_once_with(default_group_name="inbox")


@pytest.mark.asyncio
async def test_main_screen_copy_idea_body(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Copy action should handle all branches."""
    idea = service.create_idea("Test", body="hello world")
    no_body = service.create_idea("Empty")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        copy = mocker.patch("cogitus.ui.screens.main_screen.copy_to_clipboard")

        # No idea selected
        screen._selected_idea_pk = None
        screen.action_copy_idea_body()
        notify.assert_called_with("No idea selected", severity="warning")

        # Idea not found
        notify.reset_mock()
        screen._selected_idea_pk = 9999
        screen.action_copy_idea_body()
        notify.assert_called_with("Idea not found", severity="error")

        # Idea with no body
        notify.reset_mock()
        screen._selected_idea_pk = no_body.pk
        screen.action_copy_idea_body()
        notify.assert_called_with(
            "Idea has no body to copy", severity="warning"
        )

        # Success
        notify.reset_mock()
        screen._selected_idea_pk = idea.pk
        copy.return_value = True
        screen.action_copy_idea_body()
        copy.assert_called_once_with("hello world", app)
        notify.assert_called_with("Copied idea body to clipboard")

        # Selection copy takes precedence
        copy.reset_mock()
        notify.reset_mock()
        selected_text = "selected text"
        mocker.patch.object(
            screen,
            "get_selected_text",
            return_value=selected_text,
        )

        screen.action_copy_idea_body()
        copy.assert_called_once_with(selected_text, app)
        notify.assert_called_with("Copied selection to clipboard")

        # Clipboard unavailable
        notify.reset_mock()
        copy.reset_mock()
        copy.return_value = False
        screen.action_copy_idea_body()
        notify.assert_called_with("Clipboard unavailable", severity="warning")
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_selection_helper_falls_back_to_screen_selection(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Helper should use Screen-level selection text first."""
    service.create_idea("Test", body="hello world")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        selected_text = "selected via screen"
        mocker.patch.object(
            screen,
            "get_selected_text",
            return_value=selected_text,
        )
        assert screen._get_selected_rendered_body_text() == selected_text
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_selection_helper_returns_none_for_missing_extract(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Helper should return None when widget extraction returns None."""
    service.create_idea("Test", body="hello world")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        mocker.patch.object(screen, "get_selected_text", return_value="")
        body = screen.query_one("#idea-view-body")
        mocker.patch.object(
            type(body),
            "text_selection",
            new_callable=PropertyMock,
            return_value=object(),
        )
        mocker.patch.object(body, "get_selection", return_value=None)

        assert screen._get_selected_rendered_body_text() is None
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_selection_helper_returns_widget_selection_text(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Helper should return widget-level selected text when available."""
    service.create_idea("Test", body="hello world")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        mocker.patch.object(screen, "get_selected_text", return_value="")
        body = screen.query_one("#idea-view-body")
        mocker.patch.object(
            type(body),
            "text_selection",
            new_callable=PropertyMock,
            return_value=object(),
        )
        mocker.patch.object(
            body, "get_selection", return_value=("picked", "\n")
        )

        assert screen._get_selected_rendered_body_text() == "picked"
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_text_area_y_copies_selection(
    mocker: MockerFixture,
) -> None:
    """Pressing y with a selection copies text to clipboard."""

    class _TextAreaApp(App[None]):
        def compose(self) -> ComposeResult:
            yield CogitusTextArea("hello world", id="ta")

    app = _TextAreaApp()
    async with app.run_test() as pilot:
        ta = app.query_one("#ta", CogitusTextArea)
        copy = mocker.patch("cogitus.ui.widgets.text_area.copy_to_clipboard")
        notify = mocker.patch.object(ta, "notify")

        # y with no selection types normally
        ta.focus()
        await pilot.press("y")
        copy.assert_not_called()
        assert "y" in ta.text

        # y with selection copies instead of typing
        ta.text = "hello world"
        ta.select_all()
        copy.return_value = True
        await pilot.press("y")
        copy.assert_called_once_with("hello world", app)
        notify.assert_called_with("Copied selection to clipboard")

        # Failed clipboard copy shows warning
        notify.reset_mock()
        copy.return_value = False
        ta.select_all()
        await pilot.press("y")
        notify.assert_called_with("Clipboard unavailable", severity="warning")
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_y_binding_not_triggered_by_text_area_typing(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Typing y in form body should not trigger MainScreen copy binding."""
    service.create_idea("First", body="first body")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        copy_body = mocker.patch.object(screen, "action_copy_idea_body")
        screen.action_new_idea()
        await pilot.pause()

        form = app.screen
        assert isinstance(form, IdeaFormScreen)
        body = form.query_one("#body-input", CogitusTextArea)
        body.text = ""
        body.focus()

        await pilot.press("y")

        assert body.text == "y"
        copy_body.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_y_binding_not_triggered_by_text_area_selection_copy(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Copying selected text with y should not trigger MainScreen binding."""
    service.create_idea("First", body="first body")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        copy_body = mocker.patch.object(screen, "action_copy_idea_body")
        copy = mocker.patch("cogitus.ui.widgets.text_area.copy_to_clipboard")
        screen.action_new_idea()
        await pilot.pause()

        form = app.screen
        assert isinstance(form, IdeaFormScreen)
        body = form.query_one("#body-input", CogitusTextArea)
        body.text = "hello world"
        body.select_all()
        body.focus()

        await pilot.press("y")

        copy.assert_called_once_with("hello world", app)
        copy_body.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_y_binding_copies_rendered_body_selection(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Pressing y should copy selected text from rendered idea view."""
    service.create_idea("First", body="hello world")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        copy = mocker.patch("cogitus.ui.screens.main_screen.copy_to_clipboard")
        notify = mocker.patch.object(screen, "notify")
        copy.return_value = True
        selected_text = "selected text"
        mocker.patch.object(
            screen,
            "get_selected_text",
            return_value=selected_text,
        )

        await pilot.press("y")

        copy.assert_called_once_with(selected_text, app)
        notify.assert_called_with("Copied selection to clipboard")
        await pilot.pause()
