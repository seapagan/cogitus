"""Tests for Textual screens and app integration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import PropertyMock

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, ListView, TextArea

from cogitus.app import CogitusApp
from cogitus.ui.screens.idea_form_screen import (
    ConfirmDialog,
    HelpScreen,
    IdeaFormScreen,
)
from cogitus.ui.screens.main_screen import MainScreen
from cogitus.ui.widgets.idea_list import IdeaListPanel
from cogitus.ui.widgets.idea_view import IdeaView


class _SingleScreenApp(App[None]):
    """Host app that mounts a screen on start."""

    def __init__(self, screen) -> None:
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

    def __init__(self, last_viewed_idea_pk: int = 0) -> None:
        self.last_viewed_idea_pk = last_viewed_idea_pk
        self.saved = False

    def save(self) -> None:
        """Record save invocation."""
        self.saved = True


@pytest.mark.asyncio
async def test_idea_form_screen_create_and_validation(service, mocker) -> None:
    """Form should validate title and create ideas."""
    screen = IdeaFormScreen(service)
    app = _SingleScreenApp(screen)

    async with app.run_test() as pilot:
        assert screen._get_existing_tags() == ""

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
async def test_idea_form_screen_edit_and_buttons(service, mocker) -> None:
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
        screen.on_button_pressed(
            SimpleNamespace(button=SimpleNamespace(id="save-btn"))
        )
        save_action.assert_called_once()
        screen.on_button_pressed(
            SimpleNamespace(button=SimpleNamespace(id="cancel-btn"))
        )
        cancel_action.assert_called_once()

        dismiss.reset_mock()
        IdeaFormScreen.action_cancel(screen)
        dismiss.assert_called_once_with(None)
        await pilot.pause()


@pytest.mark.asyncio
async def test_confirm_dialog_and_help_screen(mocker) -> None:
    """Confirmation and help modal actions should dismiss correctly."""
    confirm = ConfirmDialog("Are you sure?")
    app = _SingleScreenApp(confirm)
    async with app.run_test() as pilot:
        dismiss = mocker.patch.object(confirm, "dismiss")
        confirm.on_button_pressed(
            SimpleNamespace(button=SimpleNamespace(id="confirm-yes-btn"))
        )
        dismiss.assert_called_once_with(True)

        dismiss.reset_mock()
        confirm.on_button_pressed(
            SimpleNamespace(button=SimpleNamespace(id="confirm-no-btn"))
        )
        dismiss.assert_called_once_with(False)
        await pilot.pause()

    help_screen = HelpScreen()
    app2 = _SingleScreenApp(help_screen)
    async with app2.run_test() as pilot:
        dismiss = mocker.patch.object(help_screen, "dismiss")
        help_screen.action_close()
        dismiss.assert_called_once_with(None)
        await pilot.pause()


@pytest.mark.asyncio
async def test_main_screen_selection_and_search(service, mocker) -> None:
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
            "search_ideas",
            return_value=[first],
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

        list_all = mocker.patch.object(
            screen._service,
            "list_ideas",
            return_value=[first],
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
    service, mocker
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
        list_view = panel.query_one("#idea-list", ListView)
        list_view.index = 0
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
async def test_main_screen_focus_toggle_help_quit_and_callback(
    service, mocker
) -> None:
    """Main screen should handle focus, help, quit, and callback updates."""
    first = service.create_idea("First")
    selected: list[int | None] = []
    screen = MainScreen(service, on_selected_idea_changed=selected.append)
    app = _SingleScreenApp(screen)

    async with app.run_test():
        panel = screen.query_one("#idea-list-panel", IdeaListPanel)
        view = screen.query_one("#content-panel", IdeaView)

        screen.action_focus_search()
        assert app.focused is panel.query_one("#search-input")

        push = mocker.patch.object(app, "push_screen")
        screen.action_show_help()
        push.assert_called()

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
async def test_cogitus_app_mount_and_exit(db) -> None:
    """Cogitus app should restore and persist last viewed idea."""
    settings = _FakeSettings(last_viewed_idea_pk=0)
    app = CogitusApp(db=db, settings=settings)

    async with app.run_test() as pilot:
        assert isinstance(app.screen, MainScreen)
        app._on_selected_idea_changed(7)
        app.exit()
        await pilot.pause()

    assert settings.last_viewed_idea_pk == 7
    assert settings.saved is True


def test_cogitus_app_init_uses_db_path(mocker, db, tmp_path) -> None:
    """App should call get_db with db_path when provided."""
    get_db = mocker.patch("cogitus.app.get_db", return_value=db)
    settings = _FakeSettings()
    db_path = str(tmp_path / "cogitus.db")

    CogitusApp(db_path=db_path, settings=settings)

    get_db.assert_called_once_with(db_path)


def test_cogitus_app_init_uses_default_db(mocker, db) -> None:
    """App should call get_db with default args when db_path is missing."""
    get_db = mocker.patch("cogitus.app.get_db", return_value=db)
    settings = _FakeSettings()

    CogitusApp(settings=settings)

    get_db.assert_called_once_with()
