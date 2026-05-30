"""Tests for Textual screens and app integration."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone, tzinfo
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import PropertyMock

import pytest
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Markdown,
    OptionList,
    Rule,
    Select,
    Static,
    TextArea,
    Tree,
)
from textual.worker import WorkerState

from cogitus import datefmt as datefmt_module
from cogitus.app import CSS_PATH, CogitusApp
from cogitus.backends import BackendConfig, RemoteIdeaBackend, RemoteSyncResult
from cogitus.config import (
    DEFAULT_THEME,
    VALID_DATE_FORMATS,
    DataBackendMode,
    EditBodyCursorMode,
    NewIdeaGroupMode,
)
from cogitus.db import get_db
from cogitus.metadata import AppMetadata
from cogitus.search import SearchResult
from cogitus.services.idea_service import IdeaService
from cogitus.ui.screens.idea_form_screen import (
    AboutScreen,
    BackendConfigScreen,
    ConfirmDialog,
    GroupDeleteReassignScreen,
    GroupFormScreen,
    HelpScreen,
    IdeaFormScreen,
    NameInputScreen,
    RemoteCloneModeAction,
    RemoteCloneProgressScreen,
    RemoteCloneSwitchModeScreen,
    RemoteStartupRecoveryAction,
    RemoteStartupRecoveryScreen,
    _depth_first_group_options,
)
from cogitus.ui.screens.main_screen import MainScreen
from cogitus.ui.widgets.footer import CogitusStatusBar, FooterNotice
from cogitus.ui.widgets.idea_list import IdeaListPanel
from cogitus.ui.widgets.idea_view import IdeaView
from cogitus.ui.widgets.search_results import SearchResultsList
from cogitus.ui.widgets.select_all import select_all_focused_text
from cogitus.ui.widgets.text_area import CogitusTextArea
from tests.helpers import _focused_widget

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture
    from sqliter import SqliterDB
    from textual.pilot import Pilot
    from textual.screen import Screen

    from cogitus.repositories.snapshot_import_repo import SnapshotImportProgress


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


class _StyledSingleScreenApp(_SingleScreenApp):
    """Host app that mounts a screen with the project stylesheet loaded."""

    def __init__(self, screen: Screen[Any]) -> None:
        App.__init__(self, css_path=CSS_PATH)
        self._screen = screen


class _ScrollConfigSingleScreenApp(_SingleScreenApp):
    """Host app with rendered idea scroll preservation config."""

    def __init__(
        self,
        screen: Screen[Any],
        *,
        save_idea_scroll_pos: bool,
    ) -> None:
        super().__init__(screen)
        self._preserve_idea_scroll_position = save_idea_scroll_pos


def _button_label_plain(button: Button) -> str:
    """Return the rendered plain button label."""
    label = button.label
    assert not isinstance(label, str)
    return label.plain


class _FakeSettings:
    """Minimal settings double for CogitusApp tests."""

    def __init__(  # noqa: PLR0913
        self,
        last_viewed_idea_pk: int = 0,
        edit_body_cursor_mode: str = "remember",
        new_idea_group_mode: str = "contextual",
        default_group_name: str = "default",
        backend_config: BackendConfig | None = None,
        *,
        prompt_after_clone: bool = True,
        timezone: str = "",
        date_format: str = "",
        save_idea_scroll_pos: bool = True,
    ) -> None:
        resolved_backend = backend_config or BackendConfig(
            mode=DataBackendMode.LOCAL,
            api_base_url="",
            api_username="",
            api_password="",
        )
        self.last_viewed_idea_pk = last_viewed_idea_pk
        self.theme = DEFAULT_THEME
        self.edit_body_cursor_mode = edit_body_cursor_mode
        self.new_idea_group_mode = new_idea_group_mode
        self.default_group_name = default_group_name
        self.data_backend_mode = resolved_backend.mode.value
        self.remote_api_base_url = resolved_backend.api_base_url
        self.remote_api_username = resolved_backend.api_username
        self.remote_api_password = resolved_backend.api_password
        self.prompt_after_clone = prompt_after_clone
        self.timezone = timezone
        self.date_format = date_format
        self.save_idea_scroll_pos = save_idea_scroll_pos
        self.saved = False

    def save(self) -> None:
        """Record save invocation."""
        self.saved = True

    def set(
        self,
        key: str,
        value: object,
        *,
        autosave: bool = True,
    ) -> None:
        """Store one setting value through the settings API."""
        setattr(self, key, value)
        if autosave:
            self.save()


class _FrozenDateTime:
    """Controllable datetime replacement for relative-time tests."""

    current = datetime.now(tz=timezone.utc)

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        """Return the configured current time."""
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)

    @classmethod
    def fromtimestamp(
        cls,
        timestamp: float,
        tz: tzinfo | None = None,
    ) -> datetime:
        """Delegate timestamp conversion to the real datetime class."""
        return datetime.fromtimestamp(timestamp, tz=tz)


_MAX_WAIT_TICKS = 200


def _remote_secret() -> str:
    """Return the fixed test secret without a password-like assignment."""
    return "secret" + "-pass"


async def _wait_for_search_active(
    pilot: Pilot[Any],
    search: Input,
) -> None:
    """Wait until the search input enters active-search mode."""
    for _ in range(_MAX_WAIT_TICKS):
        if search.has_class("search-active"):
            return
        await pilot.pause()
    pytest.fail("Timed out waiting for active-search mode")


async def _wait_for_search_results(
    pilot: Pilot[Any],
    search: Input,
    results: SearchResultsList,
) -> None:
    """Wait until active search has populated selectable result rows."""
    for _ in range(_MAX_WAIT_TICKS):
        if search.has_class("search-active") and results.has_matches():
            return
        await pilot.pause()
    pytest.fail("Timed out waiting for selectable search results")


async def _wait_for_search_cleared(
    pilot: Pilot[Any],
    search: Input,
) -> None:
    """Wait until search has been fully cleared."""
    for _ in range(_MAX_WAIT_TICKS):
        if search.value == "" and not search.has_class("search-active"):
            return
        await pilot.pause()
    pytest.fail("Timed out waiting for search to clear")


async def _wait_for_scroll_y(
    pilot: Pilot[Any],
    container: VerticalScroll,
    expected: int,
) -> None:
    """Wait until a scroll container reaches a vertical offset."""
    for _ in range(_MAX_WAIT_TICKS):
        if round(container.scroll_y) == expected:
            return
        await pilot.pause()
    pytest.fail(f"Timed out waiting for scroll_y={expected}")


async def _wait_for_scrollable(
    pilot: Pilot[Any],
    container: VerticalScroll,
) -> None:
    """Wait until a scroll container has vertical overflow."""
    for _ in range(_MAX_WAIT_TICKS):
        if container.max_scroll_y > 0:
            return
        await pilot.pause()
    pytest.fail("Timed out waiting for scrollable content")


async def _scroll_content_down(
    pilot: Pilot[Any],
    view: IdeaView,
    container: VerticalScroll,
) -> int:
    """Scroll the idea content pane using normal keyboard input."""
    view.focus_content()
    await pilot.pause()
    for _ in range(_MAX_WAIT_TICKS):
        await pilot.press("down")
        await pilot.pause()
        scroll_y = round(container.scroll_y)
        if scroll_y > 0:
            return scroll_y
    pytest.fail("Timed out waiting for keyboard scroll")


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

        notify.reset_mock()
        screen.action_save_and_close()
        notify.assert_called_once()
        dismiss.assert_not_called()

        screen.query_one("#title-input", Input).value = "My Idea"
        screen.query_one("#body-input", TextArea).text = "Body"
        screen.query_one("#tags-input", Input).value = "python, testing"
        screen.action_save()

        dismiss.assert_not_called()
        created = service.list_ideas()[0]
        pk = created.pk
        assert screen._idea is not None
        assert screen._idea.pk == pk
        assert created.title == "My Idea"
        assert {tag.name for tag in created.tags.fetch_all()} == {
            "python",
            "testing",
        }

        screen.action_save_and_close()
        dismiss.assert_called_once_with(pk)
        created_after_close = service.get_idea(pk)
        assert created_after_close is not None
        assert created_after_close.title == "My Idea"
        assert {tag.name for tag in created_after_close.tags.fetch_all()} == {
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
        dismiss.assert_not_called()

        updated = service.get_idea(idea.pk)
        assert updated is not None
        assert updated.title == "Updated"

        save_action = mocker.patch.object(screen, "action_save")
        save_close_action = mocker.patch.object(
            screen,
            "action_save_and_close",
        )
        cancel_action = mocker.patch.object(screen, "action_cancel")
        await pilot.click("#save-btn")
        save_action.assert_called_once()
        await pilot.click("#save-close-btn")
        save_close_action.assert_called_once()
        await pilot.click("#cancel-btn")
        cancel_action.assert_called_once()

        IdeaFormScreen.action_save_and_close(screen)
        dismiss.assert_called_once_with(idea.pk)
        await pilot.pause()

    clean_screen = IdeaFormScreen(service, idea=updated)
    app_clean = _SingleScreenApp(clean_screen)
    async with app_clean.run_test() as pilot:
        dismiss_clean = mocker.patch.object(clean_screen, "dismiss")
        clean_screen.query_one("#title-input", Input).value = "Updated"
        clean_screen.query_one("#body-input", TextArea).text = "new"
        clean_screen.query_one("#tags-input", Input).value = "three"

        IdeaFormScreen.action_cancel(clean_screen)

        dismiss_clean.assert_called_once_with(None)
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_keyboard_save_shortcuts_from_body_editor(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Body editor shortcuts should route save actions without text edits."""
    idea = service.create_idea("Original", body="old")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        body = screen.query_one("#body-input", CogitusTextArea)
        body.text = "keyboard body"
        body.cursor_location = (0, 8)
        body.focus()
        await pilot.pause()

        await pilot.press("f5")
        await pilot.pause()

        dismiss.assert_not_called()
        saved = service.get_idea(idea.pk)
        assert saved is not None
        assert saved.body == "keyboard body"

        await pilot.press("ctrl+s")
        await pilot.pause()

        dismiss.assert_called_once_with(idea.pk)
        assert body.text == "keyboard body"


