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

### `default_group_name`

Controls the canonical fallback group name used when no explicit group is
selected.

- Type: string
- Default: `default`

Behavior:

- Value is normalized to lowercase and trimmed.
- Empty values are treated as invalid and fall back to `default`.
- Cogitus ensures this group exists at startup.
- This configured group is treated as the protected default group and cannot
  be deleted.

Example:

```toml
default_group_name="inbox"
```

### `data_backend_mode`

Controls whether the TUI reads ideas from the local SQLite database or from a
remote Cogitus API server.

- Type: string
- Default: `local`

Valid options are:

- `"local"`
  - Uses the local Cogitus SQLite database directly.
- `"api"`
  - Uses a remote Cogitus API server and maintains a local cache database for
    the TUI.

You can change this from inside the app with `Ctrl+P` and the `Backend
settings` command.

If the configured value is invalid, Cogitus falls back to `"local"` and shows a
warning toast at startup.

Example:

```toml
data_backend_mode="api"
```

### `remote_api_base_url`

The base URL for the remote Cogitus API server when `data_backend_mode="api"`.

- Type: string
- Default: `""`

Behavior:

- Leading and trailing whitespace is trimmed.
- A trailing `/` is removed automatically.
- This value is required for remote mode.

Example:

```toml
remote_api_base_url="http://127.0.0.1:8000"
```

### `remote_api_username`

The username the TUI uses when authenticating against the remote Cogitus API.

- Type: string
- Default: `""`

This value is required for remote mode.

Example:

```toml
remote_api_username="api-user"
```

### `remote_api_password`

The password the TUI uses when authenticating against the remote Cogitus API.

- Type: string
- Default: `""`

This value is required for remote mode.

!!! warning
    This password is currently stored in the normal Cogitus config file. It is
    convenient, but not a hardened secret-storage solution yet.

Example:

```toml
remote_api_password="your-password"
```

## Notes

- Settings are saved on app exit.
- Remote-backend settings can also be edited from the in-app `Backend settings`
  dialog.
