"""Cogitus-specific bottom status bar helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Footer
from textual.widgets._footer import FooterKey

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.binding import Binding


class CogitusStatusBar(Horizontal):
    """Bottom bar with bindings footer plus right-side status indicators."""

    show_cache_warning = reactive(False)

    def compose(self) -> ComposeResult:
        """Compose the standard footer plus Cogitus status widgets."""
        yield Footer(
            id="bindings-footer",
            show_command_palette=False,
        )
        yield FooterNotice(widget_id="footer-cache-warning")
        palette_hint = self._build_palette_hint()
        if palette_hint is not None:
            yield palette_hint

    def on_mount(self) -> None:
        """Apply the initial visibility state to the warning notice."""
        self._sync_cache_warning_visibility()

    def _build_palette_hint(self) -> FooterPaletteHint | None:
        """Build the command-palette hint using the active binding."""
        if not self.app.ENABLE_COMMAND_PALETTE:
            return None
        try:
            _node, binding, enabled, tooltip = self.screen.active_bindings[
                self.app.COMMAND_PALETTE_BINDING
            ]
        except KeyError:
            return None
        return FooterPaletteHint(
            binding=binding,
            enabled=enabled,
            tooltip=tooltip,
            widget_id="footer-command-palette",
        )

    def watch_show_cache_warning(self, _show_cache_warning: object) -> None:
        """Toggle the warning notice without recreating the footer."""
        if self.is_attached:
            self._sync_cache_warning_visibility()

    def _sync_cache_warning_visibility(self) -> None:
        """Show or hide the cache warning while keeping the footer mounted."""
        warning = self.query_one("#footer-cache-warning", FooterNotice)
        warning.display = self.show_cache_warning


class FooterNotice(FooterKey):
    """A non-interactive footer notice using Footer's native key styling."""

    def __init__(self, *, widget_id: str | None = None) -> None:
        """Initialize the fixed read-only cache notice."""
        super().__init__(
            key="",
            key_display="",
            description="READ-ONLY CACHE",
            action="",
            tooltip="",
            classes="-cache-warning",
        )
        self.compact = False
        if widget_id is not None:
            self.id = widget_id
        self.display = False

    def on_mouse_down(self) -> None:
        """Ignore clicks; this is a status indicator, not an action."""


class FooterPaletteHint(FooterKey):
    """Command-palette hint rendered outside the standard footer widget."""

    def __init__(
        self,
        *,
        binding: Binding,
        enabled: bool,
        tooltip: str,
        widget_id: str | None = None,
    ) -> None:
        """Initialize from the active command-palette binding."""
        super().__init__(
            key=binding.key,
            key_display=binding.key_display or binding.key,
            description=binding.description,
            action=binding.action,
            disabled=not enabled,
            tooltip=binding.tooltip or tooltip,
            classes="-command-palette",
        )
        self.compact = False
        if widget_id is not None:
            self.id = widget_id