@pytest.mark.asyncio
async def test_idea_form_save_notifies_and_reports_saved_idea(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Stay-open save should toast and report the saved idea pk."""
    idea = service.create_idea("Original", body="old")
    on_saved = mocker.Mock()
    screen = IdeaFormScreen(service, idea=idea, on_saved=on_saved)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        dismiss = mocker.patch.object(screen, "dismiss")
        screen.query_one("#body-input", CogitusTextArea).text = "new body"

        screen.action_save()

        notify.assert_called_once_with("Idea saved")
        on_saved.assert_called_once_with(idea.pk)
        dismiss.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_save_missing_idea_reports_error(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Stay-open save should report a missing edited idea."""
    idea = service.create_idea("Original", body="old")
    on_saved = mocker.Mock()
    screen = IdeaFormScreen(service, idea=idea, on_saved=on_saved)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        push_screen = mocker.patch.object(app, "push_screen")
        dismiss = mocker.patch.object(screen, "dismiss")
        mocker.patch.object(service, "update_idea", return_value=None)
        screen.query_one("#body-input", CogitusTextArea).text = "new body"

        screen.action_save()
        screen.action_cancel()

        notify.assert_called_once_with("Idea not found", severity="error")
        on_saved.assert_not_called()
        push_screen.assert_called_once()
        dismiss.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_screen_create_notifies_backend_errors(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Create flow should surface backend errors instead of crashing."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        notify = mocker.patch.object(screen, "notify")
        mocker.patch.object(
            service,
            "create_idea",
            side_effect=ValueError("Remote API authentication failed"),
        )

        screen.query_one("#title-input", Input).value = "Remote Idea"
        screen.action_save()

        notify.assert_called_once_with(
            "Remote API authentication failed",
            severity="error",
        )
        dismiss.assert_not_called()

        notify.reset_mock()
        screen.action_save_and_close()
        notify.assert_called_once_with(
            "Remote API authentication failed",
            severity="error",
        )
        dismiss.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_screen_update_notifies_backend_errors(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Update flow should surface backend errors instead of crashing."""
    idea = service.create_idea("Original", body="old")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        notify = mocker.patch.object(screen, "notify")
        mocker.patch.object(
            service,
            "update_idea",
            side_effect=ValueError("Idea has been modified on the server"),
        )

        screen.query_one("#title-input", Input).value = "Updated"
        screen.action_save()

        notify.assert_called_once_with(
            "Idea has been modified on the server",
            severity="error",
        )
        dismiss.assert_not_called()

        notify.reset_mock()
        screen.action_save_and_close()
        notify.assert_called_once_with(
            "Idea has been modified on the server",
            severity="error",
        )
        dismiss.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_buttons_size_to_content(
    service: IdeaService,
) -> None:
    """Idea-form buttons should size to content with balanced padding."""
    screen = IdeaFormScreen(service)
    app = _StyledSingleScreenApp(screen)

    async with app.run_test() as pilot:
        expected_labels = {
            "#save-btn": "Save [F5]",
            "#save-close-btn": "Save & Close [Ctrl+s]",
            "#cancel-btn": "Cancel [Esc]",
        }
        for button_id, expected_label in expected_labels.items():
            button = screen.query_one(button_id, Button)
            assert _button_label_plain(button) == expected_label
            leftover = button.region.width - len(expected_label)
            assert leftover % 2 == 0
            assert leftover >= 4

        await pilot.pause()


def test_idea_form_save_bindings_are_split() -> None:
    """Idea form should bind checkpoint and close saves separately."""
    actions_by_key: dict[str, str] = {}
    for binding in IdeaFormScreen.BINDINGS:
        assert isinstance(binding, Binding)
        actions_by_key[binding.key] = binding.action

    assert actions_by_key["f5"] == "save"
    assert actions_by_key["ctrl+s"] == "save_and_close"


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
            return_value=Select.NULL,
        )

        screen.action_save()

        notify.assert_called_once_with(
            "Invalid group selection",
            severity="error",
        )
        dismiss.assert_not_called()

        notify.reset_mock()
        screen.action_save_and_close()

        notify.assert_called_once_with(
            "Invalid group selection",
            severity="error",
        )
        dismiss.assert_not_called()
        await pilot.pause()


def test_idea_form_restore_focus_after_cancel_reject_noop_without_target(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Focus restore should no-op when no pre-confirm target was stored."""
    screen = IdeaFormScreen(service)

    call_after_refresh = mocker.patch.object(screen, "call_after_refresh")
    screen._focus_after_cancel_reject = None

    screen._restore_focus_after_cancel_reject()

    call_after_refresh.assert_not_called()


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
async def test_idea_form_edit_mode_keeps_tags_autocomplete_hidden_on_mount(
    service: IdeaService,
) -> None:
    """Edit mode should not open tags autocomplete from preloaded values."""
    service.create_idea("Tag source", tags=["one", "two"])
    idea = service.create_idea("Original", body="old", tags=["one", "two"])
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        autocomplete = screen.query_one("#tags-autocomplete", OptionList)

        assert app.focused is body
        assert autocomplete.has_class("-hidden")
        assert autocomplete.option_count == 0
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_unfocused_tags_value_change_keeps_autocomplete_hidden(
    service: IdeaService,
) -> None:
    """Programmatic tag updates should not open autocomplete off-focus."""
    service.create_idea("Tag source", tags=["alpha"])
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        title = screen.query_one("#title-input", Input)
        tags_input = screen.query_one("#tags-input", Input)
        autocomplete = screen.query_one("#tags-autocomplete", OptionList)

        assert app.focused is title
        tags_input.value = "a"
        tags_input.cursor_position = 1
        await pilot.pause()

        assert app.focused is title
        assert autocomplete.has_class("-hidden")
        assert autocomplete.option_count == 0

        tags_input.focus()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()

        assert not autocomplete.has_class("-hidden")
        assert [str(option.prompt) for option in autocomplete.options] == [
            "alpha"
        ]


@pytest.mark.asyncio
async def test_idea_form_ctrl_a_selects_focused_editable_text(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Ctrl+a should select all text in the focused form editor."""
    service.create_idea("A", tags=["alpha"])
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        title = screen.query_one("#title-input", Input)
        tags_input = screen.query_one("#tags-input", Input)
        body = screen.query_one("#body-input", CogitusTextArea)
        autocomplete = screen.query_one("#tags-autocomplete", OptionList)

        title.value = "Draft title"
        title.focus()
        await pilot.pause()
        event = mocker.Mock()
        event.key = "ctrl+A"
        screen.on_key(cast("events.Key", event))
        assert title.selected_text == "Draft title"
        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

        tags_input.value = "python, testing"
        tags_input.cursor_position = len(tags_input.value)
        tags_input.focus()
        await pilot.pause()
        autocomplete.set_options(["python"])
        autocomplete.remove_class("-hidden")
        assert not autocomplete.has_class("-hidden")

        event = mocker.Mock()
        event.key = "ctrl+A"
        assert screen._handle_select_all_key(cast("events.Key", event)) is True
        assert tags_input.selected_text == "python, testing"
        assert autocomplete.has_class("-hidden")

        autocomplete.set_options(["python"])
        autocomplete.remove_class("-hidden")
        await pilot.press("ctrl+a")
        await pilot.pause()
        assert tags_input.selected_text == "python, testing"
        assert autocomplete.has_class("-hidden")

        body.text = "First line\nSecond line"
        body.focus()
        await pilot.pause()
        event = mocker.Mock()
        event.key = "ctrl+shift+a"
        assert screen._handle_select_all_key(cast("events.Key", event)) is True
        assert body.selected_text == body.text

        await pilot.press("ctrl+a")
        await pilot.pause()
        assert body.selected_text == body.text


@pytest.mark.asyncio
async def test_idea_form_ctrl_a_preserves_body_scroll_offset(
    service: IdeaService,
) -> None:
    """Body select-all should not jump the visible editor viewport."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        body.text = "\n".join(f"Line {index}" for index in range(80))
        body.focus()
        await pilot.pause()

        body.scroll_to(y=20, animate=False, immediate=True)
        await pilot.pause()
        scroll_y = body.scroll_offset.y
        assert scroll_y > 0

        await pilot.press("ctrl+a")
        await pilot.pause()

        assert body.selected_text == body.text
        assert body.scroll_offset.y == scroll_y


@pytest.mark.asyncio
async def test_idea_form_select_all_ignores_non_editable_focus(
    service: IdeaService,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Select-all helper should ignore missing or non-editor focus."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        monkeypatch.setattr(type(app), "focused", property(lambda _self: None))
        assert screen._select_all_focused_editable() is False

        monkeypatch.undo()
        screen.query_one("#cancel-btn", Button).focus()
        await pilot.pause()
        assert screen._select_all_focused_editable() is False
        event = mocker.Mock()
        event.key = "ctrl+a"
        assert screen._handle_select_all_key(cast("events.Key", event)) is False
        event.prevent_default.assert_not_called()
        event.stop.assert_not_called()

        event = mocker.Mock()
        event.key = "enter"
        assert screen._handle_select_all_key(cast("events.Key", event)) is False
        event.prevent_default.assert_not_called()
        event.stop.assert_not_called()


def test_select_all_focused_text_ignores_unrelated_focus(
    mocker: MockerFixture,
) -> None:
    """Select-all helper should ignore focus outside its owner."""
    owner = mocker.Mock()
    focused = mocker.Mock()
    focused.screen = object()
    focused.ancestors = []
    owner.app.focused = focused

    assert select_all_focused_text(owner) is False


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
) -> None:
    """Esc should close tags autocomplete before dirty cancel handling."""
    service.create_idea("A", tags=["alpha"])
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

        await pilot.press("escape")
        await pilot.pause()
        assert autocomplete.has_class("-hidden")
        assert app.screen is screen

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)


@pytest.mark.asyncio
async def test_idea_form_clean_new_cancel_dismisses_without_confirm(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Clean new idea cancel should close without discard confirmation."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        push_screen = mocker.patch.object(app, "push_screen")

        screen.action_cancel()

        dismiss.assert_called_once_with(None)
        push_screen.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_cancel_confirms_before_discarding_dirty_new(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Dirty new idea cancel should require explicit discard confirmation."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        push_screen = mocker.patch.object(app, "push_screen")
        title = screen.query_one("#title-input", Input)
        body = screen.query_one("#body-input", CogitusTextArea)

        title.value = "Draft title"
        body.text = "Draft body"

        screen.action_cancel()

        dismiss.assert_not_called()
        push_screen.assert_called_once()
        confirm = push_screen.call_args.args[0]
        callback = push_screen.call_args.kwargs["callback"]

        assert isinstance(confirm, ConfirmDialog)

        callback(False)
        dismiss.assert_not_called()
        assert title.value == "Draft title"
        assert body.text == "Draft body"

        callback(True)
        dismiss.assert_called_once_with(None)
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_cancel_after_save_stays_clean(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Cancel after save-in-place should not prompt until more edits occur."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        push_screen = mocker.patch.object(app, "push_screen")
        title = screen.query_one("#title-input", Input)
        body = screen.query_one("#body-input", CogitusTextArea)

        title.value = "Saved draft"
        body.text = "Saved body"
        screen.action_save()
        screen.action_cancel()

        dismiss.assert_called_once_with(None)
        push_screen.assert_not_called()

        dismiss.reset_mock()
        title.value = "Changed after save"
        screen.action_cancel()

        dismiss.assert_not_called()
        push_screen.assert_called_once()
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_cancel_confirms_before_discarding_dirty_edit(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Dirty edit cancel should require explicit discard confirmation."""
    idea = service.create_idea("Original", body="abcdef", tags=["one"])
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        set_cursor = mocker.patch.object(service, "set_idea_cursor_position")
        push_screen = mocker.patch.object(app, "push_screen")
        body = screen.query_one("#body-input", CogitusTextArea)
        body.text = "changed"
        body.cursor_location = screen._cursor_location_from_index(body.text, 4)

        screen.action_cancel()

        dismiss.assert_not_called()
        set_cursor.assert_not_called()
        push_screen.assert_called_once()
        confirm = push_screen.call_args.args[0]
        callback = push_screen.call_args.kwargs["callback"]

        assert isinstance(confirm, ConfirmDialog)

        callback(False)
        dismiss.assert_not_called()
        set_cursor.assert_not_called()

        callback(True)
        dismiss.assert_called_once_with(None)
        set_cursor.assert_called_once_with(idea.pk, 4)
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_escape_rejects_discard_and_restores_edit_focus(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Esc in discard confirm should resume editing without data loss."""
    idea = service.create_idea("Original", body="abcdef")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        set_cursor = mocker.patch.object(service, "set_idea_cursor_position")
        body = screen.query_one("#body-input", CogitusTextArea)

        body.focus()
        body.text = "changed body"
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)

        await pilot.press("escape")
        await pilot.pause()

        assert cast("object", app.screen) is screen
        assert body.text == "changed body"
        assert app.focused is body
        dismiss.assert_not_called()
        set_cursor.assert_not_called()


@pytest.mark.asyncio
async def test_idea_form_escape_still_closes_autocomplete_before_dirty_confirm(
    service: IdeaService,
) -> None:
    """Autocomplete dismissal should still win before discard confirm."""
    idea = service.create_idea("Original", body="old", tags=["alpha"])
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        tags_input = screen.query_one("#tags-input", Input)
        autocomplete = screen.query_one("#tags-autocomplete", OptionList)
        screen.query_one("#body-input", CogitusTextArea).text = "changed"

        tags_input.focus()
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        await pilot.press("escape")
        await pilot.pause()
        assert autocomplete.has_class("-hidden")
        assert app.screen is screen

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)


@pytest.mark.asyncio
async def test_idea_form_discard_confirm_without_focused_widget(
    service: IdeaService,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discard confirm should cope when the form has no focused widget."""
    idea = service.create_idea("Original", body="abcdef")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        push_screen = mocker.patch.object(app, "push_screen")
        monkeypatch.setattr(type(app), "focused", property(lambda _self: None))

        screen._confirm_discard_changes()

        assert screen._focus_after_cancel_reject is None
        push_screen.assert_called_once()
        confirm = push_screen.call_args.args[0]
        assert isinstance(confirm, ConfirmDialog)
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_discard_confirm_ignores_button_focus_target(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Discard confirm should not restore focus to the cancel button."""
    idea = service.create_idea("Original", body="abcdef")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        cancel = screen.query_one("#cancel-btn", Button)
        push_screen = mocker.patch.object(app, "push_screen")

        body.focus()
        body.text = "changed body"
        await pilot.pause()

        cancel.focus()
        await pilot.pause()

        screen._confirm_discard_changes()

        assert app.focused is cancel
        assert screen._focus_after_cancel_reject is None
        push_screen.assert_called_once()
        await pilot.pause()


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
async def test_idea_form_autocomplete_blur_descendant_branch(
    service: IdeaService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dismiss helper should keep popup open for focused descendants."""
    service.create_idea("A", tags=["alpha"])
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

        class _FocusedDescendant:
            @property
            def ancestors(self) -> list[OptionList]:
                return [autocomplete]

        class _FocusedOther:
            @property
            def ancestors(self) -> list[object]:
                return []

        monkeypatch.setattr(
            type(app),
            "focused",
            property(lambda _self: _FocusedDescendant()),
        )
        screen._dismiss_tag_autocomplete_if_unfocused()
        assert not autocomplete.has_class("-hidden")

        monkeypatch.setattr(
            type(app),
            "focused",
            property(lambda _self: _FocusedOther()),
        )
        screen._dismiss_tag_autocomplete_if_unfocused()
        assert autocomplete.has_class("-hidden")


@pytest.mark.asyncio
async def test_idea_form_option_selected_ignores_other_option_lists(
    service: IdeaService,
) -> None:
    """OptionSelected from unrelated lists should be ignored."""
    service.create_idea("A", tags=["alpha"])
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
        before = tags_input.value

        foreign = OptionList("noop", id="other-autocomplete")
        screen.on_option_list_option_selected(
            OptionList.OptionSelected(
                foreign,
                foreign.options[0],
                0,
            ),
        )
        await pilot.pause()

        assert tags_input.value == before
        assert not autocomplete.has_class("-hidden")


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
async def test_main_screen_search_by_tag_action(
    service: IdeaService,
) -> None:
    """action_search_by_tag should set search input and focus it."""
    service.create_idea("Tagged", tags=["python"])
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        screen.action_search_by_tag("python")
        await pilot.pause()

        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        assert search.value == "tag:python"
        assert search.has_focus


@pytest.mark.asyncio
async def test_main_screen_search_by_tag_quotes_multi_word_tags(
    service: IdeaService,
) -> None:
    """Tag searches should quote multi-word tag values."""
    service.create_idea("Tagged", tags=["api design"])
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        screen.action_search_by_tag("api design")
        await pilot.pause()

        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        assert search.value == "tag:'api design'"
        assert search.has_focus


@pytest.mark.asyncio
async def test_main_screen_shows_custom_app_header(
    service: IdeaService,
) -> None:
    """Main screen should show the version in the header icon slot."""
    service.create_idea("First")
    screen = MainScreen(
        service,
        app_metadata=AppMetadata(
            title="Cogitus",
            version="0.10.0",
        ),
    )
    app = _StyledSingleScreenApp(screen)

    async with app.run_test() as pilot:
        await pilot.pause()
        header = screen.query_one(Header)
        header_icon = header.children[0]

        assert header.icon == "v0.10.0"
        assert header_icon.content_size.width >= len(header.icon)


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
        dismiss = mocker.patch.object(screen, "dismiss")

        screen.action_save()

        set_cursor.assert_called_with(idea.pk, 2)
        dismiss.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_idea_form_persists_cursor_position_on_edit_save_and_close(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Edit save-and-close should persist current body cursor position."""
    idea = service.create_idea("Original", body="abcdef")
    set_cursor = mocker.patch.object(service, "set_idea_cursor_position")
    screen = IdeaFormScreen(service, idea=idea)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        body = screen.query_one("#body-input", CogitusTextArea)
        body.cursor_location = screen._cursor_location_from_index(body.text, 3)
        screen.query_one("#title-input", Input).value = "Updated"
        dismiss = mocker.patch.object(screen, "dismiss")

        screen.action_save_and_close()

        set_cursor.assert_called_with(idea.pk, 3)
        dismiss.assert_called_once_with(idea.pk)
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


def test_idea_form_group_options_are_depth_first(
    service: IdeaService,
) -> None:
    """Group dropdown options should show nested groups in tree order."""
    writing = service.create_group("writing")
    scenes = service.create_group("scenes", parent_pk=writing.pk)
    work = service.create_group("work")
    cogitus = service.create_group("cogitus", parent_pk=work.pk)
    api = service.create_group("api", parent_pk=cogitus.pk)
    default = next(
        group
        for group in service.list_groups()
        if group.name == service.default_group_name
    )

    options = _depth_first_group_options(service.list_groups())

    assert options == [
        ("default", default.pk),
        ("work", work.pk),
        ("  cogitus", cogitus.pk),
        ("    api", api.pk),
        ("writing", writing.pk),
        ("  scenes", scenes.pk),
    ]


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


def test_idea_form_new_mode_has_no_unsaved_changes_before_mount(
    service: IdeaService,
) -> None:
    """New mode should treat missing pre-mount baseline as clean."""
    screen = IdeaFormScreen(service)
    assert screen._has_unsaved_changes() is False


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
async def test_remote_startup_recovery_screen_actions(
    mocker: MockerFixture,
) -> None:
    """Startup recovery modal should dismiss with the selected action."""
    screen = RemoteStartupRecoveryScreen("Could not reach the remote API")
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")

        await pilot.click("#retry-remote-btn")
        dismiss.assert_called_once_with(RemoteStartupRecoveryAction.RETRY)

        dismiss.reset_mock()
        await pilot.click("#use-cache-btn")
        dismiss.assert_called_once_with(RemoteStartupRecoveryAction.USE_CACHE)

        dismiss.reset_mock()
        await pilot.click("#use-local-btn")
        dismiss.assert_called_once_with(
            RemoteStartupRecoveryAction.SWITCH_LOCAL
        )

        dismiss.reset_mock()
        await pilot.click("#quit-startup-btn")
        dismiss.assert_called_once_with(RemoteStartupRecoveryAction.QUIT)
        await pilot.pause()


@pytest.mark.asyncio
async def test_remote_startup_recovery_screen_layout() -> None:
    """Recovery modal should be centered and wide enough for its contents."""
    screen = RemoteStartupRecoveryScreen("Could not reach the remote API")
    app = _StyledSingleScreenApp(screen)

    async with app.run_test() as pilot:
        container = screen.query_one("#remote-startup-container", Vertical)
        center_x = container.region.x + (container.region.width // 2)
        center_y = container.region.y + (container.region.height // 2)

        assert abs(center_x - (app.size.width // 2)) <= 2
        assert abs(center_y - (app.size.height // 2)) <= 2
        assert container.region.width >= 70

        expected_labels = {
            "#retry-remote-btn": "Retry [R]",
            "#use-cache-btn": "Use Cache [C]",
            "#use-local-btn": "Use Local [L]",
            "#quit-startup-btn": "Quit [Q]",
        }
        for button_id, expected_label in expected_labels.items():
            button = screen.query_one(button_id, Button)
            assert _button_label_plain(button) == expected_label
            leftover = button.region.width - len(expected_label)
            assert leftover % 2 == 0
            assert leftover >= 4

        await pilot.pause()


@pytest.mark.asyncio
async def test_remote_startup_recovery_screen_mentions_read_only_cache() -> (
    None
):
    """Recovery modal should make cached mode read-only explicit."""
    screen = RemoteStartupRecoveryScreen("Could not reach the remote API")
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        title = screen.query_one("#form-title", Static)
        message = screen.query_one("#remote-startup-message", Static)
        assert str(title.content) == "Remote Sync Failed"
        assert "READ-ONLY mode" in str(message.content)
        assert "until remote sync succeeds again" in str(message.content)
        await pilot.pause()


@pytest.mark.asyncio
async def test_group_form_buttons_size_to_content(
    service: IdeaService,
) -> None:
    """Group-form buttons should size to content with balanced padding."""
    group_form = GroupFormScreen(service=service)
    app = _StyledSingleScreenApp(group_form)

    async with app.run_test() as pilot:
        expected_labels = {
            "#save-group-btn": "Save [Ctrl+s]",
            "#cancel-group-btn": "Cancel [Esc]",
        }
        for button_id, expected_label in expected_labels.items():
            button = group_form.query_one(button_id, Button)
            assert _button_label_plain(button) == expected_label
            leftover = button.region.width - len(expected_label)
            assert leftover % 2 == 0
            assert leftover >= 4

        await pilot.pause()


@pytest.mark.asyncio
async def test_name_input_screen_prefills_and_validates(
    mocker: MockerFixture,
) -> None:
    """Name input modal should preload text and validate empty input."""
    screen = NameInputScreen(
        title="Rename Idea",
        initial_value="Old title",
        placeholder="Idea title...",
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        name_input = screen.query_one("#name-input", Input)
        assert name_input.value == "Old title"
        assert name_input.cursor_position == len("Old title")

        notify = mocker.patch.object(screen, "notify")
        dismiss = mocker.patch.object(screen, "dismiss")

        name_input.value = "   "
        screen.action_save()
        notify.assert_called_once_with("Name is required", severity="error")
        dismiss.assert_not_called()

        notify.reset_mock()
        name_input.value = "Renamed"
        screen.action_save()
        dismiss.assert_called_once_with("Renamed")
        await pilot.pause()


@pytest.mark.asyncio
async def test_name_input_screen_enter_submits(
    mocker: MockerFixture,
) -> None:
    """Enter should submit the rename modal from the text input."""
    screen = NameInputScreen(
        title="Rename Group",
        initial_value="backend",
        placeholder="Group name...",
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")

        screen.query_one("#name-input", Input).value = "frontend"
        await pilot.press("enter")

        dismiss.assert_called_once_with("frontend")
        await pilot.pause()


@pytest.mark.asyncio
async def test_name_input_screen_ctrl_s_submits(
    mocker: MockerFixture,
) -> None:
    """Ctrl+s should submit the rename modal from the text input."""
    screen = NameInputScreen(
        title="Rename Group",
        initial_value="backend",
        placeholder="Group name...",
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")

        screen.query_one("#name-input", Input).value = "frontend"
        await pilot.press("ctrl+s")

        dismiss.assert_called_once_with("frontend")
        await pilot.pause()


@pytest.mark.asyncio
async def test_single_field_modals_ctrl_a_selects_input_text(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Ctrl+a should select text in group and rename modal inputs."""
    group_form = GroupFormScreen(service=service)
    group_app = _SingleScreenApp(group_form)

    async with group_app.run_test() as pilot:
        group_input = group_form.query_one("#group-name-input", Input)
        group_input.value = "backend"
        group_input.cursor_position = len(group_input.value)
        group_input.focus()
        await pilot.pause()

        event = mocker.Mock()
        event.key = "enter"
        group_form.on_key(cast("events.Key", event))

        await pilot.press("ctrl+a")
        await pilot.pause()

        assert group_input.selected_text == "backend"

    name_form = NameInputScreen(
        title="Rename Idea",
        initial_value="Original title",
        placeholder="Idea title...",
    )
    name_app = _SingleScreenApp(name_form)

    async with name_app.run_test() as pilot:
        name_input = name_form.query_one("#name-input", Input)
        await pilot.press("ctrl+a")
        await pilot.pause()

        assert name_input.selected_text == "Original title"


@pytest.mark.asyncio
async def test_backend_config_screen_validates_remote_requirements(
    mocker: MockerFixture,
) -> None:
    """Remote mode should require URL, username, and password."""
    screen = BackendConfigScreen(
        BackendConfig(
            mode=DataBackendMode.LOCAL,
            api_base_url="",
            api_username="",
            api_password="",
        )
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        dismiss = mocker.patch.object(screen, "dismiss")

        mode_select = screen.query_one("#backend-mode-select", Select)
        mode_select.value = DataBackendMode.API
        screen.action_save()

        notify.assert_called_once_with(
            "Remote API mode requires URL, username, and password",
            severity="error",
        )
        dismiss.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_backend_config_screen_is_centered_modal() -> None:
    """Backend config should render as a centered modal, not fullscreen."""
    screen = BackendConfigScreen(
        BackendConfig(
            mode=DataBackendMode.LOCAL,
            api_base_url="",
            api_username="",
            api_password="",
        )
    )
    app = _StyledSingleScreenApp(screen)

    async with app.run_test() as pilot:
        container = screen.query_one(
            "#backend-config-container",
            VerticalScroll,
        )
        center_x = container.region.x + (container.region.width // 2)
        center_y = container.region.y + (container.region.height // 2)

        assert abs(center_x - (app.size.width // 2)) <= 2
        assert abs(center_y - (app.size.height // 2)) <= 2
        assert container.region.width < app.size.width
        assert container.region.height < app.size.height
        assert container.region.width >= 60

        await pilot.pause()


@pytest.mark.asyncio
async def test_backend_config_screen_focuses_mode_select_on_mount() -> None:
    """Backend config modal should auto-focus the mode select on mount."""
    screen = BackendConfigScreen(
        BackendConfig(
            mode=DataBackendMode.LOCAL,
            api_base_url="",
            api_username="",
            api_password="",
        )
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        mode_select = screen.query_one("#backend-mode-select", Select)
        assert _focused_widget(app) is mode_select
        await pilot.pause()


@pytest.mark.asyncio
async def test_backend_config_screen_ctrl_a_selects_focused_input(
    mocker: MockerFixture,
) -> None:
    """Ctrl+a should select text in backend config text inputs."""
    screen = BackendConfigScreen(
        BackendConfig(
            mode=DataBackendMode.API,
            api_base_url="http://127.0.0.1:8000",
            api_username="api-user",
            api_password=_remote_secret(),
        )
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        api_url = screen.query_one("#backend-api-url", Input)
        api_url.focus()
        await pilot.pause()

        event = mocker.Mock()
        event.key = "enter"
        screen.on_key(cast("events.Key", event))

        await pilot.press("ctrl+a")
        await pilot.pause()

        assert api_url.selected_text == "http://127.0.0.1:8000"


@pytest.mark.asyncio
async def test_backend_config_screen_returns_selected_config(
    mocker: MockerFixture,
) -> None:
    """Saving backend config should return the normalized modal payload."""
    screen = BackendConfigScreen(
        BackendConfig(
            mode=DataBackendMode.LOCAL,
            api_base_url="",
            api_username="",
            api_password="",
        )
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(screen, "dismiss")
        mode_select = screen.query_one("#backend-mode-select", Select)
        mode_select.value = DataBackendMode.API
        screen.query_one(
            "#backend-api-url", Input
        ).value = "http://127.0.0.1:8000"
        screen.query_one("#backend-api-username", Input).value = "api-user"
        screen.query_one(
            "#backend-api-password", Input
        ).value = _remote_secret()

        screen.action_save()

        dismiss.assert_called_once_with(
            BackendConfig(
                mode=DataBackendMode.API,
                api_base_url="http://127.0.0.1:8000",
                api_username="api-user",
                api_password=_remote_secret(),
            )
        )
        await pilot.pause()


@pytest.mark.asyncio
async def test_backend_config_screen_button_routing_and_guard_paths(
    mocker: MockerFixture,
) -> None:
    """Backend config modal should route buttons and guard invalid mode."""
    screen = BackendConfigScreen(
        BackendConfig(
            mode=DataBackendMode.LOCAL,
            api_base_url="",
            api_username="",
            api_password="",
        )
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        assert (
            _button_label_plain(screen.query_one("#save-backend-btn", Button))
            == "Save [Ctrl+s]"
        )
        assert (
            _button_label_plain(screen.query_one("#cancel-backend-btn", Button))
            == "Cancel [Esc]"
        )
        save_action = mocker.patch.object(screen, "action_save")
        cancel_action = mocker.patch.object(screen, "action_cancel")

        await pilot.click("#save-backend-btn")
        await pilot.click("#cancel-backend-btn")

        save_action.assert_called_once_with()
        cancel_action.assert_called_once_with()
        await pilot.pause()

    invalid_screen = BackendConfigScreen(
        BackendConfig(
            mode=DataBackendMode.LOCAL,
            api_base_url="",
            api_username="",
            api_password="",
        )
    )
    invalid_app = _SingleScreenApp(invalid_screen)

    async with invalid_app.run_test() as pilot:
        notify = mocker.patch.object(invalid_screen, "notify")
        dismiss = mocker.patch.object(invalid_screen, "dismiss")
        bad_select = mocker.Mock(value="bad-mode")
        mocker.patch.object(
            invalid_screen,
            "query_one",
            return_value=bad_select,
        )

        invalid_screen.action_save()
        invalid_screen.action_cancel()

        notify.assert_called_once_with(
            "Select a backend mode",
            severity="error",
        )
        dismiss.assert_called_once_with(None)
        await pilot.pause()


@pytest.mark.asyncio
async def test_name_input_screen_button_routing(
    mocker: MockerFixture,
) -> None:
    """Name input modal buttons should route to save and cancel actions."""
    screen = NameInputScreen(
        title="Rename Group",
        initial_value="backend",
        placeholder="Group name...",
    )
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        assert (
            _button_label_plain(screen.query_one("#save-name-btn", Button))
            == "Save [Enter/Ctrl+s]"
        )
        assert (
            _button_label_plain(screen.query_one("#cancel-name-btn", Button))
            == "Cancel [Esc]"
        )
        save_action = mocker.patch.object(screen, "action_save")
        cancel_action = mocker.patch.object(screen, "action_cancel")

        await pilot.click("#save-name-btn")
        await pilot.click("#cancel-name-btn")

        save_action.assert_called_once_with()
        cancel_action.assert_called_once_with()
        await pilot.pause()


@pytest.mark.asyncio
async def test_confirm_dialog_buttons_size_to_content() -> None:
    """Confirm buttons should size to content with balanced padding."""
    confirm = ConfirmDialog("Are you sure?")
    app = _StyledSingleScreenApp(confirm)

    async with app.run_test() as pilot:
        expected_labels = {
            "#confirm-yes-btn": "Yes [Y]",
            "#confirm-no-btn": "No [N]",
        }
        for button_id, expected_label in expected_labels.items():
            button = confirm.query_one(button_id, Button)
            assert _button_label_plain(button) == expected_label
            leftover = button.region.width - len(expected_label)
            assert leftover % 2 == 0
            assert leftover >= 4

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

    name_input = NameInputScreen(
        title="Rename Group",
        initial_value="backend",
        placeholder="Group name...",
    )
    app_name = _SingleScreenApp(name_input)
    async with app_name.run_test() as pilot:
        dismiss = mocker.patch.object(name_input, "dismiss")
        name_input.action_cancel()
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
    assert "a                About" in help_screen.HELP_TEXT
    assert "Ctrl+a           Select all focused form text" in (
        help_screen.HELP_TEXT
    )
    assert "Escape           Cancel (confirm if edit is dirty)" in (
        help_screen.HELP_TEXT
    )
    app2 = _SingleScreenApp(help_screen)
    async with app2.run_test() as pilot:
        assert help_screen.query_one("#help-body", Static) is not None
        dismiss = mocker.patch.object(help_screen, "dismiss")
        help_screen.action_close()
        dismiss.assert_called_once_with(None)
        await pilot.pause()


@pytest.mark.asyncio
async def test_help_screen_scrolls_when_terminal_is_short() -> None:
    """Help modal should expose scrolling on constrained terminal heights."""
    help_screen = HelpScreen()
    app = _StyledSingleScreenApp(help_screen)

    async with app.run_test(size=(60, 10)) as pilot:
        await pilot.pause()
        content = help_screen.query_one("#help-content", VerticalScroll)
        assert content.max_scroll_y > 0


@pytest.mark.asyncio
async def test_about_screen_shows_metadata_and_closes(
    mocker: MockerFixture,
) -> None:
    """About modal should render metadata and dismiss cleanly."""
    about_screen = AboutScreen(
        AppMetadata(
            title="Cogitus",
            version="1.2.3",
            summary="Test summary",
            author="Grant Ramsay",
            project_urls={
                "Homepage": "https://example.com/docs",
                "Repository": "https://example.com/repo",
                "Issues": "https://example.com/issues",
            },
            license_name="MIT",
        ),
    )
    app = _StyledSingleScreenApp(about_screen)

    async with app.run_test() as pilot:
        title = about_screen.query_one("#about-title", Static)
        separator = about_screen.query_one("#about-separator", Rule)
        summary = about_screen.query_one("#about-summary", Static)
        metadata = about_screen.query_one("#about-metadata", Static)

        assert str(title.content) == "About Cogitus"
        assert separator.orientation == "horizontal"
        assert str(summary.content) == "Test summary"
        assert isinstance(metadata.content, Table)
        license_value = metadata.content.columns[1]._cells[-1]
        assert isinstance(license_value, Text)
        assert license_value.plain == "MIT"
        assert not license_value.spans

        dismiss = mocker.patch.object(about_screen, "dismiss")
        about_screen.action_close()
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

        # Routed button clicks cover both selector-based paths.
        save_action = mocker.patch.object(group_form, "action_save")
        cancel_action = mocker.patch.object(group_form, "action_cancel")
        await pilot.click("#save-group-btn")
        await pilot.click("#cancel-group-btn")
        save_action.assert_called_once()
        cancel_action.assert_called_once()
        await pilot.pause()

    reassign = GroupDeleteReassignScreen(
        "source",
        cast("list[tuple[str, int]]", [("bad", "x")]),
    )
    app_reassign = _SingleScreenApp(reassign)
    async with app_reassign.run_test() as pilot:
        assert (
            _button_label_plain(reassign.query_one("#move-delete-btn", Button))
            == "Move + Delete [Ctrl+s]"
        )
        assert (
            _button_label_plain(reassign.query_one("#cancel-move-btn", Button))
            == "Cancel [Esc]"
        )
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

        # Routed button clicks cover save/cancel dispatch.
        save_action = mocker.patch.object(reassign, "action_save")
        cancel_action = mocker.patch.object(reassign, "action_cancel")
        await pilot.click("#move-delete-btn")
        await pilot.click("#cancel-move-btn")
        save_action.assert_called_once()
        cancel_action.assert_called_once()
        await pilot.pause()


@pytest.mark.asyncio
async def test_group_form_creates_subgroup(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Subgroup form should save with the selected parent group."""
    parent = service.create_group("parent")
    subgroup_form = GroupFormScreen(
        service=service,
        parent_pk=parent.pk,
        show_parent_select=True,
    )
    app = _SingleScreenApp(subgroup_form)

    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(subgroup_form, "dismiss")

        subgroup_form.query_one("#group-name-input", Input).value = "child"
        subgroup_form.action_save()

        child = service.get_group(dismiss.call_args.args[0])
        assert child is not None
        assert child.parent_pk == parent.pk
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
            "search_results",
            return_value=[
                SearchResult(idea=first, score=-1.0, snippet="First")
            ],
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
        selected_view.assert_called_once_with(first, scroll_y=0)

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
        refresh.reset_mock()
        screen._on_form_saved(first.pk)
        refresh.assert_called_once_with(select_pk=first.pk)


@pytest.mark.asyncio
async def test_main_screen_rename_idea_actions(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Rename should open idea flow and handle empty selection branches."""
    first = service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        push = mocker.patch.object(app, "push_screen")
        notify = mocker.patch.object(screen, "notify")

        mocker.patch.object(panel, "get_selected_group_pk", return_value=None)
        mocker.patch.object(panel, "get_selected_idea", return_value=first)
        screen.action_rename_selected()
        assert isinstance(push.call_args.args[0], NameInputScreen)

        push.reset_mock()
        notify.reset_mock()
        mocker.patch.object(panel, "get_selected_idea", return_value=None)
        screen.action_rename_selected()
        notify.assert_called_with(
            "Nothing renameable selected",
            severity="warning",
        )
        push.assert_not_called()

        push.reset_mock()
        notify.reset_mock()
        mocker.patch.object(panel, "get_selected_idea", return_value=first)
        mocker.patch.object(screen._service, "get_idea", return_value=None)
        screen.action_rename_selected()
        notify.assert_called_with("Idea not found", severity="error")
        push.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_refresh_selects_group_when_requested(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Refresh should reselect group context when a group PK is requested."""
    backend = service.create_group("backend")
    idea = service.create_idea("Grouped", group_pk=backend.pk)
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        view = screen.query_one("#content-panel", IdeaView)

        select_group = mocker.patch.object(panel, "select_group")
        mocker.patch.object(
            screen._service,
            "list_ideas_grouped",
            return_value=[(backend, [idea])],
        )
        mocker.patch.object(panel, "get_selected_idea", return_value=None)
        show_empty = mocker.patch.object(view, "show_empty")

        screen.refresh_ideas(select_group_pk=backend.pk)

        select_group.assert_called_once_with(backend.pk)
        show_empty.assert_called_once_with()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_refresh_falls_back_to_group_when_idea_missing(
    service: IdeaService,
) -> None:
    """Missing idea restore should fall back to the requested group."""
    backend = service.create_group("backend")
    service.create_idea("Grouped", group_pk=backend.pk)
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        body = screen.query_one("#idea-view-body", Markdown)

        screen.refresh_ideas(select_pk=99999, select_group_pk=backend.pk)
        await pilot.pause()
        await pilot.pause()

        assert panel.get_selected_idea() is None
        assert panel.get_selected_group_pk() == backend.pk
        assert screen._selected_idea_pk is None
        assert "Select an idea from the list" in body.source


@pytest.mark.asyncio
async def test_main_screen_refresh_clears_selection_when_group_missing(
    service: IdeaService,
) -> None:
    """Missing group restore should leave both panes with no selection."""
    backend = service.create_group("backend")
    idea = service.create_idea("Grouped", group_pk=backend.pk)
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        body = screen.query_one("#idea-view-body", Markdown)

        assert panel.get_selected_idea() is not None
        assert screen._selected_idea_pk == idea.pk

        screen.refresh_ideas(select_group_pk=99999)
        await pilot.pause()
        await pilot.pause()

        assert panel.get_selected_idea() is None
        assert panel.get_selected_group_pk() is None
        assert screen._selected_idea_pk is None
        assert "Select an idea from the list" in body.source


@pytest.mark.asyncio
async def test_main_screen_refresh_selects_group_without_ideas(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Refresh should still reselect group context when list is empty."""
    backend = service.create_group("backend")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        view = screen.query_one("#content-panel", IdeaView)

        select_group = mocker.patch.object(panel, "select_group")
        mocker.patch.object(
            screen._service,
            "list_ideas_grouped",
            return_value=[(backend, [])],
        )
        set_selected = mocker.patch.object(screen, "_set_selected_idea")
        show_empty = mocker.patch.object(view, "show_empty")

        screen.refresh_ideas(select_group_pk=backend.pk)

        select_group.assert_called_once_with(backend.pk)
        set_selected.assert_called_once_with(None)
        show_empty.assert_called_once_with()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_refresh_empty_tree_clears_missing_group_request(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Empty refresh should clear selection if requested group is missing."""
    backend = service.create_group("backend")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        view = screen.query_one("#content-panel", IdeaView)

        select_group = mocker.patch.object(
            panel,
            "select_group",
            return_value=False,
        )
        mocker.patch.object(
            screen._service,
            "list_ideas_grouped",
            return_value=[(backend, [])],
        )
        set_selected = mocker.patch.object(screen, "_set_selected_idea")
        show_empty = mocker.patch.object(view, "show_empty")

        screen.refresh_ideas(select_group_pk=99999)

        select_group.assert_called_once_with(99999)
        set_selected.assert_called_once_with(None)
        show_empty.assert_called_once_with()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_focus_and_resume_refresh_relative_timestamps(
    service: IdeaService,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Focus/resume should refresh labels without reloading ideas."""
    base_time = datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc)
    _FrozenDateTime.current = base_time
    monkeypatch.setattr(datefmt_module, "datetime", _FrozenDateTime)

    service.create_idea("Fresh")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        idea = panel.get_selected_idea()
        assert idea is not None
        idea.updated_at = int(base_time.timestamp())

        panel.refresh_relative_timestamps()
        await pilot.pause()

        node = panel._idea_nodes_by_pk[idea.pk]
        assert isinstance(node.label, Text)
        assert node.label.plain == f"{idea.title} [just now]"

        refresh_ideas = mocker.patch.object(screen, "refresh_ideas")
        request_remote_sync = mocker.patch.object(
            screen,
            "_request_remote_sync",
        )

        _FrozenDateTime.current = base_time + timedelta(hours=2)
        screen.on_app_focus(events.AppFocus())
        await pilot.pause()
        assert node.label.plain == f"{idea.title} [2h ago]"

        _FrozenDateTime.current = base_time + timedelta(hours=3)
        screen.on_screen_resume(events.ScreenResume())
        await pilot.pause()
        assert node.label.plain == f"{idea.title} [3h ago]"

        refresh_ideas.assert_not_called()
        request_remote_sync.assert_not_called()


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
async def test_main_screen_new_subgroup_falls_back_to_default_group(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """New subgroup should use default group when nothing is selected."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)
    default = next(
        group
        for group in service.list_groups()
        if group.name == service.default_group_name
    )

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        push = mocker.patch.object(app, "push_screen")
        mocker.patch.object(panel, "get_selected_group_pk", return_value=None)
        mocker.patch.object(panel, "get_selected_idea", return_value=None)

        screen.action_new_subgroup()

        form = push.call_args.args[0]
        assert isinstance(form, GroupFormScreen)
        assert form._parent_pk == default.pk
        assert form._show_parent_select is True
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_new_subgroup_allows_missing_default_group(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """New subgroup should still open if the default group is missing."""
    backend = service.create_group("backend")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        push = mocker.patch.object(app, "push_screen")
        mocker.patch.object(panel, "get_selected_group_pk", return_value=None)
        mocker.patch.object(panel, "get_selected_idea", return_value=None)
        mocker.patch.object(service, "list_groups", return_value=[backend])

        screen.action_new_subgroup()

        form = push.call_args.args[0]
        assert isinstance(form, GroupFormScreen)
        assert form._parent_pk is None
        assert form._show_parent_select is True
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

        push.reset_mock()
        notify.reset_mock()
        mocker.patch.object(
            panel,
            "get_selected_group_pk",
            return_value=backend.pk,
        )
        screen.action_rename_selected()
        assert isinstance(push.call_args.args[0], NameInputScreen)

        default = next(
            group
            for group in service.list_groups()
            if group.name == service.default_group_name
        )
        push.reset_mock()
        notify.reset_mock()
        mocker.patch.object(
            panel,
            "get_selected_group_pk",
            return_value=default.pk,
        )
        screen.action_rename_selected()
        notify.assert_called_with(
            "Default group cannot be renamed",
            severity="warning",
        )
        push.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_delete_group_blocks_parent_groups(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Deleting a group with children should warn and leave it untouched."""
    parent = service.create_group("parent")
    service.create_group("child", parent_pk=parent.pk)
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        notify = mocker.patch.object(screen, "notify")
        push = mocker.patch.object(app, "push_screen")
        mocker.patch.object(
            panel,
            "get_selected_group_pk",
            return_value=parent.pk,
        )

        screen.action_delete_group()

        notify.assert_called_once_with(
            "Group with child groups cannot be deleted",
            severity="warning",
        )
        push.assert_not_called()
        assert service.get_group(parent.pk) is not None
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_rename_group_missing_selection(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Rename should error when a selected group PK no longer exists."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        notify = mocker.patch.object(screen, "notify")
        push = mocker.patch.object(app, "push_screen")

        mocker.patch.object(panel, "get_selected_group_pk", return_value=54321)
        screen.action_rename_selected()

        notify.assert_called_with("Group not found", severity="error")
        push.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_refresh_empty_selection_branch(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Search refresh should preview empty state without clearing selection."""
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
            "search_results",
            wraps=screen._service.search_results,
        )

        search.value = "First"
        list_grouped.reset_mock()
        screen.refresh_ideas()

        list_grouped.assert_called_once_with("First")
        set_selected.assert_not_called()
        show_empty.assert_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_refresh_with_ideas_and_no_selected_idea(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Normal refresh should clear selection when ideas load without cursor."""
    first = service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        view = screen.query_one("#content-panel", IdeaView)
        set_selected = mocker.patch.object(screen, "_set_selected_idea")
        show_empty = mocker.patch.object(view, "show_empty")

        mocker.patch.object(
            screen._service,
            "list_ideas_grouped",
            return_value=[(first.group, [first])],
        )
        mocker.patch.object(panel, "get_selected_idea", return_value=None)

        screen.refresh_ideas()

        set_selected.assert_called_once_with(None)
        show_empty.assert_called_once_with()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_refresh_reuses_selected_idea_pk_in_grouped_mode(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """No-arg refresh should reuse committed idea selection in tree mode."""
    first = service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        screen._selected_idea_pk = first.pk
        refresh_grouped = mocker.patch.object(screen, "_refresh_grouped_ideas")

        screen.refresh_ideas()

        refresh_grouped.assert_called_once()
        assert refresh_grouped.call_args.kwargs["select_pk"] == first.pk
        assert refresh_grouped.call_args.kwargs["select_group_pk"] is None
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_refresh_reuses_selected_idea_pk_in_search_mode(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Search refresh should not force committed tree selection into results."""
    first = service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        search.value = "First"
        screen._selected_idea_pk = first.pk
        refresh_search = mocker.patch.object(screen, "_refresh_search_results")

        screen.refresh_ideas()

        refresh_search.assert_called_once()
        assert refresh_search.call_args.kwargs["search_query"] == "First"
        assert refresh_search.call_args.kwargs["select_pk"] is None
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_refresh_defers_pending_whitespace_clear(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Refresh should not leave search mode before a clear debounce lands."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)

        search.value = "   "
        refresh_search = mocker.patch.object(screen, "_refresh_search_results")
        refresh_grouped = mocker.patch.object(screen, "_refresh_grouped_ideas")

        screen.refresh_ideas()

        refresh_search.assert_not_called()
        refresh_grouped.assert_not_called()
        assert panel.search_is_active() is True
        await pilot.pause()


def _main_screen_callback_test_context(
    mocker: MockerFixture,
) -> tuple[MainScreen, Any, Any, Any]:
    """Return a screen with mocked service and common assertions hooks."""
    # These callbacks are intentionally exercised without mounting the screen.
    # If callbacks start querying widgets, this test should be converted to
    # a mounted async screen test.
    service = mocker.Mock()
    screen = MainScreen(service)
    service_mock = mocker.Mock()
    screen._service = service_mock
    notify = mocker.patch.object(screen, "notify")
    refresh = mocker.patch.object(screen, "refresh_ideas")
    return screen, service_mock, notify, refresh


def test_main_screen_group_form_and_delete_callbacks(
    mocker: MockerFixture,
) -> None:
    """Group create/delete callbacks should handle success and errors."""
    screen, service_mock, notify, refresh = _main_screen_callback_test_context(
        mocker
    )

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


def test_main_screen_group_reassign_and_rename_callbacks(
    mocker: MockerFixture,
) -> None:
    """Group rename and move/delete callbacks should refresh correctly."""
    screen, service_mock, notify, refresh = _main_screen_callback_test_context(
        mocker
    )

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

    # group rename
    notify.reset_mock()
    refresh.reset_mock()
    screen._on_group_rename_dismiss(1, None)
    notify.assert_not_called()
    refresh.assert_not_called()

    notify.reset_mock()
    refresh.reset_mock()
    renamed_group = mocker.Mock()
    renamed_group.pk = 3
    service_mock.rename_group.return_value = renamed_group
    screen._on_group_rename_dismiss(1, "renamed")
    service_mock.rename_group.assert_called_once_with(1, "renamed")
    notify.assert_called_with("Group renamed")
    refresh.assert_called_once_with(select_group_pk=3)

    notify.reset_mock()
    refresh.reset_mock()
    service_mock.rename_group.reset_mock()
    service_mock.rename_group.return_value = None
    screen._on_group_rename_dismiss(1, "missing")
    notify.assert_called_with("Group not found", severity="error")
    refresh.assert_not_called()

    notify.reset_mock()
    refresh.reset_mock()
    service_mock.rename_group.reset_mock()
    service_mock.rename_group.side_effect = ValueError("bad rename")
    screen._on_group_rename_dismiss(1, "bad")
    notify.assert_called_with("bad rename", severity="error")
    refresh.assert_not_called()


def test_main_screen_idea_rename_callbacks(
    mocker: MockerFixture,
) -> None:
    """Idea rename callback should cover cancel, success, and errors."""
    screen, service_mock, notify, refresh = _main_screen_callback_test_context(
        mocker
    )

    # idea rename
    notify.reset_mock()
    refresh.reset_mock()
    screen._on_idea_rename_dismiss(1, None)
    notify.assert_not_called()
    refresh.assert_not_called()

    notify.reset_mock()
    refresh.reset_mock()
    renamed_idea = mocker.Mock()
    renamed_idea.pk = 4
    service_mock.rename_idea.return_value = renamed_idea
    screen._on_idea_rename_dismiss(1, "renamed idea")
    service_mock.rename_idea.assert_called_once_with(1, "renamed idea")
    notify.assert_called_with("Idea renamed")
    refresh.assert_called_once_with(select_pk=4)

    notify.reset_mock()
    refresh.reset_mock()
    service_mock.rename_idea.reset_mock()
    service_mock.rename_idea.return_value = None
    screen._on_idea_rename_dismiss(1, "missing")
    notify.assert_called_with("Idea not found", severity="error")
    refresh.assert_not_called()

    notify.reset_mock()
    refresh.reset_mock()
    service_mock.rename_idea.reset_mock()
    service_mock.rename_idea.side_effect = ValueError("bad rename")
    screen._on_idea_rename_dismiss(1, "bad")
    notify.assert_called_with("bad rename", severity="error")
    refresh.assert_not_called()


@pytest.mark.asyncio
async def test_main_screen_focus_toggle_help_quit_and_callback(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Main screen should handle focus, help, about, quit, and callbacks."""
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
        push.reset_mock()
        screen.action_show_about()
        push.assert_called_once()

        panel.query_one("#idea-list", Tree).focus()
        await pilot.pause()

        content_focus = mocker.patch.object(view, "focus_content")
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
async def test_main_screen_footer_shows_switch_pane_binding(
    service: IdeaService,
) -> None:
    """Default footer should expose pane-switch and About hints."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        await pilot.pause()
        bindings = screen.active_bindings
        assert bindings["a"].binding.description == "About"
        assert bindings["tab"].binding.description == "Switch Pane"


@pytest.mark.asyncio
async def test_main_screen_footer_hides_backend_settings_binding(
    service: IdeaService,
) -> None:
    """Settings should stay off the visible footer bindings."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert screen.active_bindings["c"].binding.show is False


@pytest.mark.asyncio
async def test_main_screen_footer_shows_cached_remote_warning(
    service: IdeaService,
) -> None:
    """Cached remote mode should show warning without blanking bindings."""
    screen = MainScreen(service)
    app = _StyledSingleScreenApp(screen)

    async with app.run_test() as pilot:
        service.create_idea("Seed")
        await pilot.pause()

        screen._set_remote_cached_read_only(read_only=True)
        await pilot.pause()

        footer = screen.query_one(CogitusStatusBar)
        warning = screen.query_one("#footer-cache-warning", FooterNotice)
        bindings_footer = screen.query_one("#bindings-footer", Footer)

        assert footer.show_cache_warning is True
        assert warning.description == "READ-ONLY CACHE"
        assert warning.region.width >= len("READ-ONLY CACHE") + 2
        assert warning.display is True
        assert bindings_footer.display is True
        assert any(
            child.__class__.__name__ == "FooterKey"
            for child in bindings_footer.children
        )


def test_cogitus_status_bar_handles_disabled_command_palette(
    mocker: MockerFixture,
) -> None:
    """Status bar should omit the palette hint when the app disables it."""
    status_bar = CogitusStatusBar()
    fake_app = mocker.Mock(ENABLE_COMMAND_PALETTE=False)
    mocker.patch.object(
        type(status_bar),
        "app",
        new_callable=PropertyMock,
        return_value=fake_app,
    )

    assert status_bar._build_palette_hint() is None


def test_cogitus_status_bar_handles_missing_palette_binding(
    mocker: MockerFixture,
) -> None:
    """Status bar should omit the palette hint when no binding is active."""
    status_bar = CogitusStatusBar()
    fake_app = mocker.Mock(
        ENABLE_COMMAND_PALETTE=True,
        COMMAND_PALETTE_BINDING="ctrl+p",
    )
    fake_screen = mocker.Mock(active_bindings={})
    mocker.patch.object(
        type(status_bar),
        "app",
        new_callable=PropertyMock,
        return_value=fake_app,
    )
    mocker.patch.object(
        type(status_bar),
        "screen",
        new_callable=PropertyMock,
        return_value=fake_screen,
    )

    assert status_bar._build_palette_hint() is None


@pytest.mark.asyncio
async def test_main_screen_search_mode_hides_switch_pane_binding(
    service: IdeaService,
) -> None:
    """Search input focus should hide the normal pane-switch footer hint."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)

        screen.action_focus_search()
        await pilot.pause()

        bindings = screen.active_bindings
        assert "tab" not in bindings
        assert "slash" not in bindings
        assert bindings["escape"].binding.description == "Exit Search"
        assert {
            binding.binding.description for binding in bindings.values()
        } == {"Exit Search"}

        search.value = "First"
        await _wait_for_search_active(pilot, search)
        bindings = screen.active_bindings
        assert "tab" not in bindings


@pytest.mark.asyncio
async def test_main_screen_search_ctrl_a_selects_query_and_closes_autocomplete(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Ctrl+a should select all search text and close suggestions."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        autocomplete = panel.query_one("#search-autocomplete", OptionList)

        screen.action_focus_search()
        search.focus()
        await pilot.pause()
        search.value = "tag:python"
        search.cursor_position = len(search.value)
        autocomplete.set_options(["tag:python"])
        autocomplete.remove_class("-hidden")

        event = mocker.Mock()
        event.key = "ctrl+a"
        panel._handle_search_input_key(cast("events.Key", event))
        assert search.selected_text == "tag:python"
        assert autocomplete.has_class("-hidden")

        search.cursor_position = len(search.value)
        autocomplete.set_options(["tag:python"])
        autocomplete.remove_class("-hidden")

        await pilot.press("ctrl+a")
        await pilot.pause()

        assert search.selected_text == "tag:python"
        assert autocomplete.has_class("-hidden")


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
        focused = _focused_widget(app)
        assert focused is tree


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
        view_container = content.query_one("#idea-view-container")
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
        assert app.focused is view_container

        screen._active_pane = "list"
        screen.action_focus_search()
        await pilot.pause()
        assert app.focused is search
        search.value = "xyz"
        screen.action_cancel_search()
        await pilot.pause()
        assert search.value == ""
        focused = _focused_widget(app)
        assert focused is tree


@pytest.mark.asyncio
async def test_main_screen_search_by_tag_preserves_previous_focus(
    service: IdeaService,
) -> None:
    """Tag-click searches should restore the pre-search content focus."""
    service.create_idea("Tagged", tags=["python"])
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        content = screen.query_one("#content-panel", IdeaView)
        view_container = content.query_one("#idea-view-container")
        search = panel.query_one("#search-input", Input)

        screen._active_pane = "content"
        content.focus_content()
        await pilot.pause()

        screen.action_search_by_tag("python")
        await pilot.pause()
        assert app.focused is search

        screen.action_cancel_search()
        await pilot.pause()
        assert search.value == ""
        assert app.focused is view_container


@pytest.mark.asyncio
async def test_main_screen_cancel_search_noop_when_search_not_focused(
    service: IdeaService,
) -> None:
    """Esc on tree should return to search first when search is active."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        search.value = "keep"
        await _wait_for_search_active(pilot, search)
        results.focus()
        await pilot.pause()
        screen.action_cancel_search()
        await pilot.pause()

        assert search.value == "keep"
        assert app.focused is search


@pytest.mark.asyncio
async def test_main_screen_cancel_search_ignores_non_search_focus(
    service: IdeaService,
) -> None:
    """Esc should no-op when neither search nor results currently have focus."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        content = screen.query_one("#content-panel", IdeaView)
        view_container = content.query_one("#idea-view-container")

        search.value = "keep"
        content.focus_content()
        await pilot.pause()

        screen.action_cancel_search()
        await pilot.pause()

        assert search.value == "keep"
        assert app.focused is view_container


@pytest.mark.asyncio
async def test_main_screen_search_results_support_keyboard_navigation(
    service: IdeaService,
) -> None:
    """Active search should move between input and results via keyboard."""
    service.create_idea("Alpha python")
    service.create_idea("Beta python")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        screen.action_focus_search()
        await pilot.pause()
        search.value = "python"
        await _wait_for_search_results(pilot, search, results)
        bindings = screen.active_bindings
        assert bindings["down"].binding.description == "Results"
        assert bindings["escape"].binding.description == "Exit Search"
        assert {
            binding.binding.description for binding in bindings.values()
        } == {"Results", "Exit Search"}

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is results
        assert search.value == "python"
        bindings = screen.active_bindings
        assert bindings["down"].binding.description == "Next Result"
        assert bindings["escape"].binding.description == "Back to Search"
        assert bindings["up"].binding.description == "Search"
        assert {
            binding.binding.description for binding in bindings.values()
        } == {"Next Result", "Search", "Back to Search"}

        screen.action_cancel_search()
        await pilot.pause()
        focused = _focused_widget(app)
        assert focused is search
        assert search.value == "python"

        screen.action_cancel_search()
        await _wait_for_search_cleared(pilot, search)
        assert app.focused is panel.browse_widget()
        assert search.value == ""


@pytest.mark.asyncio
async def test_main_screen_cancel_search_preserves_selected_idea(
    service: IdeaService,
) -> None:
    """Leaving search should keep the selected idea in the normal tree."""
    service.create_idea("Alpha python")
    service.create_idea("Beta python")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        screen.action_focus_search()
        await pilot.pause()
        search.value = "python"
        await _wait_for_search_results(pilot, search, results)

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is results
        for _ in range(_MAX_WAIT_TICKS):
            if not panel.is_first_result_selected():
                break
            await pilot.press("down")
            await pilot.pause()
        else:
            pytest.fail("Timed out moving away from first search result")

        selected_in_search = panel.get_selected_idea()
        assert selected_in_search is not None

        screen.action_cancel_search()
        await pilot.pause()
        screen.action_cancel_search()
        await _wait_for_search_cleared(pilot, search)
        for _ in range(_MAX_WAIT_TICKS):
            if panel.get_selected_idea() is not None:
                break
            await pilot.pause()
        else:
            pytest.fail("Timed out waiting for tree selection to be restored")

        assert app.focused is panel.browse_widget()
        selected_in_tree = panel.get_selected_idea()
        assert selected_in_tree is not None
        assert selected_in_tree.pk == selected_in_search.pk


@pytest.mark.asyncio
async def test_main_screen_search_cancel_keeps_selection_without_navigation(
    service: IdeaService,
) -> None:
    """Typing in search without entering results should not commit a hit."""
    first = service.create_idea("Alpha keep selected")
    service.create_idea("Beta python")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        panel.select_idea(first.pk)
        screen._set_selected_idea(first.pk)
        await pilot.pause()
        selected_before_search = panel.get_selected_idea()
        assert selected_before_search is not None
        assert selected_before_search.pk == first.pk

        screen.action_focus_search()
        await pilot.pause()
        search.value = "python"
        await _wait_for_search_results(pilot, search, results)

        assert app.focused is search
        selected_in_preview = panel.get_selected_idea()
        assert selected_in_preview is not None
        assert selected_in_preview.title == "Beta python"

        screen.action_cancel_search()
        await _wait_for_search_cleared(pilot, search)

        for _ in range(_MAX_WAIT_TICKS):
            if panel.get_selected_idea() is not None:
                break
            await pilot.pause()
        else:
            pytest.fail("Timed out waiting for tree selection to be restored")

        assert app.focused is panel.browse_widget()
        selected_in_tree = panel.get_selected_idea()
        assert selected_in_tree is not None
        assert selected_in_tree.pk == first.pk


@pytest.mark.asyncio
async def test_main_screen_search_refresh_keeps_committed_selection(
    service: IdeaService,
) -> None:
    """Refreshing active search should not commit the previewed first hit."""
    first = service.create_idea("Alpha keep selected")
    service.create_idea("Beta python")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        panel.select_idea(first.pk)
        screen._set_selected_idea(first.pk)
        await pilot.pause()

        screen.action_focus_search()
        await pilot.pause()
        search.value = "python"
        await _wait_for_search_results(pilot, search, results)

        screen.refresh_ideas()

        assert screen._selected_idea_pk == first.pk
        preview_selected = panel.get_selected_idea()
        assert preview_selected is not None
        assert preview_selected.title == "Beta python"

        screen.action_cancel_search()
        await _wait_for_search_cleared(pilot, search)
        for _ in range(_MAX_WAIT_TICKS):
            if panel.get_selected_idea() is not None:
                break
            await pilot.pause()
        else:
            pytest.fail("Timed out waiting for tree selection to be restored")

        selected_in_tree = panel.get_selected_idea()
        assert selected_in_tree is not None
        assert selected_in_tree.pk == first.pk


@pytest.mark.asyncio
async def test_main_screen_search_refresh_select_pk_commits_selected_hit(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Search refresh with `select_pk` should commit the matching result."""
    idea = service.create_idea("Commit python")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)
        view = screen.query_one("#content-panel", IdeaView)
        set_selected = mocker.patch.object(screen, "_set_selected_idea")
        show_idea = mocker.patch.object(view, "show_idea")
        selected_pks: list[int] = []

        def fake_select_idea(pk: int) -> bool:
            selected_pks.append(pk)
            return True

        search.value = "python"
        await _wait_for_search_results(pilot, search, results)
        mocker.patch.object(panel, "select_idea", side_effect=fake_select_idea)
        mocker.patch.object(panel, "get_selected_idea", return_value=idea)
        set_selected.reset_mock()
        show_idea.reset_mock()

        screen.refresh_ideas(select_pk=idea.pk)

        assert selected_pks == [idea.pk]
        set_selected.assert_called_once_with(idea.pk)
        show_idea.assert_called_once_with(idea, scroll_y=0)


@pytest.mark.asyncio
async def test_main_screen_search_refresh_ignores_non_matching_select_pk(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Search refresh should not commit selection for absent `select_pk`."""
    matching = service.create_idea("Match python")
    missing = service.create_idea("Missing rust")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)
        view = screen.query_one("#content-panel", IdeaView)
        set_selected = mocker.patch.object(screen, "_set_selected_idea")
        show_idea = mocker.patch.object(view, "show_idea")
        selected_pks: list[int] = []

        def fake_select_idea(pk: int) -> bool:
            selected_pks.append(pk)
            return True

        search.value = "python"
        await _wait_for_search_results(pilot, search, results)
        mocker.patch.object(panel, "select_idea", side_effect=fake_select_idea)
        mocker.patch.object(panel, "get_selected_idea", return_value=matching)
        set_selected.reset_mock()
        show_idea.reset_mock()

        screen.refresh_ideas(select_pk=missing.pk)

        assert selected_pks == []
        set_selected.assert_not_called()
        show_idea.assert_called_once_with(matching)


@pytest.mark.asyncio
async def test_main_screen_search_preview_commit_empty_state(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Committed empty preview should clear selected idea state."""
    service.create_idea("First")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        view = screen.query_one("#content-panel", IdeaView)
        set_selected = mocker.patch.object(screen, "_set_selected_idea")
        show_empty = mocker.patch.object(view, "show_empty")

        mocker.patch.object(panel, "get_selected_idea", return_value=None)

        screen._show_search_selection_preview(
            panel,
            commit_selection=True,
        )

        set_selected.assert_called_once_with(None)
        show_empty.assert_called_once_with()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_search_clear_reselects_previous_idea(
    service: IdeaService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clearing search should reselect the previously active idea."""
    idea = service.create_idea("Keep selected")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test():
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        selected_pks: list[int] = []

        def fake_select_idea(pk: int) -> bool:
            selected_pks.append(pk)
            return True

        screen._selected_idea_pk = idea.pk
        monkeypatch.setattr(
            panel,
            "select_idea",
            fake_select_idea,
        )

        screen.on_idea_list_panel_search_changed(
            IdeaListPanel.SearchChanged("")
        )

        assert selected_pks == [idea.pk]


@pytest.mark.asyncio
async def test_main_screen_tag_only_search_uses_selectable_idea_rows(
    service: IdeaService,
) -> None:
    """Tag-only search should show idea rows without fragment children."""
    tagged = service.create_idea("Tagged python", tags=["python"])
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        screen.action_focus_search()
        await pilot.pause()
        search.value = "tag:python"
        await _wait_for_search_results(pilot, search, results)
        panel.dismiss_autocomplete()
        await pilot.pause()

        assert len(results.options) == 1
        assert results.options[0].id == f"idea-{tagged.pk}"
        await pilot.press("down")
        await pilot.pause()
        assert app.focused is results
        selected = panel.get_selected_idea()
        assert selected is not None
        assert selected.pk == tagged.pk


@pytest.mark.asyncio
async def test_main_screen_search_results_footer_uses_prev_result_for_non_first(
    service: IdeaService,
) -> None:
    """`Up` should read as `Prev Result` when a non-first result is selected."""
    service.create_idea("Alpha footerprev")
    service.create_idea("Beta footerprev")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        screen.action_focus_search()
        await pilot.pause()
        search.value = "footerprev"
        await _wait_for_search_results(pilot, search, results)

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is results

        for _ in range(_MAX_WAIT_TICKS):
            if not panel.is_first_result_selected():
                break
            assert panel._adjacent_result_node(1) is not None
            await pilot.press("down")
            await pilot.pause()
        else:
            pytest.fail("Timed out moving away from first search result")

        bindings = screen.active_bindings
        assert bindings["up"].binding.description == "Prev Result"


@pytest.mark.asyncio
async def test_main_screen_search_results_footer_hides_down_on_last_result(
    service: IdeaService,
) -> None:
    """Last search result should hide the `Down` footer hint."""
    service.create_idea("Alpha footerlast")
    service.create_idea("Beta footerlast")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        screen.action_focus_search()
        await pilot.pause()
        search.value = "footerlast"
        await _wait_for_search_results(pilot, search, results)

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is results
        for _ in range(_MAX_WAIT_TICKS):
            if panel._adjacent_result_node(1) is None:
                break
            await pilot.press("down")
            await pilot.pause()
        else:
            pytest.fail("Timed out reaching final search result")

        bindings = screen.active_bindings
        assert "down" not in bindings
        assert {
            binding.binding.description for binding in bindings.values()
        } == {"Prev Result", "Back to Search"}


@pytest.mark.asyncio
async def test_main_screen_search_input_disables_non_search_actions(
    service: IdeaService,
) -> None:
    """Search input should disable edit/copy and structural bindings."""
    service.create_idea("Alpha searchinput")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)

        screen.action_focus_search()
        await pilot.pause()
        search.value = "searchinput"
        await pilot.pause()

        for action in (
            "new_idea",
            "new_group",
            "new_subgroup",
            "delete_group",
            "delete_idea",
            "edit_idea",
            "rename_selected",
            "copy_idea_body",
        ):
            assert screen.check_action(action, ()) is False


@pytest.mark.asyncio
async def test_main_screen_can_rename_selection_false_when_search_focused(
    service: IdeaService,
) -> None:
    """Direct rename helper should return False while search has focus."""
    service.create_idea("Alpha")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        screen.action_focus_search()
        await pilot.pause()

        assert screen._can_rename_selection() is False


@pytest.mark.asyncio
async def test_main_screen_can_rename_selection_false_for_default_group(
    service: IdeaService,
) -> None:
    """Default-group selection should not advertise rename availability."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        default = next(
            group
            for group in service.list_groups()
            if group.name == service.default_group_name
        )
        assert panel.select_group(default.pk) is True
        await pilot.pause()

        assert screen._can_rename_selection() is False
        assert screen.check_action("rename_selected", ()) is False


@pytest.mark.asyncio
async def test_main_screen_search_results_disable_structural_actions_only(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Search results should block structural keys but keep edit/copy."""
    service.create_idea("Alpha actiongate")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        screen.action_focus_search()
        await pilot.pause()
        search.value = "actiongate"
        await _wait_for_search_results(pilot, search, results)
        await pilot.press("down")
        await pilot.pause()
        assert app.focused is results

        for action in (
            "new_idea",
            "new_group",
            "new_subgroup",
            "delete_group",
            "delete_idea",
        ):
            assert screen.check_action(action, ()) is False
        assert screen.check_action("edit_idea", ()) is True
        assert screen.check_action("rename_selected", ()) is True
        assert screen.check_action("copy_idea_body", ()) is True

        new_idea = mocker.patch.object(screen, "action_new_idea")
        delete_idea = mocker.patch.object(screen, "action_delete_idea")
        edit_idea = mocker.patch.object(screen, "action_edit_idea")
        rename_selected = mocker.patch.object(screen, "action_rename_selected")
        copy_idea_body = mocker.patch.object(screen, "action_copy_idea_body")

        await pilot.press("n", "d", "e", "r", "y")
        await pilot.pause()

        new_idea.assert_not_called()
        delete_idea.assert_not_called()
        edit_idea.assert_called_once_with()
        rename_selected.assert_called_once_with()
        copy_idea_body.assert_called_once_with()


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

        content_focus = mocker.patch.object(content, "focus_content")
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
async def test_main_screen_toggle_focus_commits_search_result_selection(
    service: IdeaService,
) -> None:
    """Returning to the list during search should sync result selection."""
    first = service.create_idea("Alpha keep selected")
    service.create_idea("Beta python")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)
        content = screen.query_one("#content-panel", IdeaView)

        panel.select_idea(first.pk)
        screen._set_selected_idea(first.pk)
        await pilot.pause()

        screen.action_focus_search()
        await pilot.pause()
        search.value = "python"
        await _wait_for_search_results(pilot, search, results)

        content.focus_content()
        await pilot.pause()
        screen.action_toggle_focus()
        await pilot.pause()

        assert app.focused is results
        selected_in_results = panel.get_selected_idea()
        assert selected_in_results is not None
        assert screen._selected_idea_pk == selected_in_results.pk


@pytest.mark.asyncio
async def test_main_screen_toggle_list_panel_empty_search_focuses_input(
    service: IdeaService,
) -> None:
    """Expanding empty search results should focus the search input."""
    service.create_idea("Alpha keep selected")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        content = screen.query_one("#content-panel", IdeaView)
        view_container = content.query_one("#idea-view-container")

        screen.action_focus_search()
        await pilot.pause()
        search.value = "no-match"
        await pilot.pause()

        screen.action_toggle_list_panel()
        await pilot.pause()
        assert panel.has_class("collapsed")
        assert app.focused is view_container

        screen.action_toggle_list_panel()
        await pilot.pause()
        assert not panel.has_class("collapsed")
        assert app.focused is search


@pytest.mark.asyncio
async def test_main_screen_tab_from_tree_focuses_content_scroll_container(
    service: IdeaService,
) -> None:
    """Tab from the tree should focus the scrollable content pane."""
    service.create_idea("First", body="\n".join(f"Line {i}" for i in range(60)))
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        tree = panel.query_one("#idea-list", Tree)
        view = screen.query_one("#content-panel", IdeaView)
        view_container = view.query_one("#idea-view-container")

        tree.focus()
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()

        assert app.focused is view_container
        assert view.has_focus_within


@pytest.mark.asyncio
async def test_main_screen_content_focus_scrolls_markdown(
    service: IdeaService,
) -> None:
    """Focused content pane should respond to keyboard scrolling."""
    service.create_idea("First", body="\n".join(f"Line {i}" for i in range(80)))
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        tree = panel.query_one("#idea-list", Tree)
        view = screen.query_one("#content-panel", IdeaView)
        view_container = view.query_one("#idea-view-container")

        tree.focus()
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()

        start_scroll = view_container.scroll_y
        await pilot.press("down")
        await pilot.pause()

        assert app.focused is view_container
        assert view_container.scroll_y > start_scroll


@pytest.mark.asyncio
async def test_main_screen_restores_saved_idea_scroll_position(
    service: IdeaService,
) -> None:
    """Returning to an idea should restore its rendered-pane scroll."""
    first = service.create_idea(
        "First",
        body="\n".join(f"Line {i}" for i in range(100)),
    )
    second = service.create_idea("Second", body="Short body")
    screen = MainScreen(service, initial_select_pk=first.pk)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        view = screen.query_one("#content-panel", IdeaView)
        view_container = view.query_one("#idea-view-container", VerticalScroll)
        await _wait_for_scrollable(pilot, view_container)

        saved_scroll_y = await _scroll_content_down(
            pilot,
            view,
            view_container,
        )

        screen.on_idea_list_panel_idea_selected(
            IdeaListPanel.IdeaSelected(second)
        )
        await _wait_for_scroll_y(pilot, view_container, 0)
        first_hash = service.get_idea(first.pk)
        assert first_hash is not None
        assert (
            service.get_idea_scroll_position(
                first.pk,
                first_hash.detail_hash,
            )
            == saved_scroll_y
        )

        screen.on_idea_list_panel_idea_selected(
            IdeaListPanel.IdeaSelected(first)
        )
        await _wait_for_scroll_y(pilot, view_container, saved_scroll_y)


@pytest.mark.asyncio
async def test_main_screen_scroll_restore_can_be_disabled(
    service: IdeaService,
) -> None:
    """Disabled scroll preservation should leave ideas starting at top."""
    first = service.create_idea(
        "First",
        body="\n".join(f"Line {i}" for i in range(100)),
    )
    second = service.create_idea("Second", body="Short body")
    screen = MainScreen(
        service,
        initial_select_pk=first.pk,
    )
    app = _ScrollConfigSingleScreenApp(
        screen,
        save_idea_scroll_pos=False,
    )

    async with app.run_test() as pilot:
        view = screen.query_one("#content-panel", IdeaView)
        view_container = view.query_one("#idea-view-container", VerticalScroll)
        await _wait_for_scrollable(pilot, view_container)

        await _scroll_content_down(pilot, view, view_container)

        screen.on_idea_list_panel_idea_selected(
            IdeaListPanel.IdeaSelected(second)
        )
        await _wait_for_scroll_y(pilot, view_container, 0)
        first_hash = service.get_idea(first.pk)
        assert first_hash is not None
        assert (
            service.get_idea_scroll_position(
                first.pk,
                first_hash.detail_hash,
            )
            is None
        )

        screen.on_idea_list_panel_idea_selected(
            IdeaListPanel.IdeaSelected(first)
        )
        await _wait_for_scroll_y(pilot, view_container, 0)


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
async def test_cogitus_app_exit_flushes_current_idea_scroll(
    db: SqliterDB,
) -> None:
    """App exit should persist scroll for the currently displayed idea."""
    service = IdeaService(db)
    idea = service.create_idea(
        "Scrollable",
        body="\n".join(f"Line {i}" for i in range(100)),
    )
    app = CogitusApp(
        db=db,
        settings=_FakeSettings(last_viewed_idea_pk=idea.pk),
    )

    async with app.run_test() as pilot:
        view = app.screen.query_one("#content-panel", IdeaView)
        view_container = view.query_one("#idea-view-container", VerticalScroll)
        await _wait_for_scrollable(pilot, view_container)

        saved_scroll_y = await _scroll_content_down(
            pilot,
            view,
            view_container,
        )
        app.exit()
        await pilot.pause()

    saved_idea = service.get_idea(idea.pk)
    assert saved_idea is not None
    assert (
        service.get_idea_scroll_position(idea.pk, saved_idea.detail_hash)
        == saved_scroll_y
    )


def test_main_screen_flush_idea_scroll_position_ignores_unmounted(
    service: IdeaService,
) -> None:
    """Unmounted screens should ignore explicit scroll flush requests."""
    MainScreen(service).flush_idea_scroll_position()


@pytest.mark.asyncio
async def test_cogitus_app_backend_settings_palette_and_shortcut(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Palette command and hidden shortcut should both open settings."""
    app = CogitusApp(db=db, settings=_FakeSettings())

    async with app.run_test() as pilot:
        assert isinstance(app.screen, MainScreen)
        push_screen = mocker.patch.object(app, "push_screen")

        commands = list(app.get_system_commands(app.screen))
        backend_command = next(
            command
            for command in commands
            if command.title == "Backend settings"
        )
        assert backend_command.help == (
            "Configure the local or remote data backend"
        )

        backend_command.callback()
        assert isinstance(push_screen.call_args.args[0], BackendConfigScreen)

        push_screen.reset_mock()
        await pilot.press("c")
        assert isinstance(push_screen.call_args.args[0], BackendConfigScreen)

        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_clone_remote_palette_command(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Palette should expose the remote-to-local clone action."""
    app = CogitusApp(db=db, settings=_FakeSettings())

    async with app.run_test() as pilot:
        assert isinstance(app.screen, MainScreen)
        clone_action = cast(
            "Any",
            mocker.patch.object(
                app.screen,
                "action_clone_remote_to_local",
            ),
        )

        commands = list(app.get_system_commands(app.screen))
        clone_command = next(
            command
            for command in commands
            if command.title == "Clone Remote To Local"
        )
        assert clone_command.help == (
            "Overwrite the local database with a fresh remote snapshot"
        )

        clone_command.callback()
        clone_action.assert_called_once()

        app.exit()
        await pilot.pause()


def test_clone_remote_to_local_uses_default_local_target_in_api_mode(
    mocker: MockerFixture,
) -> None:
    """Remote-mode clone should import into the normal local DB path."""
    cache_db = get_db(memory=True)
    target_db = get_db(memory=True)
    client = mocker.Mock()
    client.fetch_snapshot.return_value = mocker.sentinel.snapshot
    remote_client_cls = mocker.patch(
        "cogitus.app.RemoteAPIClient",
        return_value=client,
    )
    get_db_mock = mocker.patch(
        "cogitus.app.get_db",
        side_effect=[cache_db, target_db],
    )
    importer = mocker.Mock()
    importer_cls = mocker.patch(
        "cogitus.app.SnapshotImportRepository",
        return_value=importer,
    )
    close_cache_db = mocker.spy(cache_db, "close")
    close_target_db = mocker.spy(target_db, "close")
    progress_updates: list[tuple[str, int, int]] = []
    app = CogitusApp(
        settings=_FakeSettings(
            backend_config=BackendConfig(
                mode=DataBackendMode.API,
                api_base_url="http://127.0.0.1:8000",
                api_username="api-user",
                api_password=_remote_secret(),
            )
        )
    )
    remote_client_cls.reset_mock()
    get_db_mock.reset_mock()

    app.clone_remote_to_local(
        progress_callback=lambda progress: progress_updates.append(
            (progress.stage, progress.completed, progress.total)
        )
    )

    remote_client_cls.assert_called_once()
    get_db_mock.assert_called_with(
        "~/.config/cogitus/cogitus.db",
        default_group_name="default",
    )
    importer_cls.assert_called_once_with(target_db)
    importer.replace_snapshot.assert_called_once_with(
        mocker.sentinel.snapshot,
        progress_callback=mocker.ANY,
    )
    assert progress_updates[:2] == [
        ("Download", 0, 0),
        ("Download", 1, 1),
    ]
    client.close.assert_called_once()
    assert close_target_db.call_count == 1
    assert close_cache_db.call_count == 0
    app._close_owned_db()
    assert close_cache_db.call_count == 1


def test_cogitus_app_clone_remote_to_local_requires_config(
    db: SqliterDB,
) -> None:
    """Clone should fail fast when the remote API is not configured."""
    app = CogitusApp(db=db, settings=_FakeSettings())

    with pytest.raises(
        RuntimeError,
        match="Remote API is not fully configured",
    ):
        app.clone_remote_to_local()


def test_cogitus_app_should_prompt_after_clone_uses_setting(
    db: SqliterDB,
) -> None:
    """Prompt preference should follow the persisted settings value."""
    app = CogitusApp(
        db=db,
        settings=_FakeSettings(prompt_after_clone=False),
    )

    assert app.should_prompt_after_clone() is False


def test_cogitus_app_clone_target_prefers_explicit_local_db_path(
    mocker: MockerFixture,
    db: SqliterDB,
    tmp_path: Path,
) -> None:
    """Local mode with an explicit db_path should clone into that file."""
    db_path = str(tmp_path / "custom-local.db")
    get_db = mocker.patch("cogitus.app.get_db", return_value=db)
    app = CogitusApp(
        db_path=db_path,
        settings=_FakeSettings(),
    )

    get_db.reset_mock()

    assert app._resolve_clone_target_local_db_path() == db_path


def test_cogitus_app_clone_target_prefers_explicit_local_db_path_in_api_mode(
    mocker: MockerFixture,
    db: SqliterDB,
    tmp_path: Path,
) -> None:
    """API mode should still clone into the explicitly configured local DB."""
    db_path = str(tmp_path / "custom-local.db")
    get_db = mocker.patch("cogitus.app.get_db", return_value=db)
    app = CogitusApp(
        db_path=db_path,
        settings=_FakeSettings(
            backend_config=BackendConfig(
                mode=DataBackendMode.API,
                api_base_url="http://127.0.0.1:8000",
                api_username="api-user",
                api_password=_remote_secret(),
            )
        ),
    )

    get_db.reset_mock()

    assert app._resolve_clone_target_local_db_path() == db_path


@pytest.mark.asyncio
async def test_clone_remote_to_local_requires_confirmation(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """The destructive clone action should require confirmation first."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        run_clone = mocker.patch.object(
            screen,
            "_run_remote_clone",
            return_value=mocker.Mock(is_finished=False),
        )

        screen.action_clone_remote_to_local()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)
        message = str(app.screen.query_one("#confirm-message", Static).render())
        assert "overwrite the existing local database" in message.lower()

        await pilot.press("n")
        run_clone.assert_not_called()

        screen.action_clone_remote_to_local()
        await pilot.pause()
        await pilot.press("y")
        run_clone.assert_called_once()
        assert isinstance(app.screen, RemoteCloneProgressScreen)

        app.pop_screen()
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_remote_clone_progress_screen_updates_widgets() -> None:
    """Clone progress modal should update status text and per-stage progress."""
    screen = RemoteCloneProgressScreen()
    app = _StyledSingleScreenApp(screen)

    async with app.run_test() as pilot:
        screen.mark_download_complete()
        screen.update_stage_progress(
            stage="Groups",
            completed=0,
            total=0,
        )
        screen.update_stage_progress(
            stage="Ideas",
            completed=2,
            total=3,
        )

        status = str(screen.query_one("#remote-clone-status", Static).render())
        groups_bar = cast(
            "Any",
            screen.query_one("#clone-groups-progress"),
        )
        ideas_bar = cast(
            "Any",
            screen.query_one("#clone-ideas-progress"),
        )

        assert "Applying snapshot to local database" in status
        assert groups_bar.progress == 1
        assert groups_bar.total == 1
        assert ideas_bar.progress == 2
        assert ideas_bar.total == 3
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_remote_clone_switch_mode_screen_actions(
    mocker: MockerFixture,
) -> None:
    """Switch modal actions should dismiss with the correct result."""
    screen = RemoteCloneSwitchModeScreen()
    app = _StyledSingleScreenApp(screen)

    async with app.run_test() as pilot:
        assert (
            _button_label_plain(screen.query_one("#stay-remote-btn", Button))
            == "Stay Remote [S]"
        )
        assert (
            _button_label_plain(
                screen.query_one("#switch-local-after-clone-btn", Button)
            )
            == "Use Local [L]"
        )
        dismiss = mocker.patch.object(screen, "dismiss")

        screen.action_stay_remote()
        dismiss.assert_called_once_with(RemoteCloneModeAction.STAY_REMOTE)

        dismiss.reset_mock()
        screen.action_switch_local()
        dismiss.assert_called_once_with(RemoteCloneModeAction.SWITCH_LOCAL)
        app.exit()
        await pilot.pause()


def test_remote_clone_switch_mode_screen_button_handlers(
    mocker: MockerFixture,
) -> None:
    """Button handlers should delegate to the corresponding actions."""
    screen = RemoteCloneSwitchModeScreen()
    stay_remote = mocker.patch.object(screen, "action_stay_remote")
    switch_local = mocker.patch.object(screen, "action_switch_local")

    screen._handle_stay_remote_button()
    screen._handle_switch_local_button()

    stay_remote.assert_called_once_with()
    switch_local.assert_called_once_with()


@pytest.mark.asyncio
async def test_clone_switch_to_local_persists_backend_mode(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Post-clone local choice should use persisted backend config flow."""

    class _CloneSwitchApp(_SingleScreenApp):
        def __init__(self, screen: MainScreen) -> None:
            super().__init__(screen)
            self._config = BackendConfig(
                mode=DataBackendMode.API,
                api_base_url="http://127.0.0.1:8000",
                api_username="api-user",
                api_password=_remote_secret(),
            )
            self.applied: BackendConfig | None = None

        def get_backend_config(self) -> BackendConfig:
            return self._config

        def apply_backend_config(self, config: BackendConfig) -> None:
            self.applied = config

    screen = MainScreen(service)
    app = _CloneSwitchApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")

        screen._on_remote_clone_switch_dismiss(
            RemoteCloneModeAction.SWITCH_LOCAL
        )

        assert app.applied == BackendConfig(
            mode=DataBackendMode.LOCAL,
            api_base_url="http://127.0.0.1:8000",
            api_username="api-user",
            api_password=_remote_secret(),
        )
        notify.assert_called_once_with("Switched to local mode")
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_handle_remote_clone_success_local_refreshes(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Successful local clone should refresh ideas and notify."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        refresh_ideas = mocker.patch.object(screen, "refresh_ideas")
        notify = mocker.patch.object(screen, "notify")
        screen._remote_clone_worker = mocker.Mock()
        screen._clone_started_in_remote_mode = False

        screen._handle_remote_clone_success()

        refresh_ideas.assert_called_once_with(
            select_pk=screen._selected_idea_pk
        )
        notify.assert_called_once_with(
            "Local database replaced from remote snapshot"
        )
        assert screen._remote_clone_worker is None
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_handle_remote_clone_success_remote_no_prompt(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Remote clone success without prompt should only notify."""

    class _NoPromptCloneApp(_SingleScreenApp):
        def should_prompt_after_clone(self) -> bool:
            return False

    screen = MainScreen(service)
    app = _NoPromptCloneApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        push_screen = mocker.patch.object(app, "push_screen")
        screen._remote_clone_worker = mocker.Mock()
        screen._clone_started_in_remote_mode = True

        screen._handle_remote_clone_success()

        push_screen.assert_not_called()
        notify.assert_called_once_with(
            "Local database replaced from remote snapshot"
        )
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_handle_remote_clone_success_remote_prompts(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Remote clone success with prompt enabled should open the switch modal."""

    class _PromptCloneApp(_SingleScreenApp):
        def should_prompt_after_clone(self) -> bool:
            return True

    screen = MainScreen(service)
    app = _PromptCloneApp(screen)

    async with app.run_test() as pilot:
        push_screen = mocker.patch.object(app, "push_screen")
        screen._remote_clone_worker = mocker.Mock()
        screen._clone_started_in_remote_mode = True

        screen._handle_remote_clone_success()

        assert isinstance(
            push_screen.call_args.args[0],
            RemoteCloneSwitchModeScreen,
        )
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_handle_remote_clone_error_uses_default_message(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Clone error handler should fall back to a default message."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        worker = mocker.Mock(error=None)
        screen._remote_clone_worker = mocker.Mock()

        screen._handle_remote_clone_error(worker)

        notify.assert_called_once_with("Remote clone failed", severity="error")
        assert screen._remote_clone_worker is None
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_worker_state_changed_routes_remote_clone_events(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Clone worker events should dispatch to the clone handlers only."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        success = mocker.patch.object(screen, "_handle_remote_clone_success")
        error = mocker.patch.object(screen, "_handle_remote_clone_error")
        worker = mocker.Mock()
        screen._remote_clone_worker = worker

        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.SUCCESS)
        )
        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.ERROR)
        )

        success.assert_called_once_with()
        error.assert_called_once_with(worker)
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_dismiss_remote_clone_progress_pops_modal(
    service: IdeaService,
) -> None:
    """Dismissing clone progress should pop the modal when it is active."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        progress_screen = RemoteCloneProgressScreen()
        screen._remote_clone_progress_screen = progress_screen
        app.push_screen(progress_screen)
        await pilot.pause()

        screen._dismiss_remote_clone_progress()
        await pilot.pause()

        assert app.screen is screen
        assert screen._remote_clone_progress_screen is None
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_update_remote_clone_progress_updates_modal(
    service: IdeaService,
) -> None:
    """Main screen should forward progress updates into the mounted modal."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        progress_screen = RemoteCloneProgressScreen()
        screen._remote_clone_progress_screen = progress_screen
        app.push_screen(progress_screen)
        await pilot.pause()

        screen._update_remote_clone_progress(
            progress=cast(
                "Any",
                type(
                    "Progress",
                    (),
                    {"stage": "Download", "completed": 1, "total": 1},
                )(),
            )
        )
        screen._update_remote_clone_progress(
            progress=cast(
                "Any",
                type(
                    "Progress",
                    (),
                    {"stage": "Tags", "completed": 2, "total": 4},
                )(),
            )
        )

        status = str(
            progress_screen.query_one("#remote-clone-status", Static).render()
        )
        tags_bar = cast(
            "Any",
            progress_screen.query_one("#clone-tags-progress"),
        )
        assert "Applying snapshot to local database" in status
        assert tags_bar.progress == 2
        assert tags_bar.total == 4
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_update_remote_clone_progress_ignores_missing_modal(
    service: IdeaService,
) -> None:
    """Progress updates should be ignored when no modal is mounted."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        screen._update_remote_clone_progress(
            progress=cast(
                "Any",
                type(
                    "Progress",
                    (),
                    {"stage": "Tags", "completed": 2, "total": 4},
                )(),
            )
        )
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_run_remote_clone_requires_app_hook(
    service: IdeaService,
) -> None:
    """Clone worker body should fail clearly without an app clone hook."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        with pytest.raises(TypeError, match="Remote clone is unavailable"):
            cast("Any", MainScreen._run_remote_clone).__wrapped__(screen)
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_run_remote_clone_forwards_progress_updates(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Clone worker should pass progress back through call_from_thread."""

    class _CloneApp(_SingleScreenApp):
        def clone_remote_to_local(
            self,
            *,
            progress_callback: Callable[[SnapshotImportProgress], None]
            | None = None,
        ) -> None:
            if progress_callback is not None:
                progress_callback(
                    type(
                        "Progress",
                        (),
                        {"stage": "Tags", "completed": 2, "total": 4},
                    )()
                )

    screen = MainScreen(service)
    app = _CloneApp(screen)

    async with app.run_test() as pilot:
        call_from_thread = mocker.patch.object(app, "call_from_thread")

        cast("Any", MainScreen._run_remote_clone).__wrapped__(screen)

        call_from_thread.assert_called_once()
        assert call_from_thread.call_args.args[0] == (
            screen._update_remote_clone_progress
        )
        progress = call_from_thread.call_args.args[1]
        assert progress.stage == "Tags"
        assert progress.completed == 2
        assert progress.total == 4
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_action_clone_remote_to_local_warns_when_already_running(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Starting a second clone should warn instead of opening a modal."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        screen._remote_clone_worker = mocker.Mock(is_finished=False)

        screen.action_clone_remote_to_local()

        notify.assert_called_once_with(
            "Remote clone already in progress",
            severity="warning",
        )
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_remote_clone_switch_dismiss_branches(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Dismiss results should notify for stay-remote and app-hook fallback."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")

        screen._on_remote_clone_switch_dismiss(
            RemoteCloneModeAction.STAY_REMOTE
        )
        notify.assert_called_once_with(
            "Local database replaced from remote snapshot"
        )

        notify.reset_mock()
        screen._on_remote_clone_switch_dismiss(
            RemoteCloneModeAction.SWITCH_LOCAL
        )
        notify.assert_called_once_with(
            "Local fallback is unavailable",
            severity="error",
        )
        app.exit()
        await pilot.pause()


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


@pytest.mark.asyncio
async def test_cogitus_app_mount_warns_on_invalid_data_backend_mode(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Invalid backend mode should notify and fallback to local."""
    settings = _FakeSettings()
    settings.data_backend_mode = "broken-mode"
    app = CogitusApp(db=db, settings=settings)
    notify = mocker.patch.object(app, "notify")

    async with app.run_test() as pilot:
        assert app.get_backend_config().mode == DataBackendMode.LOCAL
        notify.assert_called_once_with(
            "Invalid config 'data_backend_mode=broken-mode'; using 'local'.",
            severity="warning",
        )
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_mount_warns_on_invalid_timezone(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Invalid timezone should notify and fallback to system."""
    settings = _FakeSettings(timezone="Not/ARealTimezone")
    app = CogitusApp(db=db, settings=settings)
    notify = mocker.patch.object(app, "notify")

    async with app.run_test() as pilot:
        assert app._configured_timezone == "Not/ARealTimezone"
        assert app._invalid_timezone is True
        assert app._timezone == "Not/ARealTimezone"
        notify.assert_any_call(
            "Invalid config "
            "'timezone=Not/ARealTimezone'; "
            "using system timezone.",
            severity="warning",
        )
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_mount_warns_on_invalid_date_format(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Invalid date format should notify and fallback to system locale."""
    settings = _FakeSettings(date_format="ymd")
    app = CogitusApp(db=db, settings=settings)
    notify = mocker.patch.object(app, "notify")

    async with app.run_test() as pilot:
        assert app._configured_date_format == "ymd"
        assert app._date_format == ""
        assert app._invalid_date_format is True
        valid_values = ", ".join(f"'{value}'" for value in VALID_DATE_FORMATS)
        notify.assert_any_call(
            "Invalid config 'date_format=ymd'; "
            "using system locale. "
            f"Valid values: {valid_values}.",
            severity="warning",
        )
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_restores_non_default_theme(
    db: SqliterDB,
) -> None:
    """App should restore a non-default persisted theme on startup."""
    settings = _FakeSettings()
    settings.theme = "nord"
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        assert app.theme == "nord"
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_persists_theme_change(
    db: SqliterDB,
) -> None:
    """Changing the theme at runtime should immediately persist to settings."""
    settings = _FakeSettings()
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        settings.saved = False
        app.theme = DEFAULT_THEME
        await pilot.pause()
        assert settings.saved is False

        app.theme = "gruvbox"
        await pilot.pause()
        assert settings.theme == "gruvbox"
        assert settings.saved is True
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_invalid_stored_theme_falls_back_to_default(
    db: SqliterDB,
) -> None:
    """An unrecognised stored theme should fall back to DEFAULT_THEME."""
    settings = _FakeSettings()
    settings.theme = "not-a-real-theme"
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        assert app.theme == DEFAULT_THEME
        assert settings.theme == DEFAULT_THEME
        assert settings.saved is True
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

    app = CogitusApp(settings=settings)

    get_db.assert_called_once_with(default_group_name="default")
    assert app.title == "Cogitus [local]"
    app._close_owned_db()


@pytest.mark.asyncio
async def test_cogitus_app_exit_closes_owned_db(
    mocker: MockerFixture,
) -> None:
    """App-owned database connections should close on app exit."""
    db = get_db(memory=True)
    close = mocker.spy(db, "close")
    mocker.patch("cogitus.app.get_db", return_value=db)
    app = CogitusApp(settings=_FakeSettings())

    async with app.run_test() as pilot:
        app.exit()
        await pilot.pause()

    assert close.call_count == 1


@pytest.mark.asyncio
async def test_cogitus_app_exit_does_not_close_injected_db(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Injected database connections should remain caller-owned on exit."""
    close = mocker.spy(db, "close")
    app = CogitusApp(db=db, settings=_FakeSettings())

    async with app.run_test() as pilot:
        app.exit()
        await pilot.pause()

    assert close.call_count == 0


def test_cogitus_app_init_normalizes_configured_default_group_name(
    mocker: MockerFixture,
    db: SqliterDB,
) -> None:
    """App should pass normalized configured default group name to DB."""
    get_db = mocker.patch("cogitus.app.get_db", return_value=db)
    settings = _FakeSettings(default_group_name="  Inbox  ")

    app = CogitusApp(settings=settings)

    get_db.assert_called_once_with(default_group_name="inbox")
    app._close_owned_db()


def test_cogitus_app_init_uses_remote_cache_db_when_api_mode(
    mocker: MockerFixture,
    db: SqliterDB,
) -> None:
    """Remote mode should use the dedicated cache database path."""
    get_db = mocker.patch("cogitus.app.get_db", return_value=db)
    settings = _FakeSettings(
        backend_config=BackendConfig(
            mode=DataBackendMode.API,
            api_base_url="http://127.0.0.1:8000",
            api_username="api-user",
            api_password=_remote_secret(),
        )
    )

    app = CogitusApp(settings=settings)

    get_db.assert_called_once_with(
        "~/.config/cogitus/cogitus-remote-cache.db",
        default_group_name="default",
    )
    assert app.title == "Cogitus [remote]"
    assert app.get_backend_config() == BackendConfig(
        mode=DataBackendMode.API,
        api_base_url="http://127.0.0.1:8000",
        api_username="api-user",
        api_password=_remote_secret(),
    )
    app._close_owned_db()


def test_cogitus_app_build_backend_raises_without_db(
    db: SqliterDB,
) -> None:
    """Building a backend should fail clearly when no DB is available."""
    app = CogitusApp(db=db, settings=_FakeSettings())
    app._db = None

    with pytest.raises(
        RuntimeError,
        match="Backend database is not initialized",
    ):
        app._build_backend()


def test_cogitus_app_build_main_screen_includes_app_metadata(
    mocker: MockerFixture,
    db: SqliterDB,
) -> None:
    """App should pass resolved metadata into the main screen."""
    settings = _FakeSettings()
    main_screen = mocker.patch("cogitus.app.MainScreen")
    mocker.patch(
        "cogitus.app.get_app_metadata",
        return_value=AppMetadata(
            title="Cogitus",
            version="1.2.3",
            summary="Test summary",
        ),
    )

    app = CogitusApp(db=db, settings=settings)
    app._build_main_screen()

    main_screen.assert_called_once_with(
        app._service,
        initial_select_pk=None,
        on_selected_idea_changed=app._on_selected_idea_changed,
        edit_body_cursor_mode=app._edit_body_cursor_mode,
        new_idea_group_mode=app._new_idea_group_mode,
        app_metadata=AppMetadata(
            title="Cogitus",
            version="1.2.3",
            summary="Test summary",
        ),
    )
    assert main_screen.return_value.title == "Cogitus [local]"


@pytest.mark.asyncio
async def test_cogitus_app_apply_backend_config_rebuilds_backend(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Applying backend config should save settings and replace the backend."""
    mocker.patch.object(
        RemoteIdeaBackend, "sync_from_remote", return_value=None
    )
    settings = _FakeSettings()
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        assert isinstance(app.screen, MainScreen)
        replace_service = mocker.patch.object(app.screen, "replace_service")

        app.apply_backend_config(
            BackendConfig(
                mode=DataBackendMode.API,
                api_base_url="http://127.0.0.1:8000",
                api_username="api-user",
                api_password=_remote_secret(),
            )
        )

        assert settings.saved is True
        assert settings.data_backend_mode == DataBackendMode.API.value
        assert isinstance(app._service, RemoteIdeaBackend)
        replace_service.assert_called_once_with(app._service)
        assert app.title == "Cogitus [remote]"
        assert app.screen.title == "Cogitus [remote]"
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_apply_backend_config_closes_owned_db_before_replace(
    mocker: MockerFixture,
) -> None:
    """Owned database connections should close before backend rebuilds."""
    initial_db = get_db(memory=True)
    replacement_db = get_db(memory=True)
    initial_close = mocker.spy(initial_db, "close")
    replacement_close = mocker.spy(replacement_db, "close")
    mocker.patch(
        "cogitus.app.get_db",
        side_effect=[initial_db, replacement_db],
    )
    mocker.patch.object(
        RemoteIdeaBackend, "sync_from_remote", return_value=None
    )
    app = CogitusApp(settings=_FakeSettings())

    async with app.run_test() as pilot:
        app.apply_backend_config(
            BackendConfig(
                mode=DataBackendMode.API,
                api_base_url="http://127.0.0.1:8000",
                api_username="api-user",
                api_password=_remote_secret(),
            )
        )

        assert initial_close.call_count == 1
        assert app._db is replacement_db
        assert app._owns_db is True
        app.exit()
        await pilot.pause()

    assert replacement_close.call_count == 1


@pytest.mark.asyncio
async def test_cogitus_app_replace_backend_preserves_old_backend(
    mocker: MockerFixture,
) -> None:
    """Failed DB rebuilds should leave the current backend running."""
    initial_db = get_db(memory=True)
    initial_close = mocker.spy(initial_db, "close")
    mocker.patch("cogitus.app.get_db", return_value=initial_db)
    app = CogitusApp(settings=_FakeSettings())
    old_service = app._service
    mocker.patch.object(
        app,
        "_build_backend_db",
        side_effect=RuntimeError("db build failed"),
    )

    async with app.run_test() as pilot:
        with pytest.raises(RuntimeError, match="db build failed"):
            app.apply_backend_config(
                BackendConfig(
                    mode=DataBackendMode.API,
                    api_base_url="http://127.0.0.1:8000",
                    api_username="api-user",
                    api_password=_remote_secret(),
                )
            )

        assert app._service is old_service
        assert app._db is initial_db
        assert app._owns_db is True
        assert initial_close.call_count == 0
        app.exit()
        await pilot.pause()

    assert initial_close.call_count == 1


@pytest.mark.asyncio
async def test_cogitus_app_replace_backend_closes_new_owned_db_on_build_failure(
    mocker: MockerFixture,
) -> None:
    """Failed backend construction should clean up the replacement DB."""
    initial_db = get_db(memory=True)
    replacement_db = get_db(memory=True)
    initial_close = mocker.spy(initial_db, "close")
    replacement_close = mocker.spy(replacement_db, "close")
    mocker.patch("cogitus.app.get_db", return_value=initial_db)
    app = CogitusApp(settings=_FakeSettings())
    old_service = app._service
    mocker.patch("cogitus.app.get_db", return_value=replacement_db)
    mocker.patch.object(
        app,
        "_build_backend",
        side_effect=RuntimeError("backend build failed"),
    )

    async with app.run_test() as pilot:
        with pytest.raises(RuntimeError, match="backend build failed"):
            app.apply_backend_config(
                BackendConfig(
                    mode=DataBackendMode.API,
                    api_base_url="http://127.0.0.1:8000",
                    api_username="api-user",
                    api_password=_remote_secret(),
                )
            )

        assert replacement_close.call_count == 1
        assert app._service is old_service
        assert app._db is initial_db
        assert app._owns_db is True
        assert initial_close.call_count == 0
        app.exit()
        await pilot.pause()

    assert initial_close.call_count == 1


@pytest.mark.asyncio
async def test_cogitus_app_apply_backend_config_closes_remote_backend(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Switching away from a remote backend should close the old one."""
    remote_backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=mocker.Mock(),
    )
    mocker.patch.object(remote_backend, "sync_from_remote", return_value=None)
    settings = _FakeSettings()
    app = CogitusApp(db=db, settings=settings, backend=remote_backend)

    async with app.run_test() as pilot:
        close = mocker.patch.object(remote_backend, "close")
        db_close = mocker.spy(db, "close")
        replace_service = mocker.patch.object(app.screen, "replace_service")

        app.apply_backend_config(
            BackendConfig(
                mode=DataBackendMode.LOCAL,
                api_base_url="",
                api_username="",
                api_password="",
            )
        )

        close.assert_called_once_with()
        replace_service.assert_called_once_with(app._service)
        assert db_close.call_count == 0
        assert app.title == "Cogitus [local]"
        assert app.screen.title == "Cogitus [local]"
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_cached_remote_mode_updates_titles(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Runtime remote offline state should only affect the active title."""
    mocker.patch.object(
        RemoteIdeaBackend, "sync_from_remote", return_value=None
    )
    settings = _FakeSettings(
        backend_config=BackendConfig(
            mode=DataBackendMode.API,
            api_base_url="http://127.0.0.1:8000",
            api_username="api-user",
            api_password=_remote_secret(),
        )
    )
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        app.activate_cached_remote_mode()
        assert app.title == "Cogitus [remote: offline]"
        assert app.screen.title == "Cogitus [remote: offline]"
        assert settings.data_backend_mode == DataBackendMode.API.value

        app.restore_remote_mode()
        assert app.title == "Cogitus [remote]"
        assert app.screen.title == "Cogitus [remote]"
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_remote_runtime_title_helpers_are_noops_in_local_mode(
    db: SqliterDB,
) -> None:
    """Remote runtime title helpers should no-op when local mode is active."""
    app = CogitusApp(db=db, settings=_FakeSettings())

    async with app.run_test() as pilot:
        app.activate_cached_remote_mode()
        assert app.title == "Cogitus [local]"

        app.restore_remote_mode()
        assert app.title == "Cogitus [local]"
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_session_local_fallback_is_not_persisted(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Session-local fallback should not rewrite persisted backend settings."""
    mocker.patch.object(
        RemoteIdeaBackend, "sync_from_remote", return_value=None
    )
    settings = _FakeSettings(
        backend_config=BackendConfig(
            mode=DataBackendMode.API,
            api_base_url="http://127.0.0.1:8000",
            api_username="api-user",
            api_password=_remote_secret(),
        )
    )
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        assert isinstance(app._service, RemoteIdeaBackend)
        close = mocker.patch.object(app._service, "close")
        db_close = mocker.spy(db, "close")

        app.activate_session_local_fallback()

        close.assert_called_once_with()
        assert db_close.call_count == 0
        assert settings.data_backend_mode == DataBackendMode.API.value
        assert not isinstance(app._service, RemoteIdeaBackend)
        assert app.get_backend_config().mode == DataBackendMode.LOCAL
        assert app.title == "Cogitus [local]"
        assert app.screen.title == "Cogitus [local]"
        app.exit()
        await pilot.pause()


@pytest.mark.asyncio
async def test_cogitus_app_session_fallback_closes_owned_db(
    mocker: MockerFixture,
) -> None:
    """Session-local fallback should close the previous owned DB."""
    initial_db = get_db(memory=True)
    replacement_db = get_db(memory=True)
    initial_close = mocker.spy(initial_db, "close")
    replacement_close = mocker.spy(replacement_db, "close")
    mocker.patch(
        "cogitus.app.get_db",
        side_effect=[initial_db, replacement_db],
    )
    mocker.patch.object(
        RemoteIdeaBackend, "sync_from_remote", return_value=None
    )
    settings = _FakeSettings(
        backend_config=BackendConfig(
            mode=DataBackendMode.API,
            api_base_url="http://127.0.0.1:8000",
            api_username="api-user",
            api_password=_remote_secret(),
        )
    )
    app = CogitusApp(settings=settings)

    async with app.run_test() as pilot:
        app.activate_session_local_fallback()

        assert initial_close.call_count == 1
        assert app._db is replacement_db
        assert app._owns_db is True
        app.exit()
        await pilot.pause()

    assert replacement_close.call_count == 1


@pytest.mark.asyncio
async def test_main_screen_sync_remote_before_edit_notifies_on_failure(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Edit preparation should report worker failures on the UI thread."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        worker = mocker.Mock(error=RuntimeError("Remote sync failed"))
        run_remote_sync = mocker.patch.object(
            screen,
            "_run_remote_sync",
            return_value=worker,
        )
        mocker.patch.object(
            screen,
            "_syncing_backend",
            return_value=mocker.Mock(),
        )

        assert screen._sync_remote_before_edit() is False
        run_remote_sync.assert_called_once_with()
        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.ERROR)
        )
        notify.assert_called_once_with("Remote sync failed", severity="error")
        assert app.sub_title == ""
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_sync_remote_before_edit_clears_indicator_on_bug(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Unexpected worker failures should still clear the indicator."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        worker = mocker.Mock(error=KeyError("boom"))
        mocker.patch.object(
            screen,
            "_run_remote_sync",
            return_value=worker,
        )
        mocker.patch.object(
            screen,
            "_syncing_backend",
            return_value=mocker.Mock(),
        )

        assert screen._sync_remote_before_edit() is False
        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.ERROR)
        )

        notify.assert_called_once_with("'boom'", severity="error")
        assert app.sub_title == ""
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_replace_service_refreshes_and_reconfigures(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Replacing the backend should reconfigure sync and refresh selection."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        configure = mocker.patch.object(screen, "_configure_remote_sync")
        refresh = mocker.patch.object(screen, "refresh_ideas")
        screen._selected_idea_pk = 3

        screen.replace_service(service)

        configure.assert_called_once_with()
        refresh.assert_called_once_with(select_pk=3)
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_configure_remote_sync_branches(
    service: IdeaService,
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Remote sync configuration should enable and disable polling cleanly."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)
    remote_backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=mocker.Mock(),
    )

    async with app.run_test() as pilot:
        timer = mocker.Mock()
        screen._remote_sync_timer = timer
        request_sync = mocker.patch.object(screen, "_request_remote_sync")
        set_interval = mocker.patch.object(
            screen,
            "set_interval",
            return_value=mocker.Mock(),
        )

        mocker.patch.object(screen, "_syncing_backend", return_value=None)
        screen._configure_remote_sync()
        timer.stop.assert_called_once_with()
        request_sync.assert_not_called()

        request_sync.reset_mock()
        mocker.patch.object(
            screen,
            "_syncing_backend",
            return_value=remote_backend,
        )
        screen._configure_remote_sync()
        request_sync.assert_called_once_with()
        set_interval.assert_called_once_with(
            screen.REMOTE_SYNC_INTERVAL_SECONDS,
            screen._request_remote_sync,
        )

        assert screen._syncing_backend() is remote_backend
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_request_remote_sync_guards_missing_or_busy_backend(
    service: IdeaService,
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Remote sync requests should skip missing or already-running backends."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)
    remote_backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=mocker.Mock(),
    )

    async with app.run_test() as pilot:
        set_indicator = mocker.patch.object(screen, "_set_sync_indicator")
        run_remote_sync = mocker.patch.object(screen, "_run_remote_sync")

        mocker.patch.object(screen, "_syncing_backend", return_value=None)
        screen._request_remote_sync()
        set_indicator.assert_not_called()
        run_remote_sync.assert_not_called()

        set_indicator.reset_mock()
        run_remote_sync.reset_mock()
        mocker.patch.object(
            screen,
            "_syncing_backend",
            return_value=remote_backend,
        )
        screen._remote_sync_worker = mocker.Mock(is_finished=False)
        screen._request_remote_sync()
        set_indicator.assert_not_called()
        run_remote_sync.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_request_remote_sync_schedules_when_idle_and_visible(
    service: IdeaService,
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Remote sync requests should schedule only when the screen is ready."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)
    remote_backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=mocker.Mock(),
    )

    async with app.run_test() as pilot:
        set_indicator = mocker.patch.object(screen, "_set_sync_indicator")
        run_remote_sync = mocker.patch.object(screen, "_run_remote_sync")

        mocker.patch.object(
            screen,
            "_syncing_backend",
            return_value=remote_backend,
        )
        screen._request_remote_sync()
        set_indicator.assert_not_called()
        run_remote_sync.assert_called_once_with()

        set_indicator.reset_mock()
        run_remote_sync.reset_mock()
        screen._remote_sync_worker = mocker.Mock(is_finished=True)
        screen._request_remote_sync()
        set_indicator.assert_not_called()
        run_remote_sync.assert_called_once_with()

        set_indicator.reset_mock()
        run_remote_sync.reset_mock()
        app.push_screen(HelpScreen())
        await pilot.pause()
        screen._request_remote_sync()
        set_indicator.assert_not_called()
        run_remote_sync.assert_not_called()
        app.pop_screen()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_remote_sync_helper_branches(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Remote sync helper methods should preserve state and ignore noise."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        refresh = mocker.patch.object(screen, "refresh_ideas")
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        mocker.patch.object(panel, "get_selected_group_pk", return_value=1)
        screen._selected_idea_pk = 2
        screen._refresh_after_remote_sync()
        refresh.assert_called_once_with(select_pk=2, select_group_pk=1)

        refresh.reset_mock()
        worker = mocker.Mock(is_finished=False)
        continuation = mocker.Mock()
        mocker.patch.object(
            screen,
            "_syncing_backend",
            return_value=mocker.Mock(),
        )
        run_remote_sync = mocker.patch.object(
            screen,
            "_run_remote_sync",
            return_value=worker,
        )
        assert screen._sync_remote_before_edit(continuation) is False
        run_remote_sync.assert_called_once_with()
        refresh.assert_not_called()
        assert screen._pending_pre_edit_action is continuation

        second_continuation = mocker.Mock()
        screen._sync_remote_before_edit(second_continuation)
        run_remote_sync.assert_called_once_with()
        assert screen._pending_pre_edit_action is second_continuation

        refresh_after_sync = mocker.patch.object(
            screen,
            "_refresh_after_remote_sync",
        )
        run_pending_pre_edit = mocker.patch.object(
            screen,
            "_run_pending_pre_edit_action",
        )
        notify = mocker.patch.object(screen, "notify")
        screen._remote_sync_worker = mocker.Mock()
        screen.on_worker_state_changed(
            mocker.Mock(worker=mocker.Mock(), state=WorkerState.SUCCESS)
        )
        refresh_after_sync.assert_not_called()
        run_pending_pre_edit.assert_not_called()
        notify.assert_not_called()

        worker_runner = inspect.unwrap(MainScreen._run_remote_sync)
        mocker.patch.object(screen, "_syncing_backend", return_value=None)
        assert worker_runner(screen) == RemoteSyncResult(changed=False)
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_pre_edit_sync_runs_pending_action_on_success(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Deferred edit actions should run after the worker succeeds."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        refresh_after_sync = mocker.patch.object(
            screen,
            "_refresh_after_remote_sync",
        )
        continuation = mocker.Mock()
        worker = mocker.Mock()
        mocker.patch.object(
            screen,
            "_run_remote_sync",
            return_value=worker,
        )
        mocker.patch.object(
            screen,
            "_syncing_backend",
            return_value=mocker.Mock(),
        )

        assert screen._sync_remote_before_edit(continuation) is False
        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.SUCCESS)
        )

        refresh_after_sync.assert_called_once_with()
        continuation.assert_called_once_with()
        assert screen._pending_pre_edit_action is None
        assert app.sub_title == ""
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_worker_success_refreshes_after_remote_sync(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Successful remote sync worker completion should refresh the screen."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        refresh_after_sync = mocker.patch.object(
            screen,
            "_refresh_after_remote_sync",
        )
        worker = mocker.Mock()
        screen._remote_sync_worker = worker
        screen._set_sync_indicator()

        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.SUCCESS)
        )

        refresh_after_sync.assert_called_once_with()
        assert app.sub_title == ""
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_worker_unchanged_sync_skips_refresh(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Unchanged remote sync should clear indicators without reloading UI."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        refresh_after_sync = mocker.patch.object(
            screen,
            "_refresh_after_remote_sync",
        )
        worker = mocker.Mock(result=RemoteSyncResult(changed=False))
        screen._remote_sync_worker = worker
        screen._set_sync_indicator()

        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.SUCCESS)
        )

        refresh_after_sync.assert_not_called()
        assert app.sub_title == ""
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_tree_selection_does_not_request_remote_sync(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Tree navigation should read local cache without remote refresh calls."""
    first = service.create_idea("First")
    second = service.create_idea("Second")
    screen = MainScreen(service, initial_select_pk=first.pk)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        request_remote_sync = mocker.patch.object(
            screen,
            "_request_remote_sync",
        )
        run_remote_sync = mocker.patch.object(screen, "_run_remote_sync")

        screen.on_idea_list_panel_idea_selected(
            IdeaListPanel.IdeaSelected(second)
        )

        request_remote_sync.assert_not_called()
        run_remote_sync.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_worker_success_recovers_remote_cached_mode(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """A successful retry should restore normal remote mode from cache mode."""

    class _RecoveryApp(_SingleScreenApp):
        def __init__(self, screen: MainScreen) -> None:
            super().__init__(screen)
            self.restore_calls = 0

        def restore_remote_mode(self) -> None:
            self.restore_calls += 1

    screen = MainScreen(service)
    app = _RecoveryApp(screen)

    async with app.run_test() as pilot:
        service.create_idea("Seed")
        await pilot.pause()
        notify = mocker.patch.object(screen, "notify")
        refresh_after_sync = mocker.patch.object(
            screen,
            "_refresh_after_remote_sync",
        )
        worker = mocker.Mock()
        screen._remote_sync_worker = worker
        screen._remote_cached_read_only = True
        screen._set_sync_indicator()

        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.SUCCESS)
        )

        assert screen._remote_cached_read_only is False
        assert app.restore_calls == 1
        notify.assert_called_once_with("Remote API reconnected")
        refresh_after_sync.assert_called_once_with()
        assert app.sub_title == ""
        await pilot.pause()
        footer = screen.query_one("#bindings-footer", Footer)
        assert "n" in screen.active_bindings
        assert screen.active_bindings["n"].binding.description == "New"
        assert any(
            child.__class__.__name__ == "FooterKey" for child in footer.children
        )
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_worker_error_notifies_once(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Failed remote sync worker completion should notify the user."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        worker = mocker.Mock(error=ValueError("Remote API request failed"))
        screen._remote_sync_worker = worker
        screen._set_sync_indicator()

        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.ERROR)
        )
        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.ERROR)
        )

        notify.assert_called_once_with(
            "Remote API request failed",
            severity="error",
        )
        assert app.sub_title == ""
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_worker_error_is_suppressed_in_cached_mode(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Cached offline mode should suppress repeated remote-failure toasts."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        worker = mocker.Mock(error=ValueError("Could not reach the remote API"))
        screen._remote_sync_worker = worker
        screen._set_remote_cached_read_only(read_only=True)
        screen._set_sync_indicator()

        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.ERROR)
        )

        notify.assert_not_called()
        assert screen._remote_sync_error == "Could not reach the remote API"
        assert app.sub_title == ""
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_startup_remote_error_shows_recovery_modal(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Initial remote sync failures should open the recovery modal."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        push_screen = mocker.patch.object(app, "push_screen")
        notify = mocker.patch.object(screen, "notify")
        worker = mocker.Mock(error=ValueError("Could not reach the remote API"))
        screen._remote_sync_worker = worker
        screen._initial_remote_sync_pending = True
        screen._set_sync_indicator()

        screen.on_worker_state_changed(
            mocker.Mock(worker=worker, state=WorkerState.ERROR)
        )

        assert isinstance(
            push_screen.call_args.args[0],
            RemoteStartupRecoveryScreen,
        )
        assert push_screen.call_args.kwargs["callback"] == (
            screen._on_remote_startup_recovery_dismiss
        )
        assert screen._remote_startup_modal_open is True
        notify.assert_not_called()
        assert app.sub_title == ""
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_startup_recovery_ignores_duplicate_or_invalid_input(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Recovery helpers should no-op for duplicate show and invalid results."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        push_screen = mocker.patch.object(app, "push_screen")

        screen._remote_startup_modal_open = True
        screen._show_remote_startup_recovery("Remote sync failed")
        push_screen.assert_not_called()

        screen._remote_startup_modal_open = True
        screen._on_remote_startup_recovery_dismiss(None)
        assert screen._remote_startup_modal_open is False
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_startup_modal_actions(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Recovery actions should retry, cache, switch local, and quit cleanly."""

    class _RecoveryApp(_SingleScreenApp):
        def __init__(self, screen: MainScreen) -> None:
            super().__init__(screen)
            self.cached_calls = 0
            self.restore_calls = 0
            self.local_calls = 0

        def activate_cached_remote_mode(self) -> None:
            self.cached_calls += 1

        def restore_remote_mode(self) -> None:
            self.restore_calls += 1

        def activate_session_local_fallback(self) -> None:
            self.local_calls += 1

    screen = MainScreen(service)
    app = _RecoveryApp(screen)

    async with app.run_test() as pilot:
        request_sync = mocker.patch.object(screen, "_request_remote_sync")
        refresh_ideas = mocker.patch.object(screen, "refresh_ideas")
        notify = mocker.patch.object(screen, "notify")
        exit_app = mocker.patch.object(app, "exit")

        screen._remote_startup_modal_open = True
        screen._on_remote_startup_recovery_dismiss(
            RemoteStartupRecoveryAction.RETRY
        )
        assert screen._remote_startup_modal_open is False
        assert screen._initial_remote_sync_pending is True
        assert app.restore_calls == 1
        request_sync.assert_called_once_with()

        request_sync.reset_mock()
        screen._remote_startup_modal_open = True
        screen._on_remote_startup_recovery_dismiss(
            RemoteStartupRecoveryAction.USE_CACHE
        )
        assert screen._remote_cached_read_only is True
        assert app.cached_calls == 1
        refresh_ideas.assert_called_once_with(
            select_pk=screen._selected_idea_pk
        )

        screen._remote_startup_modal_open = True
        screen._on_remote_startup_recovery_dismiss(
            RemoteStartupRecoveryAction.SWITCH_LOCAL
        )
        assert app.local_calls == 1
        notify.assert_called_once_with("Using local mode for this session")

        screen._remote_startup_modal_open = True
        screen._on_remote_startup_recovery_dismiss(
            RemoteStartupRecoveryAction.QUIT
        )
        exit_app.assert_called_once_with()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_startup_modal_local_fallback_unavailable(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Recovery should notify if session-local fallback support is missing."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")

        screen._remote_startup_modal_open = True
        screen._on_remote_startup_recovery_dismiss(
            RemoteStartupRecoveryAction.SWITCH_LOCAL
        )

        notify.assert_called_once_with(
            "Local fallback is unavailable",
            severity="error",
        )
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_remote_startup_modal_pauses_sync_requests(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """No new remote sync worker should start while recovery modal is open."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        run_remote_sync = mocker.patch.object(screen, "_run_remote_sync")
        backend = mocker.Mock()
        screen._remote_startup_modal_open = True
        mocker.patch.object(screen, "_syncing_backend", return_value=backend)

        screen._request_remote_sync()

        run_remote_sync.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_edit_and_rename_abort_when_sync_fails(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Edit-style flows should stop before opening modals when sync fails."""
    group = service.create_group("backend")
    idea = service.create_idea("Seed", group_pk=group.pk)
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        push_screen = mocker.patch.object(app, "push_screen")
        mocker.patch.object(panel, "get_selected_idea", return_value=idea)
        mocker.patch.object(
            screen,
            "_sync_remote_before_edit",
            return_value=False,
        )

        screen.action_edit_idea()
        screen._rename_selected_group(group.pk)
        screen._rename_selected_idea(idea.pk)

        push_screen.assert_not_called()
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_cached_remote_mode_is_read_only(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Cached remote mode should block mutating actions and edit refreshes."""
    group = service.create_group("backend")
    idea = service.create_idea("Seed", group_pk=group.pk)
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        push_screen = mocker.patch.object(app, "push_screen")
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        mocker.patch.object(panel, "get_selected_idea", return_value=idea)
        mocker.patch.object(
            panel,
            "get_selected_group_pk",
            return_value=group.pk,
        )
        screen._remote_cached_read_only = True

        screen.action_new_idea()
        screen.action_new_group()
        screen.action_new_subgroup()
        screen.action_edit_idea()
        screen.action_delete_idea()
        screen.action_rename_selected()
        screen.action_delete_group()

        assert screen._sync_remote_before_edit() is False
        assert screen.check_action("new_idea", ()) is False
        assert screen.check_action("new_subgroup", ()) is False
        assert screen.check_action("edit_idea", ()) is False
        push_screen.assert_not_called()
        assert notify.call_count == 8
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_cached_remote_mode_blocks_mutation_callbacks(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Read-only cached mode should also guard direct mutation callbacks."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")
        delete_idea = mocker.patch.object(service, "delete_idea")
        rename_group = mocker.patch.object(service, "rename_group")
        rename_idea = mocker.patch.object(service, "rename_idea")
        delete_group = mocker.patch.object(service, "delete_group")
        screen._remote_cached_read_only = True

        screen._on_delete_confirm(1, confirmed=True)
        screen._on_group_rename_dismiss(1, "renamed")
        screen._on_idea_rename_dismiss(1, "renamed")
        screen._on_delete_group_confirm(1, confirmed=True)
        screen._on_delete_group_reassign(1, 2)

        delete_idea.assert_not_called()
        rename_group.assert_not_called()
        rename_idea.assert_not_called()
        delete_group.assert_not_called()
        assert notify.call_count == 5
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_check_action_and_bindings_cover_runtime_branches(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Action gating and footer bindings should cover runtime branches."""
    group = service.create_group("backend")
    service.create_idea("Seed", group_pk=group.pk)
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        subgroup_binding = next(
            binding
            for binding in screen.BINDINGS
            if isinstance(binding, Binding)
            if binding.action == "new_subgroup"
        )
        assert subgroup_binding.key == "ctrl+g"
        assert subgroup_binding.description == "New Subgroup"

        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        screen._remote_cached_read_only = True
        assert screen.check_action("new_idea", ()) is False

        screen._remote_cached_read_only = False
        mocker.patch.object(
            panel,
            "is_search_input_focused",
            return_value=False,
        )
        mocker.patch.object(
            panel,
            "get_selected_group_pk",
            return_value=group.pk,
        )
        assert screen.check_action("rename_selected", ()) is True
        assert screen.check_action("toggle_focus", ()) is True

        mocker.patch.object(panel, "is_search_input_focused", return_value=True)
        mocker.patch.object(panel, "search_is_active", return_value=False)
        bindings = screen.active_bindings
        assert list(bindings) == ["escape"]

        mocker.patch.object(panel, "search_is_active", return_value=True)
        mocker.patch.object(
            panel,
            "is_search_results_focused",
            return_value=False,
        )
        bindings = screen.active_bindings
        assert all(
            binding.binding.action in screen._SEARCH_INPUT_FOOTER_ACTIONS
            for binding in bindings.values()
        )

        mocker.patch.object(
            panel,
            "is_search_input_focused",
            return_value=False,
        )
        mocker.patch.object(
            panel,
            "is_search_results_focused",
            return_value=True,
        )
        bindings = screen.active_bindings
        assert all(
            binding.binding.action in screen._SEARCH_RESULTS_FOOTER_ACTIONS
            for binding in bindings.values()
        )

        seen: list[int | None] = []
        screen._on_selected_idea_changed = seen.append
        screen._set_selected_idea(group.pk)
        assert screen._selected_idea_pk == group.pk
        assert seen == [group.pk]
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_backend_config_flow(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Settings action should open the config modal and apply updates."""

    class _BackendConfigApp(_SingleScreenApp):
        def __init__(self, screen: MainScreen) -> None:
            super().__init__(screen)
            self._config = BackendConfig(
                mode=DataBackendMode.LOCAL,
                api_base_url="",
                api_username="",
                api_password="",
            )
            self.applied: BackendConfig | None = None

        def get_backend_config(self) -> BackendConfig:
            return self._config

        def apply_backend_config(self, config: BackendConfig) -> None:
            self.applied = config

    screen = MainScreen(service)
    app = _BackendConfigApp(screen)

    async with app.run_test() as pilot:
        push_screen = mocker.patch.object(app, "push_screen")
        screen.action_show_backend_config()
        assert isinstance(push_screen.call_args.args[0], BackendConfigScreen)

        notify = mocker.patch.object(screen, "notify")
        config = BackendConfig(
            mode=DataBackendMode.API,
            api_base_url="http://127.0.0.1:8000",
            api_username="api-user",
            api_password=_remote_secret(),
        )
        screen._on_backend_config_dismiss(config)

        assert app.applied == config
        notify.assert_called_once_with("Connection settings updated")
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_backend_config_unavailable_paths(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Settings action should fail cleanly when app helpers are unavailable."""
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        notify = mocker.patch.object(screen, "notify")

        screen.action_show_backend_config()
        notify.assert_called_once_with(
            "Backend settings are unavailable",
            severity="error",
        )

        notify.reset_mock()
        screen._on_backend_config_dismiss(None)
        notify.assert_not_called()

        screen._on_backend_config_dismiss(
            BackendConfig(
                mode=DataBackendMode.API,
                api_base_url="http://127.0.0.1:8000",
                api_username="api-user",
                api_password=_remote_secret(),
            )
        )
        notify.assert_called_once_with(
            "Backend settings are unavailable",
            severity="error",
        )
        await pilot.pause()


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
async def test_main_screen_copy_idea_body_uses_search_preview_target(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Active search should copy from the previewed result."""
    base = service.create_idea("Base", body="base body")
    preview = service.create_idea("Preview copy token", body="preview body")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)
        content = screen.query_one("#content-panel", IdeaView)
        notify = mocker.patch.object(screen, "notify")
        copy = mocker.patch("cogitus.ui.screens.main_screen.copy_to_clipboard")
        copy.return_value = True

        screen._selected_idea_pk = base.pk
        screen.action_focus_search()
        await pilot.pause()
        search.value = "token"
        await _wait_for_search_results(pilot, search, results)
        content.focus()
        await pilot.pause()

        screen.action_copy_idea_body()

        copy.assert_called_once_with(preview.body, app)
        notify.assert_called_with("Copied idea body to clipboard")


@pytest.mark.asyncio
async def test_main_screen_copy_idea_body_with_empty_search_results_warns(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Active search with no match should warn as no selected idea."""
    base = service.create_idea("Base", body="base body")
    screen = MainScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        content = screen.query_one("#content-panel", IdeaView)
        notify = mocker.patch.object(screen, "notify")
        copy = mocker.patch("cogitus.ui.screens.main_screen.copy_to_clipboard")

        screen._selected_idea_pk = base.pk
        screen.action_focus_search()
        await pilot.pause()
        search.value = "no-match-token"
        await _wait_for_search_active(pilot, search)
        content.focus()
        await pilot.pause()

        screen.action_copy_idea_body()

        notify.assert_called_with("No idea selected", severity="warning")
        copy.assert_not_called()


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
async def test_cogitus_text_area_enter_scrolls_new_line_into_view() -> None:
    """Pressing Enter at the bottom should reveal the new cursor row."""

    class _TextAreaApp(App[None]):
        CSS = "#ta { height: 3; width: 20; }"

        def compose(self) -> ComposeResult:
            yield CogitusTextArea("line1\nline2\nline3", id="ta")

    app = _TextAreaApp()
    async with app.run_test() as pilot:
        ta = app.query_one("#ta", CogitusTextArea)
        ta.focus()
        ta.cursor_location = (2, len("line3"))
        await pilot.pause()
        initial_scroll_y = ta.scroll_offset.y

        await pilot.press("enter")
        await pilot.pause()

        assert ta.text == "line1\nline2\nline3\n"
        assert ta.cursor_location == (3, 0)
        assert ta.scroll_offset.y > initial_scroll_y


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
