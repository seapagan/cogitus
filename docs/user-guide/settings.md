# Settings

Cogitus stores user settings using XDG config paths.

## Settings File

Configuration is persisted under your XDG config directory for `cogitus`
(for example `~/.config/cogitus/config.toml` on many Linux systems).

## Current Settings

### `last_viewed_idea_pk`

Stores the last selected idea when the app exits.

- Type: integer
- Default: `0` (means no selection persisted yet)

!!! note
    This setting will be deprecated in a future version and stored internal to
    the cogitus database.

### `edit_body_cursor_mode`

Controls initial cursor placement when opening an existing idea in edit mode.

- Type: string
- Default: `remember`

Valid options are:

- `"remember"`
  - Uses the previously saved cursor position for that idea.
- `"start"`
  - Places the cursor at the start of the body text.
- `"end"`
  - Places the cursor at the end of the body text.

Example:

```toml
edit_body_cursor_mode="start"
```

### `new_idea_group_mode`

Controls which group is preselected when opening the **New Idea** form.

- Type: string
- Default: `contextual`

Valid options are:

- `"contextual"`
  - Uses the current selection in the left tree pane.
  - If a group is selected, that group is used.
  - If an idea is selected, that idea's group is used.
  - If nothing usable is selected, falls back to default-group behavior.
- `"default_group"`
  - Uses default-group behavior directly.

If the configured value is invalid, Cogitus falls back to `"contextual"`
and shows a warning toast at startup.

Example:

```toml
new_idea_group_mode="default_group"
```

## Notes

- Settings are saved on app exit.
