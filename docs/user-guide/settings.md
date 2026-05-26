# Settings

Cogitus stores user settings using XDG config paths.

## Settings File

Configuration is persisted under your XDG config directory for `cogitus`
(for example `~/.config/cogitus/config.toml` on many Linux systems).

## Current Settings

### `theme`

Stores the active Textual theme so it is restored on next launch.

- Type: string
- Default: `textual-dark`

The value is set automatically whenever you change the theme via the Command
Palette (`Ctrl+P` → **Set theme**). You can also set it manually. See
[Theming](theming.md) for the list of available themes.

Example:

```toml
theme="nord"
```

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

### `mcp_auth_token_expire_days`

Controls how long newly generated MCP tokens are valid.

- Type: integer
- Default: `90`

Non-positive values fall back to the default.

Example:

```toml
mcp_auth_token_expire_days=365
```

### `prompt_after_clone`

Controls whether Cogitus asks to switch the current session to local mode after
successfully running `Clone Remote To Local` from remote mode.

- Type: boolean
- Default: `true`

Behavior:

- `true`
  - After a successful clone started from remote mode, Cogitus shows a prompt
    offering `Stay Remote` or `Use Local`.
- `false`
  - After a successful clone started from remote mode, Cogitus stays in remote
    mode and only shows a success notification.

This setting only affects the post-clone prompt for remote-mode sessions. It
does not change the clone target database.

Example:

```toml
prompt_after_clone=false
```

### `save_idea_scroll_pos`

Controls whether Cogitus saves and restores the rendered idea pane scroll
position when switching between ideas.

- Type: boolean
- Default: `true`

Behavior:

- `true`
  - Saves each idea's rendered-pane scroll position locally.
  - Restores the position only while the rendered idea content is unchanged.
- `false`
  - Starts each idea at the top of the rendered pane.

This is local UI state. In remote mode it is stored only in the local cache and
is not sent to the API or shared with other users.

Example:

```toml
save_idea_scroll_pos=false
```

### `timezone`

Overrides the display timezone for timestamps shown in the TUI.

- Type: string
- Default: `""` (auto-detect from system)

When empty, Cogitus uses the system's local timezone. Set to an IANA timezone
name to force a specific timezone regardless of system configuration.

Example:

```toml
timezone="Europe/London"
```

### `date_format`

Overrides the date component ordering used when displaying dates in the TUI.

- Type: string
- Default: `""` (auto-detect from system locale)

When empty, Cogitus detects the ordering from the system locale. Valid
options are:

- `"iso"` — `YYYY-MM-DD`
- `"mdy"` — `MM/DD/YYYY` (US convention)
- `"dmy"` — `DD/MM/YYYY` (UK/EU convention)

Example:

```toml
date_format="dmy"
```

## Notes

- Settings are saved on app exit.
- Remote-backend settings can also be edited from the in-app `Backend settings`
  dialog.
- `Clone Remote To Local` is documented in [Remote Clone](remote-clone.md).
